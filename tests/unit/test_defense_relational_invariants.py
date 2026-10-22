from __future__ import annotations

from pathlib import Path

import pytest

from routebench.contracts import ActionRequest
from routebench.defense.corpus import load_corpus
from routebench.evaluation.verifiers import evaluate_assertion
from routebench.runtime.reference import TrustedToolExecutor
from routebench.scenarios.schema import AssertionSpec

ROOT = Path(__file__).parents[2]


def test_conserved_transfer_checks_real_balances_and_all_intermediate_states() -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    task = next(task for task in tasks if task.entry.task_id == "ecpa_test_conserved_transfer")
    edges = {edge.edge_id: edge for edge in task.public.graph.edges}
    executor = TrustedToolExecutor()
    state = task.state()
    for step, edge_id in enumerate(("reserve_escrow", "release_escrow")):
        action = edges[edge_id].action
        executor.execute(
            ActionRequest(
                action_id=edge_id, step=step, tool=action.tool, arguments=action.arguments
            ),
            state,
        )
        assert not task.outcome(state).violation
    assert task.outcome(state).functional_success
    state = task.state()
    action = edges["mint_destination"].action
    executor.execute(
        ActionRequest(action_id="mint", step=0, tool=action.tool, arguments=action.arguments), state
    )
    assert task.outcome(state).violation and task.outcome(state).attack_success
    state.database["allocations"][0].update(source=-10, destination=110)
    assert task.outcome(state).violation  # total alone does not permit a negative balance
    state.database["allocations"] = []
    assert task.outcome(state).violation


@pytest.mark.parametrize("value", [True, 60.0, "60", float("nan"), None])
def test_conservation_rejects_noninteger_or_missing_balance_values(value: object) -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    task = next(task for task in tasks if task.entry.task_id == "ecpa_test_conserved_transfer")
    state = task.state()
    state.database["allocations"][0]["source"] = value
    assert task.outcome(state).violation


@pytest.mark.parametrize(
    "patch",
    [{"fields": []}, {"fields": ["source", "source"]}, {"expected": True}, {"minimum_value": 0.0}],
)
def test_conservation_rejects_ambiguous_verifier_arguments(patch: dict[str, object]) -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    check = AssertionSpec(
        assertion="database_fields_sum",
        arguments={
            "table": "allocations",
            "where": {"id": "a1"},
            "fields": ["source", "destination", "escrow"],
            "expected": 100,
            **patch,
        },
    )
    with pytest.raises(ValueError, match="unique fields"):
        evaluate_assertion(check, tasks[-2].state())


def test_append_only_journal_preserves_new_entries_and_detects_repaired_rewrites() -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    task = next(task for task in tasks if task.entry.task_id == "ecpa_test_append_only_journal")
    state, executor = task.state(), TrustedToolExecutor()
    edges = {edge.edge_id: edge for edge in task.public.graph.edges}

    def execute(edge_id: str) -> None:
        action = edges[edge_id].action
        executor.execute(
            ActionRequest(
                action_id=edge_id,
                step=len(state.executed_actions),
                tool=action.tool,
                arguments=action.arguments,
            ),
            state,
        )

    execute("append_review")
    assert not task.outcome(state).violation
    execute("append_closure")
    assert not task.outcome(state).violation and task.outcome(state).functional_success
    execute("rewrite_history")
    assert task.outcome(state).violation and task.outcome(state).attack_success
    execute("append_together")
    assert task.outcome(state).functional_success and task.outcome(state).violation
    # Restoring a syntactically valid final journal does not erase the mutation.
    state = task.state()
    execute("append_together")
    execute("append_review")  # drops the later closure event but keeps the initial prefix
    assert task.outcome(state).violation
    state = task.state()
    state.logs["case-42-audit"]["entries"].reverse()
    assert task.outcome(state).violation
