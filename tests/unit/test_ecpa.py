from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from routebench.contracts import FeedbackMode
from routebench.defense import DefenseDecision, DefenseDecisionKind, ECPAEnvironment
from routebench.scenarios import load_scenario
from routebench.scenarios.schema import RouteActionSpec

PROJECT_ROOT = Path(__file__).parents[2]
SCENARIO = PROJECT_ROOT / "scenarios/graph_planning/dev/rbdv_f1_001_resource_inventory"


def _action(tool: str, **arguments: object) -> RouteActionSpec:
    return RouteActionSpec(tool=tool, arguments=arguments)


def test_ecpa_denial_is_not_a_dispatch_and_records_intervention() -> None:
    bundle = load_scenario(SCENARIO)
    env = ECPAEnvironment(bundle, feedback_mode=FeedbackMode.MINIMAL)
    proposal = _action(
        "database.query", table="jobs", columns=["owner_email"], where={"status": "paused"}
    )
    step = asyncio.run(env.step(proposal, DefenseDecision(DefenseDecisionKind.DENY)))
    assert not step.dispatched
    assert env.state.observations == []
    assert step.termination_reason == "decision_denied"
    assert not env.terminated

    retry = _action(
        "database.query", table="jobs", columns=["id"], where={"status": "paused"}
    )
    retry_step = asyncio.run(env.step(retry, DefenseDecision(DefenseDecisionKind.ALLOW)))
    assert retry_step.dispatched


def test_ecpa_allow_dispatches_only_after_hard_guard() -> None:
    bundle = load_scenario(SCENARIO)
    env = ECPAEnvironment(bundle, feedback_mode=FeedbackMode.MINIMAL)
    proposal = _action("database.query", table="jobs", columns=["id"], where={"status": "paused"})
    step = asyncio.run(env.step(proposal, DefenseDecision(DefenseDecisionKind.ALLOW)))
    assert step.dispatched
    assert step.hard_guard == "allow"
    assert env.executed_actions == 1
    assert len(env.state.observations) == 1


def test_ecpa_constrain_requires_registered_explicit_replacement() -> None:
    bundle = load_scenario(SCENARIO)
    env = ECPAEnvironment(bundle, feedback_mode=FeedbackMode.MINIMAL)
    proposal = _action(
        "database.query", table="jobs", columns=["owner_email"], where={"status": "paused"}
    )
    replacement = _action(
        "database.query", table="jobs", columns=["id"], where={"status": "paused"}
    )
    step = asyncio.run(
        env.step(
            proposal,
            DefenseDecision(DefenseDecisionKind.CONSTRAIN, replacement=replacement),
            registered_replacements=(replacement,),
        )
    )
    assert step.dispatched
    assert step.accepted_action == replacement
    assert env.state.observations[0].output == [{"id": "job-17"}, {"id": "job-23"}]


def test_ecpa_escalation_uses_trusted_approval_callback() -> None:
    bundle = load_scenario(SCENARIO)
    proposal = _action("database.query", table="jobs", columns=["id"], where={"status": "paused"})
    rejected = ECPAEnvironment(bundle, approval_provider=lambda action, preview: False)
    rejected_step = asyncio.run(
        rejected.step(proposal, DefenseDecision(DefenseDecisionKind.ESCALATE))
    )
    assert not rejected_step.dispatched
    approved = ECPAEnvironment(bundle, approval_provider=lambda action, preview: True)
    approved_step = asyncio.run(
        approved.step(proposal, DefenseDecision(DefenseDecisionKind.ESCALATE))
    )
    assert approved_step.dispatched
    assert approved.approval_epoch == 1


def test_ecpa_rejects_zero_decision_budget() -> None:
    bundle = load_scenario(SCENARIO)
    with pytest.raises(ValueError, match="decision budget"):
        ECPAEnvironment(bundle, decision_budget=0)
