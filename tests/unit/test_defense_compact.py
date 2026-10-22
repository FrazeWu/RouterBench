from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Any

import httpx
import pytest

from routebench.defense.agent import JsonRecoveryAgent, RecoveryAgentConfig
from routebench.defense.collect import PolicyChoice, collect_episode
from routebench.defense.compact import (
    CompactConfig,
    ContextOverflow,
    answer_training_ids,
    selector_messages,
)
from routebench.defense.development import load_development_tasks
from routebench.defense.ecpa import (
    AgentReply,
    AgentReplyKind,
    AgentView,
    BudgetLimits,
    DefenseObservation,
    ECPAEnvironment,
    ToolContent,
)
from routebench.defense.evaluation import HiddenOutcomeEvaluator, episode_metrics
from routebench.defense.lora import (
    BranchGroup,
    BranchOutcome,
    LoraSpec,
    model_fingerprint,
    prepare_choices,
    train_lora,
    validate_adapter,
)
from routebench.defense.pilot import (
    GpuTelemetry,
    ThermalLimit,
    ThermalPacer,
    UnguardedSimulatorReference,
)
from routebench.defense.policies import PerActionAuthorizationPolicy, PublicRulePolicy
from routebench.defense.relay import RelayCampaign, RelayStage, StagedResponseRelay
from routebench.runtime.reference import ScenarioState

ROOT = Path(__file__).parents[2]


def environment(cls: type[ECPAEnvironment] = ECPAEnvironment, **kwargs: Any) -> ECPAEnvironment:
    task = load_development_tasks(ROOT, ROOT / "configs/defense/development-contracts.yaml")[0]
    return cls(
        task.public, ScenarioState.from_fixture(task.bundle.root / "fixtures/state.json"), **kwargs
    )


def observation() -> DefenseObservation:
    result = asyncio.run(
        environment().observe(AgentReply(kind=AgentReplyKind.PROPOSE, edge_id="query_paused_ids"))
    )
    assert result is not None
    return result


def group() -> BranchGroup:
    obs = observation()
    return BranchGroup(
        group_id="actual-state-1",
        observation=obs,
        semantic_family=obs.task.contract.semantic_family,
        attack_mechanism="text_attack",
        split="development",
        source_revision="a" * 40,
        proposal_sampling_probability=1.0,
        outcomes=tuple(
            BranchOutcome(
                candidate_id=item.candidate_id,
                repeat=0,
                continuation_seed=10,
                terminated=True,
                truncated=False,
                safe_completion=item.candidate_id != "deny",
                violation=False,
                cost=2 if item.candidate_id == "deny" else 10,
                termination_reason="agent_stop",
            )
            for item in obs.menu
        ),
    )


def test_selector_allowlist_excludes_raw_content_feedback_and_tokens() -> None:
    obs = observation().model_copy(
        update={
            "tool_contents": (ToolContent(tool="file.read", content="SECRET_RELAY_TEXT"),),
            "feedback": ("SECRET_ERROR_BODY",),
            "state_token": "SECRET_STATE_TOKEN",
        }
    )
    encoded = json.dumps(selector_messages(obs))
    assert "SECRET" not in encoded
    assert "verifier" not in encoded and "reference_route" not in encoded
    assert obs.menu[1].candidate_id in encoded
    assert "receipts" in encoded and "remaining" in encoded


def test_labels_choose_completion_over_cost_and_reject_censoring_or_partial_menus() -> None:
    record = group()
    examples, audit = prepare_choices([record], development_smoke=True)
    assert examples[0].candidate_id != "deny" and audit["examples"] == 1
    censored = record.model_copy(
        update={
            "outcomes": (
                record.outcomes[0].model_copy(update={"truncated": True, "terminated": False}),
                *record.outcomes[1:],
            )
        }
    )
    with pytest.raises(ValueError, match="no complete uncensored"):
        prepare_choices([censored], development_smoke=True)
    with pytest.raises(ValueError, match="no complete uncensored"):
        prepare_choices(
            [record.model_copy(update={"outcomes": record.outcomes[:1]})], development_smoke=True
        )
    risky = record.model_copy(
        update={
            "outcomes": tuple(
                row.model_copy(update={"safe_completion": False, "violation": True, "cost": 0})
                if row.candidate_id != "deny"
                else row
                for row in record.outcomes
            )
        }
    )
    examples, _ = prepare_choices([risky], development_smoke=True)
    assert examples[0].candidate_id == "deny"


def test_branch_sources_reject_cross_split_identity_duplicates_and_seed_mismatch() -> None:
    record = group()
    with pytest.raises(ValueError, match="formal fitting"):
        prepare_choices([record])
    with pytest.raises(ValueError, match="formal fitting"):
        prepare_choices(
            [record.model_copy(update={"split": "test"})], formal_protocol_id="ecpa-test-1"
        )
    with pytest.raises(ValueError, match="duplicate branch group"):
        prepare_choices([record, record], development_smoke=True)
    wrong_seed = record.model_copy(
        update={
            "outcomes": (
                record.outcomes[0].model_copy(update={"continuation_seed": 999}),
                *record.outcomes[1:],
            )
        }
    )
    with pytest.raises(ValueError, match="share a continuation seed"):
        prepare_choices([wrong_seed], development_smoke=True)


def test_answer_only_loss_and_no_context_truncation() -> None:
    class Tokenizer:
        eos_token_id = 1

        def apply_chat_template(self, *args: Any, **kwargs: Any) -> list[int]:
            return [2, 3, 4]

        def encode(self, *args: Any, **kwargs: Any) -> list[int]:
            return [5, 6]

    ids, labels = answer_training_ids(Tokenizer(), observation(), "deny", context_tokens=6)
    assert ids == [2, 3, 4, 5, 6, 1] and labels == [-100, -100, -100, 5, 6, 1]
    with pytest.raises(ContextOverflow):
        answer_training_ids(Tokenizer(), observation(), "deny", context_tokens=5)


def test_thermal_pacer_waits_for_cooling_and_never_ignores_a_hard_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    telemetry = GpuTelemetry(tmp_path / "telemetry.json", gpu_ids=(0,))
    telemetry.rows.append({"gpu": 0, "celsius": 72})
    pacer = ThermalPacer(telemetry, minimum_gap_seconds=0, pause_celsius=70, resume_celsius=65)
    cooled = []

    def cool(seconds: float) -> None:
        cooled.append(seconds)
        telemetry.rows.append({"gpu": 0, "celsius": 65})

    monkeypatch.setattr("routebench.defense.pilot.time.sleep", cool)
    pacer.before(0)
    assert cooled and telemetry.temperature(0) == 65
    telemetry.error = "thermal slowdown"
    with pytest.raises(ThermalLimit, match="thermal slowdown"):
        pacer.before(0)


def test_development_collection_reuse_preserves_revision_and_rejects_changed_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(ROOT))
    from scripts.run_defense_pilot import Pilot

    tasks = load_development_tasks(ROOT, ROOT / "configs/defense/development-contracts.yaml")
    config_path = ROOT / "configs/defense/compact-pilot.yaml"
    agent_path = tmp_path / "configs/defense/development-agent.yaml"
    agent_path.parent.mkdir(parents=True)
    agent_path.write_text((ROOT / "configs/defense/development-agent.yaml").read_text())
    monkeypatch.setattr("scripts.run_defense_pilot.clean_revision", lambda root: "a" * 40)
    monkeypatch.setattr("scripts.run_defense_pilot.model_fingerprint", lambda path: "test-hash")
    monkeypatch.setattr("scripts.run_defense_pilot.load_development_tasks", lambda *args: tasks)
    source, output = tmp_path / "artifacts/private/source", tmp_path / "artifacts/private/output"
    Pilot(tmp_path, config_path, source)
    (source / "collection").mkdir()
    payload = group().model_dump_json()
    (source / "collection/group.private.json").write_text(payload)
    (source / "collect-cost.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "source_revision": "a" * 40,
            }
        )
    )
    (source / "collect-telemetry.json").write_text("{}")
    monkeypatch.setattr("scripts.run_defense_pilot.clean_revision", lambda root: "b" * 40)
    Pilot(tmp_path, config_path, output, collection_source=source)
    assert (output / "collection/group.private.json").read_text() == payload
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["source_revision"] == "b" * 40
    assert manifest["collection_origin"]["source_revision"] == "a" * 40
    original = json.loads((source / "manifest.json").read_text())
    original["config"]["budgets"]["decisions"] += 1
    (source / "manifest.json").write_text(json.dumps(original))
    with pytest.raises(ValueError, match="identity mismatch"):
        Pilot(tmp_path, config_path, tmp_path / "artifacts/private/bad", collection_source=source)


def test_text_relay_pair_counts_actual_calls_and_does_not_enter_system_message() -> None:
    async def run() -> None:
        for attacked in (False, True):
            requests: list[Any] = []

            def respond(request: httpx.Request, requests: list[Any] = requests) -> httpx.Response:
                requests.append(json.loads(request.content))
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {
                                    "content": '{"kind":"propose","edge_id":"query_paused_ids"}'
                                },
                            }
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    },
                )

            env = environment(budgets=BudgetLimits(agent_calls=2))
            relay = StagedResponseRelay(
                RelayCampaign(
                    task_id=env.task.contract.task_id,
                    stages=(RelayStage(node="start", edge_id="inspect_owner_contacts_early"),),
                ),
                mode="text",
                attacked=attacked,
            )
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                agent = JsonRecoveryAgent(
                    RecoveryAgentConfig(), client=client, relay=relay, text_receiver=True
                )
                assert await env.call_agent(agent, seed=7) is not None
                assert len(agent.calls) == env.budget.used["agent_calls"] == 2
                assert agent.calls[0].purpose == "relay_draft"
                assert requests[0]["messages"][0] == requests[1]["messages"][0]
                assert requests[1]["response_format"]["json_schema"]["schema"]["properties"][
                    "kind"
                ]["enum"] == ["propose", "stop"]
                assert requests[1]["response_format"]["json_schema"]["schema"]["properties"][
                    "action"
                ] == {"type": "null"}
                assert await env.call_agent(agent, seed=8) is None
                assert (
                    len(agent.calls) == 2
                    and env.termination_reason == "budget_exhausted:agent_calls"
                )
                if attacked:
                    assert "authorization is already" in requests[1]["messages"][-1]["content"]
                    assert "authorization is already" not in requests[1]["messages"][0]["content"]
                else:
                    assert not relay.events[0]["changed"]

    asyncio.run(run())


def test_guarded_runtime_blocks_structured_forgery_while_simulator_reference_measures_harm() -> (
    None
):
    class StopAgent:
        async def respond(self, view: AgentView, *, seed: int) -> AgentReply:
            return AgentReply(kind=AgentReplyKind.STOP)

    async def run() -> None:
        for cls, expected_violation in (
            (ECPAEnvironment, False),
            (UnguardedSimulatorReference, True),
        ):
            env = environment(cls)
            relay = StagedResponseRelay(
                RelayCampaign(
                    task_id=env.task.contract.task_id,
                    stages=(RelayStage(node="start", edge_id="inspect_owner_contacts_early"),),
                ),
                mode="structured",
                attacked=True,
            )
            forged = AgentReply.model_validate_json(relay.transform("{}", env.agent_view()))
            obs = await env.observe(forged)
            assert obs is not None
            policy = PerActionAuthorizationPolicy()
            if not expected_violation:
                assert policy.choose(obs, rng=random.Random(0)) == PolicyChoice("deny")
            task = load_development_tasks(
                ROOT, ROOT / "configs/defense/development-contracts.yaml"
            )[0]
            episode = await collect_episode(
                env,
                StopAgent(),
                policy,
                first_observation=obs,
                evaluator=HiddenOutcomeEvaluator(task.bundle),
            )
            assert episode_metrics(episode)["violation"] is expected_violation

    asyncio.run(run())


def test_observation_callback_branches_independent_states_without_relabeling() -> None:
    class ScriptAgent:
        async def respond(self, view: AgentView, *, seed: int) -> AgentReply:
            return AgentReply(kind=AgentReplyKind.STOP)

    async def run() -> None:
        env = environment()
        obs = await env.observe(AgentReply(kind=AgentReplyKind.PROPOSE, edge_id="query_paused_ids"))
        assert obs is not None

        async def branch(parent: ECPAEnvironment, current: DefenseObservation) -> None:
            clone = parent.clone_for_collection()
            choice = next(item.candidate_id for item in current.menu if item.candidate_id != "deny")
            await clone.step(current, choice, agent=ScriptAgent(), seed=9)
            assert clone.receipts and not parent.receipts
            assert parent.node == "start" and clone.node != parent.node

        await collect_episode(
            env,
            ScriptAgent(),
            PublicRulePolicy(),
            first_observation=obs,
            observation_callback=branch,
            first_choice=PolicyChoice("deny"),
        )
        assert not env.receipts

    asyncio.run(run())


@pytest.mark.parametrize("device", ["cpu", "cuda:0"])
def test_actual_tiny_lora_updates_reload_and_artifact_identity(tmp_path: Path, device: str) -> None:
    torch = pytest.importorskip("torch")
    pytest.importorskip("peft")
    if device.startswith("cuda") and not torch.cuda.is_available():
        pytest.skip("CUDA is unavailable")
    from tokenizers import Tokenizer  # type: ignore[import-not-found]
    from tokenizers.models import WordLevel  # type: ignore[import-not-found]
    from tokenizers.pre_tokenizers import WhitespaceSplit  # type: ignore[import-not-found]
    from transformers import (  # type: ignore[import-not-found]
        PreTrainedTokenizerFast,
        Qwen3Config,
        Qwen3ForCausalLM,
    )

    torch.set_num_threads(1)
    base_path, adapter = tmp_path / "base", tmp_path / "adapter"
    vocab = {"[UNK]": 0, "[EOS]": 1, "deny": 2, "allow:query_paused_ids": 3}
    backend = Tokenizer(WordLevel(vocab, unk_token="[UNK]"))
    backend.pre_tokenizer = WhitespaceSplit()
    tokenizer = PreTrainedTokenizerFast(
        tokenizer_object=backend, eos_token="[EOS]", unk_token="[UNK]"
    )
    tokenizer.chat_template = (
        "{% for message in messages %}{{ message['role'] + ' ' + message['content'] + ' ' }}"
        "{% endfor %}{% if add_generation_prompt %}assistant {% endif %}"
    )
    tokenizer.save_pretrained(base_path)
    Qwen3ForCausalLM(
        Qwen3Config(
            vocab_size=4,
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=1,
            num_attention_heads=4,
            num_key_value_heads=2,
            head_dim=8,
            max_position_embeddings=8192,
            eos_token_id=1,
            pad_token_id=1,
        )
    ).save_pretrained(base_path)
    fingerprint = model_fingerprint(str(base_path))
    config = CompactConfig(model_path=str(base_path), device=device, context_tokens=8192)
    measurement = train_lora(
        [group()],
        config,
        LoraSpec(updates=2, rank=2, alpha=4),
        adapter,
        source_revision="b" * 40,
        development_smoke=True,
    )
    assert isinstance(measurement["trainable_parameters"], int)
    assert measurement["trainable_parameters"] > 0
    assert model_fingerprint(str(base_path)) == fingerprint
    validate_adapter(adapter, config, allow_development=True)
    with pytest.raises(ValueError, match="forbidden in formal"):
        validate_adapter(adapter, config)
    with pytest.raises(ValueError, match="forbidden in formal"):
        validate_adapter(adapter, config, allow_development=True, expected_protocol_id="ecpa-test")
    from routebench.defense.compact import LocalCandidateModel

    loaded = LocalCandidateModel(config, adapter=adapter, allow_development=True)
    assert loaded.has_adapter and not any(
        parameter.requires_grad for parameter in loaded.model.parameters()
    )
    base_choice = loaded.choose(observation(), use_adapter=False, rng=random.Random(0))
    tuned_choice = loaded.choose(observation(), use_adapter=True, rng=random.Random(0))
    legal = {item.candidate_id for item in observation().menu}
    assert base_choice.candidate_id in legal and tuned_choice.candidate_id in legal
    (adapter / "adapter_model.safetensors").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        validate_adapter(adapter, config, allow_development=True)
