"""Relational source checks use actual simulator effects, without model inference."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from routebench.contracts import ActionRequest
from routebench.defense.collect import collect_episode
from routebench.defense.corpus import CorpusTask, load_corpus
from routebench.defense.ecpa import AgentReply, AgentReplyKind, AgentView
from routebench.defense.evaluation import episode_metrics
from routebench.defense.pilot import UnguardedSimulatorReference
from routebench.defense.policies import PerActionAuthorizationPolicy
from routebench.evaluation.verifiers import evaluate_assertion
from routebench.runtime.reference import ScenarioState, TrustedToolExecutor
from routebench.scenarios.schema import AssertionSpec

ROOT = Path(__file__).parents[2]


def task_named(name: str) -> CorpusTask:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    return next(task for task in tasks if task.entry.task_id == name)


def execute(task: CorpusTask, state: ScenarioState, edge_id: str) -> None:
    action = next(edge.action for edge in task.public.graph.edges if edge.edge_id == edge_id)
    TrustedToolExecutor().execute(
        ActionRequest(
            action_id=edge_id,
            step=len(state.executed_actions),
            tool=action.tool,
            arguments=action.arguments,
        ),
        state,
    )


def test_identical_next_hop_change_depends_on_preceding_forwarding_state() -> None:
    task = task_named("ecpa_test_acyclic_forwarding")
    state = task.state()
    assert not task.outcome(state).violation
    execute(task, state, "close_cycle")
    assert task.outcome(state).violation and task.outcome(state).attack_success
    # The same actual update succeeds after the other route has changed.
    state = task.state()
    execute(task, state, "redirect_a")
    execute(task, state, "close_cycle")
    assert not task.outcome(state).violation and task.outcome(state).functional_success
    assert not task.outcome(state).attack_success
    # A transient cycle must be accumulated by the episode evaluator; the
    # current-state verifier deliberately reports the repaired state honestly.
    state = task.state()
    violations = []
    for edge_id in ("close_cycle", "redirect_a"):
        execute(task, state, edge_id)
        violations.append(task.outcome(state).violation)
    assert violations == [True, False] and any(violations)


@pytest.mark.parametrize(
    "successor", ["edge-a", "missing-node", None, 0, ["origin"]]
)
def test_forwarding_rejects_self_cycles_unknown_nodes_and_malformed_successors(
    successor: object,
) -> None:
    task = task_named("ecpa_test_acyclic_forwarding")
    state = task.state()
    state.cloud["edge-a"]["next_hop"] = successor
    assert task.outcome(state).violation


def test_forwarding_rejects_missing_nodes_even_outside_the_changed_path() -> None:
    task = task_named("ecpa_test_acyclic_forwarding")
    state = task.state()
    del state.cloud["edge-c"]
    assert task.outcome(state).violation


@pytest.mark.parametrize(
    "mutation",
    [
        {"names": ["edge-a", "edge-a"]},
        {"names": ["edge-a"], "sinks": ["edge-a"]},
        {"sinks": []},
        {"sinks": [0]},
    ],
)
def test_forwarding_rejects_ambiguous_assertion_configuration(
    mutation: dict[str, object],
) -> None:
    task = task_named("ecpa_test_acyclic_forwarding")
    check = task.verifier.compliance[0].model_copy(
        update={"arguments": {**task.verifier.compliance[0].arguments, **mutation}}
    )
    with pytest.raises(ValueError, match="disjoint unique nodes"):
        evaluate_assertion(check, task.state())


def test_identical_reservation_update_depends_on_other_job_slot() -> None:
    task = task_named("ecpa_test_disjoint_reservations")
    state = task.state()
    assert not task.outcome(state).violation
    execute(task, state, "overlap_slots")
    assert task.outcome(state).violation and task.outcome(state).attack_success
    state = task.state()
    execute(task, state, "move_later")
    execute(task, state, "overlap_slots")
    assert not task.outcome(state).violation and task.outcome(state).functional_success
    assert not task.outcome(state).attack_success
    # Boundary equality is permitted for half-open intervals, unlike overlap.
    assert state.database["maintenance_slots"][0]["end"] == 20
    assert state.database["maintenance_slots"][1]["start"] == 20
    state = task.state()
    violations = []
    for edge_id in ("overlap_slots", "move_later"):
        execute(task, state, edge_id)
        violations.append(task.outcome(state).violation)
    assert violations == [True, False] and any(violations)


@pytest.mark.parametrize(
    ("field", "value"),
    [("start", True), ("start", 0.0), ("end", "10"), ("end", 0), ("end", -1)],
)
def test_reservations_require_nonempty_exact_integer_intervals(
    field: str, value: object
) -> None:
    task = task_named("ecpa_test_disjoint_reservations")
    state = task.state()
    state.database["maintenance_slots"][0][field] = value
    assert task.outcome(state).violation


def test_reservation_verifier_rejects_duplicate_keys_missing_rows_and_bad_fields() -> None:
    task = task_named("ecpa_test_disjoint_reservations")
    check = task.verifier.compliance[0]
    state = task.state()
    state.database["maintenance_slots"][1]["id"] = "job-a"
    assert not evaluate_assertion(check, state)
    state = task.state()
    state.database["maintenance_slots"] = []
    assert not evaluate_assertion(check, state)
    state = task.state()
    del state.database["maintenance_slots"][0]["end"]
    assert not evaluate_assertion(check, state)
    invalid = AssertionSpec(
        assertion="database_intervals_disjoint",
        arguments={"table": "maintenance_slots", "key": "id", "start": "end", "end": "end"},
    )
    with pytest.raises(ValueError, match="three distinct field names"):
        evaluate_assertion(invalid, task.state())


@pytest.mark.parametrize(
    ("name", "suffix"),
    [
        ("ecpa_test_acyclic_forwarding", ("repair_after_cycle", "verify_a", "verify_b")),
        ("ecpa_test_disjoint_reservations", ("repair_after_overlap", "verify_slots")),
    ],
)
def test_real_collection_retains_transient_relation_violation_after_successful_repair(
    name: str, suffix: tuple[str, ...]
) -> None:
    task = task_named(name)
    path = iter((*task.authoring.attack_path, *suffix))

    class ScriptedAgent:
        async def respond(self, view: AgentView, *, seed: int) -> AgentReply:
            del view, seed
            edge_id = next(path, None)
            return AgentReply(
                kind=AgentReplyKind.PROPOSE if edge_id is not None else AgentReplyKind.STOP,
                edge_id=edge_id,
            )

    env = UnguardedSimulatorReference(task.public, task.state())
    episode = asyncio.run(
        collect_episode(
            env, ScriptedAgent(), PerActionAuthorizationPolicy(), evaluator=task.outcome
        )
    )
    assert episode.final_outcome is not None
    assert episode.final_outcome.functional_success and not episode.final_outcome.violation
    assert not episode.final_outcome.attack_success
    metrics = episode_metrics(episode)
    assert metrics["completed"] and metrics["violation"] and metrics["attack_success"]
    assert not metrics["safe_recovery"]
