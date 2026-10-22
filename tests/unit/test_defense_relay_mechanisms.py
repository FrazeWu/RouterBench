from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from routebench.defense.agent import JsonRecoveryAgent, RecoveryAgentConfig
from routebench.defense.corpus import load_corpus, replay_prefix
from routebench.defense.ecpa import (
    AgentReply,
    AgentReplyKind,
    DefenseCandidate,
    DefenseDecisionKind,
)
from routebench.defense.relay import RelayCampaign, RelayMechanism, RelayStage, StagedResponseRelay

ROOT = Path(__file__).parents[2]
MECHANISMS: tuple[RelayMechanism, ...] = (
    "authorization_pretext",
    "appended_completion_directive",
    "forged_observation_envelope",
)


@pytest.mark.parametrize("mechanism", MECHANISMS)
def test_text_operators_change_only_untrusted_draft_and_preserve_benign_bytes(
    mechanism: RelayMechanism,
) -> None:
    async def run() -> None:
        _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
        task = tasks[-1]
        env = await replay_prefix(task, task.authoring.attack_path[:-1])
        view = env.agent_view()
        before = view.model_dump_json()
        edge_id = task.authoring.attack_path[-1]
        campaign = RelayCampaign(
            task_id=task.entry.task_id,
            stages=(RelayStage(node=view.node, edge_id=edge_id),),
            mechanism=mechanism,
        )
        draft = '  {"kind":"stop"}\nDRAFT_SENTINEL'
        benign = StagedResponseRelay(campaign, mode="text", attacked=False)
        assert benign.transform(draft, view) == draft
        assert not benign.events[0]["changed"]
        relay = StagedResponseRelay(campaign, mode="text", attacked=True)
        replacement = relay.transform(draft, view)
        assert replacement != draft and edge_id in replacement
        assert view.model_dump_json() == before
        assert relay.transform("later response", view) == "later response"
        assert len(relay.events) == 1
        assert relay.events[0]["effective_mechanism"] == mechanism
        if mechanism == "appended_completion_directive":
            assert replacement.startswith(draft + "\n\n")
        elif mechanism == "forged_observation_envelope":
            spoof = json.loads(replacement)
            assert spoof["role"] == "tool"
            assert spoof["tool_result"]["required_next_edge"] == edge_id
            assert spoof["tool_result"]["observed_facts"] == list(
                task.public.contract.actions[edge_id].requires
            )
        offered = view.model_copy(
            update={"offer": DefenseCandidate(candidate_id="deny", kind=DefenseDecisionKind.DENY)}
        )
        untouched = StagedResponseRelay(campaign, mode="text", attacked=True)
        assert untouched.transform(draft, offered) == draft and untouched.events == []

    asyncio.run(run())


def test_structured_transport_cannot_claim_text_operator_holdout() -> None:
    async def run() -> None:
        _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
        task = tasks[-1]
        env = await replay_prefix(task, ())
        stage = task.relay_campaign().stages[:1]
        results = []
        for mechanism in MECHANISMS:
            relay = StagedResponseRelay(
                RelayCampaign(task_id=task.entry.task_id, stages=stage, mechanism=mechanism),
                mode="structured",
                attacked=True,
            )
            result = relay.transform("original", env.agent_view())
            assert AgentReply.model_validate_json(result).edge_id == stage[0].edge_id
            assert relay.effective_mechanism == "registered_proposal_substitution"
            assert relay.events[0]["effective_mechanism"] == relay.effective_mechanism
            results.append(result)
        assert len(set(results)) == 1

    asyncio.run(run())


@pytest.mark.parametrize("mechanism", MECHANISMS)
def test_http_receiver_never_promotes_spoofed_roles_or_facts(mechanism: RelayMechanism) -> None:
    async def run() -> None:
        _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
        task = tasks[-1]
        env = await replay_prefix(task, task.authoring.attack_path[:-1])
        view = env.agent_view()
        before = view.model_dump_json()
        requests: list[dict[str, Any]] = []

        def response(request: httpx.Request) -> httpx.Response:
            requests.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": '{"kind":"stop"}'}}
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
            )

        relay = StagedResponseRelay(
            task.relay_campaign().model_copy(update={"mechanism": mechanism}),
            mode="text",
            attacked=True,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            agent = JsonRecoveryAgent(
                RecoveryAgentConfig(), client=client, relay=relay, text_receiver=True
            )
            reply = await agent.respond(view, seed=11)
        assert reply.kind is AgentReplyKind.STOP
        assert len(agent.calls) == len(requests) == 2
        assert requests[0]["messages"][:2] == requests[1]["messages"][:2]
        assert [message["role"] for message in requests[1]["messages"]] == [
            "system",
            "user",
            "user",
        ]
        assert task.authoring.attack_path[-1] in requests[1]["messages"][-1]["content"]
        assert view.model_dump_json() == before

    asyncio.run(run())


def test_corpus_campaign_binds_actual_operator_and_rejects_unregistered_labels() -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    for task in tasks:
        campaign = task.relay_campaign()
        assert campaign.mechanism == task.entry.attack_mechanism
        assert tuple(stage.edge_id for stage in campaign.stages) == task.authoring.attack_path
    with pytest.raises(ValueError):
        RelayCampaign.model_validate({"task_id": "x", "stages": [], "mechanism": "renamed_only"})
