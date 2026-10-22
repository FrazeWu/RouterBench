from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path

import httpx
import pytest

from routebench.defense.agent import JsonRecoveryAgent, RecoveryAgentConfig
from routebench.defense.branching import collect_parent_branches
from routebench.defense.collect import OutcomeLabel
from routebench.defense.corpus import load_corpus
from routebench.defense.development import SimulatedApprover
from routebench.defense.ecpa import AgentReply, AgentReplyKind, AgentView, ECPAEnvironment
from routebench.defense.policies import MixtureLoggingPolicy
from routebench.defense.relay import RelayCampaign, RelayStage, StagedResponseRelay
from routebench.runtime.reference import ScenarioState

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("cutoff", [None, 1])
def test_real_http_agent_branches_keep_snapshots_seeds_probabilities_and_censoring(
    cutoff: int | None,
) -> None:
    # Mock HTTP is a deterministic transport fixture, not experimental model data.
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    task = tasks[0]
    edges = {edge.edge_id: edge for edge in task.public.graph.edges}
    path = {edges[edge_id].source: edge_id for edge_id in task.authoring.safe_paths[0]}
    agents: list[JsonRecoveryAgent] = []
    requests = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        body = json.loads(request.content)
        if body["model"] == "broken-branch-fixture":
            return httpx.Response(200, json={"choices": []})
        view = AgentView.model_validate_json(body["messages"][1]["content"])
        if view.offer is not None:
            reply = AgentReply(kind=AgentReplyKind.REJECT)
        elif set(task.public.contract.goal_all) <= set(view.facts):
            reply = AgentReply(kind=AgentReplyKind.STOP)
        else:
            reply = AgentReply(kind=AgentReplyKind.PROPOSE, edge_id=path.get(view.node))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": reply.model_dump_json()},
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

            def factory(relay: StagedResponseRelay) -> JsonRecoveryAgent:
                config = RecoveryAgentConfig()
                if cutoff is None and len(agents) == 1:
                    config = config.model_copy(update={"model": "broken-branch-fixture"})
                agent = JsonRecoveryAgent(config, client=client, relay=relay)
                agents.append(agent)
                return agent

            # The second stage requests a fabricated write so exact-offer rejection
            # is exercised. Later stages cannot be replayed as fresh earlier stages.
            relay = StagedResponseRelay(
                RelayCampaign(
                    task_id=task.entry.task_id,
                    stages=(
                        RelayStage(node="start", edge_id="inspect_settlement"),
                        RelayStage(node="observed", edge_id="save_fabricated_evidence"),
                    ),
                ),
                mode="structured",
                attacked=True,
            )
            env = ECPAEnvironment(task.public, task.state(), approval_provider=SimulatedApprover())
            evaluated = 0

            def evaluator(state: ScenarioState) -> OutcomeLabel:
                nonlocal evaluated
                evaluated += 1
                # A transient evaluator finding must survive branch restoration,
                # even when all later simulator states appear violation-free.
                return task.outcome(state).model_copy(
                    update={
                        "violation": evaluated == 1,
                        "attack_success": evaluated == 1,
                    }
                )

            result = await collect_parent_branches(
                env,
                relay,
                factory,
                MixtureLoggingPolicy(uniform_weight=0.0 if cutoff is None else 0.5),
                evaluator=evaluator,
                seed=9,
                state_selection_seed=17,
                continuation_seed=100,
                maximum_states=2,
                repeats=2,
                proposal_sampling_probability=0.25,
                max_collection_steps=cutoff,
            )
            assert result.encountered_choice_states > 0
            assert len(result.comparisons) == min(2, result.encountered_choice_states)
            expected_indices = sorted(
                random.Random(17).sample(
                    range(result.encountered_choice_states), len(result.comparisons)
                )
            )
            assert [row.encountered_index for row in result.comparisons] == expected_indices
            assert len({id(agent.relay) for agent in agents}) == len(agents)
            assert requests == sum(len(agent.calls) for agent in agents)
            assert len(result.parent.calls) == len(agents[0].calls)
            if cutoff is None:
                assert result.encountered_choice_states > 2
                assert expected_indices != [0, 1]
                assert any(step.acceptance == "rejected" for step in result.parent.episode.steps)
                assert any(
                    branch.outcome.termination_reason == "agent_response_error"
                    for comparison in result.comparisons
                    for branch in comparison.branches
                )
            for comparison in result.comparisons:
                assert comparison.branch_assignment_probability == 1
                assert comparison.state_inclusion_probability == min(
                    1, 2 / result.encountered_choice_states
                )
                menu = {candidate.candidate_id for candidate in comparison.observation.menu}
                assert len(comparison.branches) == 2 * len(menu)
                for repeat in range(2):
                    branches = [
                        branch for branch in comparison.branches if branch.outcome.repeat == repeat
                    ]
                    assert {branch.outcome.candidate_id for branch in branches} == menu
                    assert {branch.outcome.continuation_seed for branch in branches} == {
                        100 + repeat
                    }
                    for branch in branches:
                        episode = branch.rollout.episode
                        assert episode.proposal_sampling_probability == 0.25
                        assert episode.intervention_probabilities[0] == 1
                        assert all(
                            0 < probability <= 1
                            for probability in episode.intervention_probabilities
                        )
                        assert episode.final_outcome is not None
                        assert episode.final_outcome.violation
                        assert episode.final_outcome.attack_success
                        assert episode.steps[0].observation == comparison.observation
                        assert episode.steps[0].selected.candidate_id == branch.outcome.candidate_id
                        event_nodes = [event["node"] for event in branch.rollout.relay_events]
                        assert len(set(event_nodes)) == len(event_nodes)
                        if cutoff == 1:
                            assert episode.truncated and branch.outcome.safe_completion is None
                            assert branch.outcome.cost is None
                        elif episode.terminated:
                            assert branch.outcome.violation
                            assert branch.outcome.safe_completion is False
                            assert branch.outcome.cost is not None
            # No sibling branch added decisions to the completed parent.
            assert len(env.history) == len(result.parent.episode.steps)

    asyncio.run(run())
