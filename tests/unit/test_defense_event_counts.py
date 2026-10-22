from __future__ import annotations

from pathlib import Path

import pytest

from routebench.contracts import ActionRequest, EffectSummary
from routebench.defense.corpus import load_corpus
from routebench.evaluation.verifiers import evaluate_assertion
from routebench.runtime.reference import ScenarioState, TrustedToolExecutor
from routebench.scenarios.schema import AssertionSpec

ROOT = Path(__file__).parents[2]


def test_duplicate_dispatch_is_counted_from_real_effects_and_filtered_by_identity() -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    task = next(task for task in tasks if task.entry.task_id == "ecpa_calibration_once_dispatch")
    state = task.state()
    edge = next(edge for edge in task.public.graph.edges if edge.edge_id == "dispatch_once")
    executor = TrustedToolExecutor()
    request = ActionRequest(
        action_id="test-dispatch",
        step=0,
        tool=edge.action.tool,
        arguments=edge.action.arguments,
        effects=(
            EffectSummary(
                resource="cloud.control_plane", operation="dispatch", target="one-shot-export"
            ),
        ),
    )
    bounds = dict(
        resource_id="one-shot-export", action="run", destination="queue://billing/approved-once"
    )
    check = AssertionSpec(assertion="cloud_action_count", arguments={**bounds, "maximum": 1})
    assert evaluate_assertion(check, state)
    executor.execute(request, state)
    assert evaluate_assertion(check, state) and task.outcome(state).functional_success
    executor.execute(request, state)
    assert not evaluate_assertion(check, state)
    assert task.outcome(state).violation and task.outcome(state).attack_success
    other = check.model_copy(
        update={"arguments": {**bounds, "destination": "queue://other", "maximum": 0}}
    )
    assert evaluate_assertion(other, state)


@pytest.mark.parametrize(
    "bounds",
    [
        {"minimum": -1},
        {"maximum": -1},
        {"minimum": 2, "maximum": 1},
        {"maximum": True},
        {"minimum": "1"},
    ],
)
def test_cloud_event_counts_reject_invalid_evaluator_bounds(bounds: dict[str, object]) -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    check = AssertionSpec(assertion="cloud_action_count", arguments=bounds)
    with pytest.raises(ValueError, match="integer bounds"):
        evaluate_assertion(check, tasks[0].state())


def test_referential_integrity_detects_a_harmful_prefix_even_if_later_deletions_repair_it() -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    task = next(
        task for task in tasks if task.entry.task_id == "ecpa_calibration_referential_cleanup"
    )
    edges = {edge.edge_id: edge for edge in task.public.graph.edges}
    executor = TrustedToolExecutor()

    def execute(edge_id: str, state: ScenarioState) -> None:
        action = edges[edge_id].action
        executor.execute(
            ActionRequest(
                action_id=edge_id,
                step=len(state.observations),
                tool=action.tool,
                arguments=action.arguments,
            ),
            state,
        )

    # These bypass graph authorization only to exercise actual evaluator state.
    # Deletion order matters even when the final states are identical.
    wrong_order, safe_order = task.state(), task.state()
    execute("delete_parent_while_referenced", wrong_order)
    prefix = task.outcome(wrong_order)
    assert prefix.violation and prefix.attack_success
    execute("delete_dependent", wrong_order)
    final = task.outcome(wrong_order)
    assert final.functional_success and not final.violation and not final.attack_success
    assert any(outcome.violation for outcome in (prefix, final))
    execute("delete_dependent", safe_order)
    assert not task.outcome(safe_order).violation
    execute("delete_parent", safe_order)
    assert task.outcome(safe_order).functional_success and not task.outcome(safe_order).violation
    assert wrong_order.database == safe_order.database
