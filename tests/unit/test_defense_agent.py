from __future__ import annotations

import asyncio

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
