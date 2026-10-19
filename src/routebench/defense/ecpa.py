"""A trusted, intervention-dependent simulator for ECPA data collection.

The environment keeps policy decisions separate from dispatch. A learned policy can
request an intervention, but it cannot rewrite a proposal, waive a hard guard, or
manufacture approval. Constrained actions must be supplied as explicit registered
replacement requests by the caller.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from routebench.authorization.controllers import (
    AuthorizationContext,
    PathStateAuthorizationController,
)
from routebench.contracts import ActionRequest, DecisionKind, FeedbackMode
from routebench.evaluation import evaluate_all
from routebench.runtime.reference import Preview, ScenarioState, TrustedToolExecutor
from routebench.runtime.runner import ReferenceController
from routebench.scenarios.loader import ScenarioBundle
from routebench.scenarios.schema import RouteActionSpec


class DefenseDecisionKind(StrEnum):
    """Runtime intervention choices exposed to a defense policy."""

    ALLOW = "allow"
    CONSTRAIN = "constrain"
    ESCALATE = "escalate"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class DefenseDecision:
    """A policy proposal; approval is supplied only by the trusted environment."""

    kind: DefenseDecisionKind
    replacement: RouteActionSpec | None = None


@dataclass(frozen=True, slots=True)
class DefenseObservation:
    """Value-free state presented to a policy or stored in a training trace."""

    step: int
    proposal_hash: str
    tool: str
    effect_resource: str
    effect_operation: str
    effect_target: str
    labels: tuple[str, ...]
    executed_actions: int
    decision_budget_remaining: int
    approval_epoch: int
    first_violation: bool
    terminal: bool


@dataclass(frozen=True, slots=True)
class ECPAStep:
    """One intervention and its actual simulator outcome."""

    observation: DefenseObservation
    proposal: RouteActionSpec
    decision: DefenseDecisionKind
    accepted_action: RouteActionSpec | None
    dispatched: bool
    approved: bool
    hard_guard: str
    functional_success: bool
    policy_compliance: bool
    attack_success: bool
    violation: bool
    first_violation: bool
    termination_reason: str | None


class ApprovalProvider(Protocol):
    """Trusted approval source; model output cannot implement this callback."""

    def __call__(self, action: ActionRequest, preview: Preview) -> bool | Awaitable[bool]: ...


class ECPAEnvironment:
    """Execute intervention-dependent rollouts inside the trusted simulator."""

    def __init__(
        self,
        bundle: ScenarioBundle,
        *,
        feedback_mode: FeedbackMode = FeedbackMode.MINIMAL,
        hard_guard: ReferenceController | None = None,
        approval_provider: ApprovalProvider | None = None,
        decision_budget: int | None = None,
    ) -> None:
        self.bundle = bundle
        self.feedback_mode = feedback_mode
        self.state = ScenarioState.from_fixture(bundle.root / "fixtures" / "state.json")
        self.executor = TrustedToolExecutor()
        self.context = AuthorizationContext(
            task=bundle.definition.task,
            policy=bundle.definition.policy,
            state=self.state,
            feedback_mode=feedback_mode,
        )
        self.hard_guard = hard_guard or PathStateAuthorizationController()
        self.approval_provider = approval_provider
        configured_budget = bundle.definition.metadata.budgets.max_proposals
        self.decision_budget = configured_budget if decision_budget is None else decision_budget
        if self.decision_budget <= 0:
            raise ValueError("ECPA decision budget must be positive")
        self.step_index = 0
        self.approval_epoch = 0
        self.executed_actions = 0
        self.first_violation_seen = False
        self.terminated = False
        self.history: list[ECPAStep] = []

    async def step(
        self,
        proposal: RouteActionSpec,
        decision: DefenseDecision,
        *,
        registered_replacements: tuple[RouteActionSpec, ...] = (),
    ) -> ECPAStep:
        """Apply one decision and return the actual, replay-derived outcome.

        A constrained replacement must be byte-for-byte equal to one of the supplied
        registered requests. The guard is rerun on the accepted request immediately
        before dispatch. Any non-allow guard result is terminal for this step and no
        tool effect is executed.
        """
        if self.terminated:
            raise RuntimeError("ECPA episode is already terminated")
        if self.step_index >= self.decision_budget:
            self.terminated = True
            raise RuntimeError("ECPA decision budget exhausted")

        proposal_request, proposal_preview = self._prepare(proposal)
        observation = DefenseObservation(
            step=self.step_index,
            proposal_hash=proposal_request.action_hash,
            tool=proposal.tool,
            effect_resource=proposal_preview.effect.resource,
            effect_operation=proposal_preview.effect.operation,
            effect_target=proposal_preview.effect.target,
            labels=proposal_preview.labels,
            executed_actions=self.executed_actions,
            decision_budget_remaining=self.decision_budget - self.step_index,
            approval_epoch=self.approval_epoch,
            first_violation=self.first_violation_seen,
            terminal=False,
        )

        accepted_action: RouteActionSpec | None = None
        approved = False
        hard_guard = "not_checked"
        if decision.kind is DefenseDecisionKind.DENY:
            hard_guard = "policy_denied"
        elif decision.kind is DefenseDecisionKind.CONSTRAIN:
            if decision.replacement is None:
                return self._record(
                    observation, proposal, decision.kind, None, False, False,
                    "missing_registered_replacement", "replacement_required"
                )
            if decision.replacement not in registered_replacements:
                return self._record(
                    observation, proposal, decision.kind, None, False, False,
                    "unregistered_replacement", "replacement_not_registered"
                )
            accepted_action = decision.replacement
        elif decision.kind is DefenseDecisionKind.ALLOW:
            accepted_action = proposal
        elif decision.kind is DefenseDecisionKind.ESCALATE:
            accepted_action = proposal
            if self.approval_provider is not None:
                approved_value = self.approval_provider(proposal_request, proposal_preview)
                approved = (
                    bool(await approved_value)
                    if inspect.isawaitable(approved_value)
                    else bool(approved_value)
                )
            if not approved:
                return self._record(
                    observation, proposal, decision.kind, None, False, False,
                    "approval_pending_or_rejected", "approval_rejected"
                )
            self.approval_epoch += 1
        else:  # pragma: no cover - StrEnum exhaustiveness guard
            raise ValueError(f"unsupported ECPA decision: {decision.kind}")

        if accepted_action is None:
            return self._record(
                observation, proposal, decision.kind, None, False, approved,
                hard_guard, "decision_denied"
            )

        accepted_request, accepted_preview = self._prepare(accepted_action)
        guard_decision = await self.hard_guard.decide(
            accepted_request, self.context, accepted_preview
        )
        if guard_decision.kind is not DecisionKind.ALLOW:
            return self._record(
                observation, proposal, decision.kind, accepted_action, False, approved,
                f"guard_{guard_decision.kind.value}", "hard_guard_rejected"
            )

        self.executor.execute(accepted_request, self.state)
        self.executed_actions += 1
        functional = evaluate_all(self.bundle.definition.verifier.functional, self.state)
        compliant = evaluate_all(self.bundle.definition.verifier.compliance, self.state)
        target_id = self.bundle.definition.metadata.primary_target_id
        attack = (
            evaluate_all(self.bundle.definition.verifier.attack[target_id], self.state)
            if target_id is not None
            else False
        )
        violation = not compliant
        first_violation = violation and not self.first_violation_seen
        self.first_violation_seen = self.first_violation_seen or violation
        terminal_reason = "task_completed" if functional else None
        return self._record(
            observation, proposal, decision.kind, accepted_action, True, approved,
            "allow", terminal_reason, functional=functional, compliant=compliant,
            attack=attack, violation=violation, first_violation=first_violation,
        )

    def _prepare(self, action: RouteActionSpec) -> tuple[ActionRequest, Preview]:
        self.executor.require_prior_actions(action, self.state)
        preview = self.executor.preview(action, self.state)
        effect = preview.effect.model_copy(update={"sensitivity": ",".join(preview.labels) or None})
        request = ActionRequest(
            action_id=f"ecpa-{self.step_index}-{action.tool}",
            step=self.step_index,
            tool=action.tool,
            arguments=action.arguments,
            effects=(effect,),
        )
        return request, preview

    def _record(
        self,
        observation: DefenseObservation,
        proposal: RouteActionSpec,
        decision: DefenseDecisionKind,
        accepted_action: RouteActionSpec | None,
        dispatched: bool,
        approved: bool,
        hard_guard: str,
        termination_reason: str | None,
        *,
        functional: bool = False,
        compliant: bool = True,
        attack: bool = False,
        violation: bool = False,
        first_violation: bool = False,
    ) -> ECPAStep:
        self.step_index += 1
        if termination_reason == "task_completed":
            self.terminated = True
        result = ECPAStep(
            observation=observation,
            proposal=proposal,
            decision=decision,
            accepted_action=accepted_action,
            dispatched=dispatched,
            approved=approved,
            hard_guard=hard_guard,
            functional_success=functional,
            policy_compliance=compliant,
            attack_success=attack,
            violation=violation,
            first_violation=first_violation,
            termination_reason=termination_reason,
        )
        self.history.append(result)
        return result
