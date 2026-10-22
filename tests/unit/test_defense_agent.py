from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from routebench.defense.agent import JsonRecoveryAgent, RecoveryAgentConfig
from routebench.defense.ecpa import AgentResponseError


def test_json_agent_records_actual_tokens_and_separates_no_raw_output() -> None:
    from pathlib import Path

    from routebench.defense.development import load_development_tasks
    from routebench.defense.ecpa import ECPAEnvironment
    from routebench.runtime.reference import ScenarioState

    root = Path(__file__).parents[2]
    task = load_development_tasks(root, root / "configs/defense/development-contracts.yaml")[0]
    environment = ECPAEnvironment(
        task.public, ScenarioState.from_fixture(task.bundle.root / "fixtures/state.json")
    )

    async def run() -> None:
        response = httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"kind":"propose","edge_id":"query_paused_ids"}'},
                    }
                ],
                "usage": {"prompt_tokens": 42, "completion_tokens": 7},
            },
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: response)
        ) as client:
            agent = JsonRecoveryAgent(RecoveryAgentConfig(), client=client)
            reply = await agent.respond(environment.agent_view(), seed=9)
            assert reply.edge_id == "query_paused_ids"
            assert agent.calls[0].prompt_tokens == 42
            assert agent.calls[0].completion_tokens == 7
            assert "content" not in agent.calls[0].model_dump()

    asyncio.run(run())


def test_agent_schema_keeps_all_current_edges_without_recommending_safe_route() -> None:
    from routebench.defense.development import load_development_tasks
    from routebench.defense.ecpa import ECPAEnvironment
    from routebench.runtime.reference import ScenarioState

    root = Path(__file__).parents[2]
    task = load_development_tasks(root, root / "configs/defense/development-contracts.yaml")[0]
    env = ECPAEnvironment(
        task.public, ScenarioState.from_fixture(task.bundle.root / "fixtures/state.json")
    )
    requests: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        properties = body["response_format"]["json_schema"]["schema"]["properties"]
        node = json.loads(body["messages"][1]["content"])["node"]
        expected = {edge.edge_id for edge in task.public.graph.edges if edge.source == node}
        assert set(properties["edge_id"]["enum"]) == {None, *expected}
        assert properties["kind"]["enum"] == ["propose", "stop"]
        assert properties["action"] == properties["request_hash"] == {"type": "null"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"kind":"stop"}'}}
                ]
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            agent = JsonRecoveryAgent(RecoveryAgentConfig(), client=client)
            await agent.respond(env.agent_view(), seed=3)
            # Replanning after two real actions must not offer a later-node edge.
            env.node = "inventory_staged"
            await agent.respond(env.agent_view(), seed=4)

    asyncio.run(run())
    assert len(requests) == 2
    properties = requests[1]["response_format"]
    assert "inspect_contacts_after_staging" in str(properties)
    assert "query_paused_ids" not in str(properties)


@pytest.mark.parametrize(
    "body",
    [
        {"choices": []},
        {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": "bad json"}}]},
    ],
)
def test_malformed_or_truncated_responses_are_recorded_failures(body: dict[str, object]) -> None:
    from pathlib import Path

    from routebench.defense.development import load_development_tasks
    from routebench.defense.ecpa import ECPAEnvironment
    from routebench.runtime.reference import ScenarioState

    root = Path(__file__).parents[2]
    task = load_development_tasks(root, root / "configs/defense/development-contracts.yaml")[0]
    environment = ECPAEnvironment(
        task.public, ScenarioState.from_fixture(task.bundle.root / "fixtures/state.json")
    )

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))
        ) as client:
            agent = JsonRecoveryAgent(RecoveryAgentConfig(), client=client)
            with pytest.raises(AgentResponseError):
                await agent.respond(environment.agent_view(), seed=3)
            assert len(agent.calls) == 1 and agent.calls[0].status == "invalid_response"

    asyncio.run(run())
