"""Transport/simulator fixtures only: no model inference or research labels."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from routebench.defense.agent import JsonRecoveryAgent, RecoveryAgentConfig
from routebench.defense.compact import ContextOverflow
from routebench.defense.contracts import content_hash
from routebench.defense.corpus import load_corpus, replay_prefix
from routebench.defense.ecpa import (
    AgentReply,
    AgentReplyKind,
    AgentResponseError,
    AgentView,
    ECPAEnvironment,
)
from routebench.defense.freeze import StudySpec
from routebench.defense.lora import BranchGroup, BranchOutcome, file_digest
from routebench.defense.protocol import AcquisitionLedger
from routebench.defense.relay import StagedResponseRelay
from routebench.defense.study import (
    FrozenStudy,
    MeteredStudyAgent,
    collect_training,
    load_training_collection,
    load_training_phase,
    private_output,
    training_coverage,
    write_exclusive,
)
from scripts.run_defense_study import server_address, server_command

ROOT = Path(__file__).parents[2]


def fixture_study() -> FrozenStudy:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    spec = StudySpec.model_validate(
        {
            "purpose": "ecpa_independent_formal_study",
            "corpus_manifest": "configs/defense/independent-corpus.yaml",
            "agent": {"context_tokens": 8192, "max_completion_tokens": 768},
            "task_model_path": "/TEST/NOT-A-MODEL/agent",
            "compact": {"model_path": "/TEST/NOT-A-MODEL/defender", "device": "cuda:0"},
            "lora": {
                "seed": 29,
                "updates": 16,
                "gradient_accumulation": 1,
                "learning_rate": 0.0001,
                "rank": 8,
                "alpha": 16,
                "dropout": 0.0,
                "target_modules": ["q_proj", "v_proj"],
            },
            "budgets": {"decisions": 6, "agent_calls": 24},
            "comparison": {},
            "adapter_seeds": [29, 31, 37],
            "presentations": 1,
            "episode_seed": 43,
            "arm_order_seed": 47,
            "state_selection_seed": 53,
            "continuation_seed": 59,
            "maximum_branch_states_per_parent": 1,
            "branch_repeats": 1,
            "modes": ["text", "structured"],
            "logging_uniform_weight": 0.0,
            "acquisition_call_limit": 100,
            "acquisition_token_limit": 1000000,
            "resources": {
                "gpu_ids": [0, 1],
                "task_agent_gpu": 1,
                "maximum_celsius": 85,
                "minimum_request_gap_seconds": 2,
                "cooling_pause_celsius": 73,
                "cooling_resume_celsius": 71,
                "maximum_cooling_wait_seconds": 300,
            },
            "training_acquisition": "enumerate_each_train_task_transport_condition_once",
            "required_training_target_kinds": ["allow", "constrain", "escalate", "deny"],
            "comparator_selection": (
                "lowest_violations_then_highest_safe_completion_then_cost_on_tune"
            ),
            "checkpoint_selection": "single_prespecified_update_count",
            "precision_interpretation": "retain_criteria_report_inconclusive",
            "structured_mechanism_claim": "shared_proposal_substitution_no_holdout",
        }
    )
    return FrozenStudy("ecpa-test-fixture", "a" * 40, spec, tasks, "b" * 64)


class TokenizerFixture:
    def __init__(self, length: int = 20):
        self.length = length

    def apply_chat_template(self, messages: object, **kwargs: object) -> list[int]:
        return [1] * self.length


@pytest.mark.parametrize("usage", [None, {"prompt_tokens": 30, "completion_tokens": 5}])
def test_metered_text_draft_receiver_acceptance_and_hard_cap(usage: dict[str, int] | None) -> None:
    study = fixture_study()
    task = study.tasks[0]
    env = ECPAEnvironment(task.public, task.state())
    ledger = AcquisitionLedger(3, 30000)
    records: list[dict[str, object]] = []
    sent = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        body: dict[str, Any] = {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"kind":"stop"}'}}]
        }
        if usage is not None:
            body["usage"] = usage
        return httpx.Response(200, json=body)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            agent = MeteredStudyAgent(
                study.spec.agent,
                tokenizer=TokenizerFixture(),
                ledger=ledger,
                acquisition_purpose="branch",
                before_call=lambda: None,
                after_call=lambda: None,
                record_call=records.append,
                client=client,
                text_receiver=True,
            )
            await agent.respond(env.agent_view(), seed=3)
            assert len(agent.calls) == 2  # actual draft and receiving call
            observation = await env.observe(
                AgentReply(
                    kind=AgentReplyKind.PROPOSE, edge_id=task.authoring.menu_probes[0].proposal
                )
            )
            assert observation is not None
            agent.text_receiver = False
            await agent.respond(env.agent_view(observation.menu[0]), seed=4)
            assert agent.calls[-1].purpose == "acceptance"
            with pytest.raises(RuntimeError, match="call budget"):
                await agent.respond(env.agent_view(), seed=5)

    asyncio.run(run())
    assert sent == len(records) == ledger.calls["branch"] == 3
    assert ledger.tokens["branch"] == 3 * (35 if usage is not None else 8192)
    assert not ledger._pending


@pytest.mark.parametrize(
    "failure", ["transport", "malformed", "excess_usage", "context", "thermal"]
)
def test_metered_failures_are_charged_or_stopped_before_http(failure: str) -> None:
    study = fixture_study()
    task = study.tasks[0]
    ledger = AcquisitionLedger(2, 20000)
    records: list[dict[str, object]] = []
    sent = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        if failure == "transport":
            raise httpx.ReadTimeout("fixture timeout", request=request)
        body: dict[str, Any] = {"choices": []}
        if failure == "excess_usage":
            body = {
                "choices": [{"finish_reason": "stop", "message": {"content": '{"kind":"stop"}'}}],
                "usage": {"prompt_tokens": 9000, "completion_tokens": 2},
            }
        return httpx.Response(200, json=body)

    def before() -> None:
        if failure == "thermal":
            raise RuntimeError("TEST thermal stop")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            agent = MeteredStudyAgent(
                study.spec.agent,
                tokenizer=TokenizerFixture(9000 if failure == "context" else 20),
                ledger=ledger,
                acquisition_purpose="rollout",
                before_call=before,
                after_call=lambda: None,
                record_call=records.append,
                client=client,
            )
            expected = {
                "transport": AgentResponseError,
                "malformed": AgentResponseError,
                "excess_usage": ValueError,
                "context": ContextOverflow,
                "thermal": RuntimeError,
            }[failure]
            with pytest.raises(expected):
                await agent.respond(ECPAEnvironment(task.public, task.state()).agent_view(), seed=3)

    asyncio.run(run())
    assert sent == len(records) == (0 if failure in {"context", "thermal"} else 1)
    assert sum(ledger.tokens.values()) == sent * 8192
    assert not ledger._pending


def test_collection_uses_only_train_preserves_raw_rollouts_and_does_not_invent_coverage(
    tmp_path: Path,
) -> None:
    study = fixture_study()
    train = study.tasks[0]
    heldout = next(task for task in study.tasks if task.entry.split == "test")
    study = replace(study, tasks=(train, heldout))
    edges = {edge.edge_id: edge for edge in train.public.graph.edges}
    safe_path = {edges[edge].source: edge for edge in train.authoring.safe_paths[0]}
    factories = 0

    def respond(request: httpx.Request) -> httpx.Response:
        view = AgentView.model_validate_json(json.loads(request.content)["messages"][1]["content"])
        assert view.task.contract.task_id == train.entry.task_id
        if view.offer:
            reply = AgentReply(
                kind=AgentReplyKind.ACCEPT,
                edge_id=view.offer.edge_id,
                action=view.offer.action,
                request_hash=view.offer.request_hash,
            )
        elif set(view.task.contract.goal_all) <= set(view.facts):
            reply = AgentReply(kind=AgentReplyKind.STOP)
        else:
            reply = AgentReply(kind=AgentReplyKind.PROPOSE, edge_id=safe_path.get(view.node))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": reply.model_dump_json()}}
                ],
                "usage": {"prompt_tokens": 25, "completion_tokens": 5},
            },
        )

    async def run() -> dict[str, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

            def factory(purpose: str, relay: StagedResponseRelay) -> JsonRecoveryAgent:
                nonlocal factories
                factories += 1
                assert purpose in {"rollout", "branch"}
                return JsonRecoveryAgent(
                    study.spec.agent, client=client, relay=relay, text_receiver=relay.mode == "text"
                )

            return await collect_training(study, tmp_path / "collection", factory)

    report = asyncio.run(run())
    assert report["status"] == "complete" and report["efficacy_evidence"] is False
    assert len(report["cases"]) == 4  # type: ignore[arg-type]
    rows = list((tmp_path / "collection").glob("*.rollout.private.json"))
    assert len(rows) == factories > 4
    assert (tmp_path / "collection/collection.json").exists()
    for path in rows:
        raw = json.loads(path.read_text())
        assert raw["task_id"] == train.entry.task_id
        assert len(raw["relay_events"]) <= len(train.authoring.attack_path)
        if raw["rollout_key"] != "parent":
            assert raw["inherited_relay_events"]
            assert not {event["node"] for event in raw["relay_events"]}.intersection(
                event["node"] for event in raw["inherited_relay_events"]
            )
    with pytest.raises(ValueError, match="lack a prespecified kind"):
        load_training_collection(tmp_path / "collection", study)
    with pytest.raises(FileExistsError):
        asyncio.run(run())
    first = rows[0]
    first.write_text("tampered TEST data")
    with pytest.raises(ValueError, match="artifact integrity"):
        load_training_collection(tmp_path / "collection", study)


def test_realized_target_coverage_and_dedup_use_outcomes_without_test_data() -> None:
    study = fixture_study()
    groups: list[BranchGroup] = []

    async def prepare() -> None:
        # Counterfactual labels below are explicit TEST fixtures; public menus
        # are obtained from actual simulator states, not fabricated candidates.
        for kind in study.spec.required_training_target_kinds:
            task, probe = next(
                (task, probe)
                for task in study.tasks
                if task.entry.split == "train"
                for probe in task.authoring.menu_probes
                if probe.expected_kind.value == kind
            )
            env = await replay_prefix(task, probe.prefix)
            obs = await env.observe(AgentReply(kind=AgentReplyKind.PROPOSE, edge_id=probe.proposal))
            assert obs is not None
            target = next(item for item in obs.menu if item.kind.value == kind)
            groups.append(
                BranchGroup(
                    group_id=f"TEST-{kind}",
                    observation=obs,
                    semantic_family=task.entry.semantic_family,
                    attack_mechanism="TEST-FIXTURE",
                    split="train",
                    source_revision=study.revision,
                    formal_protocol_id=study.protocol_id,
                    proposal_sampling_probability=1.0,
                    outcomes=tuple(
                        BranchOutcome(
                            candidate_id=item.candidate_id,
                            repeat=0,
                            continuation_seed=19,
                            terminated=True,
                            truncated=False,
                            safe_completion=item == target,
                            violation=item != target,
                            cost=1,
                            termination_reason="agent_stop",
                        )
                        for item in obs.menu
                    ),
                )
            )

    asyncio.run(prepare())
    chosen, audit = training_coverage(groups, study)
    assert len(chosen) == 4 and audit["fit_ready"] is True
    assert audit["realized_target_kind_counts"] == dict.fromkeys(
        study.spec.required_training_target_kinds, 1
    )
    duplicate = groups[0].model_copy(update={"group_id": "TEST-renamed-duplicate"})
    chosen, audit = training_coverage([*groups, duplicate], study)
    assert len(chosen) == 4 and audit["duplicate_group_ids"] == [duplicate.group_id]
    with pytest.raises(ValueError, match="only training"):
        training_coverage([groups[0].model_copy(update={"split": "test"})], study)
    censored = groups[0].model_copy(
        update={
            "outcomes": tuple(
                row.model_copy(update={"truncated": True, "terminated": False})
                for row in groups[0].outcomes
            )
        }
    )
    _, audit = training_coverage([censored, *groups[1:]], study)
    assert audit["fit_ready"] is False and audit["skipped"] == 1


def test_phase_completion_private_paths_exclusive_output_and_owned_server_binding(
    tmp_path: Path,
) -> None:
    study = fixture_study()
    output = tmp_path / "artifacts/private/run"
    assert private_output(tmp_path, output) == output
    with pytest.raises(ValueError, match="artifacts/private"):
        private_output(tmp_path, tmp_path / "public")
    write_exclusive(output / "record.json", {"TEST": True})
    with pytest.raises(FileExistsError):
        write_exclusive(output / "record.json", {"TEST": False})
    write_exclusive(output / "phase-result.json", {"phase": "collect", "status": "aborted"})
    with pytest.raises(ValueError, match="thermally valid"):
        load_training_phase(output / "collection", study)
    command = server_command(study)
    assert command[command.index("--model") + 1] == study.spec.task_model_path
    assert command[command.index("--max-model-len") + 1] == "8192"
    assert server_address(study.spec) == ("127.0.0.1", 8011)
    unsafe = study.spec.model_copy(
        update={"agent": RecoveryAgentConfig(endpoint="http://example.com/v1")}
    )
    with pytest.raises(ValueError, match=r"127\.0\.0\.1"):
        server_address(unsafe)


def test_complete_source_bound_training_fixture_loads_and_rejects_missing_branches(
    tmp_path: Path,
) -> None:
    """Invented TEST outcomes exercise provenance only; never research labels."""
    study = fixture_study()
    chosen = []
    used = set()
    for kind in study.spec.required_training_target_kinds:
        task, probe = next(
            (task, probe)
            for task in study.tasks
            if task.entry.split == "train" and task.entry.task_id not in used
            for probe in task.authoring.menu_probes
            if probe.expected_kind.value == kind
        )
        used.add(task.entry.task_id)
        chosen.append((task, probe, kind))
    study = replace(study, tasks=tuple(task for task, _, _ in chosen))
    directory = tmp_path / "phase/collection"
    directory.mkdir(parents=True)
    groups: list[BranchGroup] = []
    cases: list[dict[str, Any]] = []

    async def build() -> None:
        for task, probe, kind in chosen:
            for mode in study.spec.modes:
                for attacked in (False, True):
                    index = len(cases)
                    identity = {"task_id": task.entry.task_id, "mode": mode, "attacked": attacked}
                    case_id = "case-" + content_hash(identity)[:20]
                    env = await replay_prefix(task, probe.prefix)
                    obs = await env.observe(
                        AgentReply(kind=AgentReplyKind.PROPOSE, edge_id=probe.proposal)
                    )
                    assert obs is not None
                    target = next(item for item in obs.menu if item.kind.value == kind)
                    mechanism = (
                        (
                            "registered_proposal_substitution"
                            if mode == "structured"
                            else task.entry.attack_mechanism
                        )
                        if attacked
                        else "benign"
                    )
                    group = BranchGroup(
                        group_id=f"{case_id}-state-0",
                        observation=obs,
                        semantic_family=task.entry.semantic_family,
                        attack_mechanism=mechanism,
                        split="train",
                        source_revision=study.revision,
                        formal_protocol_id=study.protocol_id,
                        proposal_sampling_probability=1.0,
                        outcomes=tuple(
                            BranchOutcome(
                                candidate_id=item.candidate_id,
                                repeat=0,
                                continuation_seed=study.spec.continuation_seed + index,
                                terminated=True,
                                truncated=False,
                                safe_completion=item == target,
                                violation=item != target,
                                cost=1,
                                termination_reason="agent_stop",
                            )
                            for item in obs.menu
                        ),
                    )
                    name = f"{group.group_id}.group.private.json"
                    write_exclusive(directory / name, group.model_dump(mode="json"))
                    groups.append(group)
                    cases.append(
                        {
                            **identity,
                            "case_id": case_id,
                            "groups": [name],
                            "encountered_choice_states": 1,
                            "task_source_digest": task.digest,
                        }
                    )

    asyncio.run(build())
    selected, coverage = training_coverage(groups, study)
    assert coverage["fit_ready"] is True
    report = {
        "purpose": "formal_train_collection",
        "status": "complete",
        "source_revision": study.revision,
        "formal_protocol_id": study.protocol_id,
        "frozen_manifest_digest": study.manifest_digest,
        "training_acquisition": study.spec.training_acquisition,
        "cases": cases,
        "coverage": coverage,
        "selected_group_ids": [group.group_id for group in selected],
        "files": {path.name: file_digest(path) for path in directory.iterdir()},
    }
    write_exclusive(directory / "collection.json", report)
    phase: dict[str, Any] = {
        "phase": "collect",
        "status": "complete",
        "error_kind": None,
        "source_revision": study.revision,
        "formal_protocol_id": study.protocol_id,
        "collection_files": {path.name: file_digest(path) for path in directory.iterdir()},
    }
    write_exclusive(directory.parent / "phase-result.json", phase)
    assert load_training_phase(directory, study) == selected
    group_path = directory / cases[0]["groups"][0]
    changed = json.loads(group_path.read_text())
    changed["outcomes"].pop()
    group_path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="phase file integrity"):
        load_training_phase(directory, study)
    # Even a newly hashed malformed fixture cannot omit a candidate branch.
    report["files"][group_path.name] = file_digest(group_path)  # type: ignore[index]
    (directory / "collection.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="menu/repeat schedule"):
        load_training_collection(directory, study)
