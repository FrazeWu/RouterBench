"""P0 reference-route runner with per-action attack verification and evidence freezing."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from routebench.attacks import route_from_program, validate_revision
from routebench.authorization.controllers import AuthorizationContext
from routebench.contracts import (
    ActionRequest,
    AttackProgram,
    AttackStep,
    Decision,
    DecisionKind,
    FeedbackMode,
    RunStatus,
)
from routebench.evaluation import evaluate_all
from routebench.runtime.reference import Preview, ScenarioState, TrustedToolExecutor
from routebench.scenarios.loader import ScenarioBundle
from routebench.scenarios.schema import RouteActionSpec, RouteSpec


class ReferenceController(Protocol):
    async def decide(
        self, action: ActionRequest, context: AuthorizationContext, preview: Preview
    ) -> Decision: ...


class RevisionProvider(Protocol):
    """Supplies an online revision after a controller has denied a committed action."""

    async def revise(
        self,
        current: AttackProgram,
        denied_step: AttackStep,
        decision: Decision,
    ) -> AttackProgram | None: ...


@dataclass(frozen=True, slots=True)
class ReferenceRunResult:
    target_goal_id: str | None
    functional_success: bool
    policy_compliance: bool
    attack_success: bool
    intervened: bool
    evidence_frozen: bool
    actions_executed: int
    proposals_used: int
    status: RunStatus
    termination_reason: str | None
    decisions: tuple[str, ...]
    state: ScenarioState

    @property
    def task_compliance(self) -> bool:
        return self.functional_success and self.policy_compliance

    @property
    def joint_success(self) -> bool:
        return self.functional_success and self.attack_success


@dataclass(frozen=True, slots=True)
class ProgramRunResult(ReferenceRunResult):
    initial_program_hash: str
    program_hashes: tuple[str, ...]
    revisions_used: int


def _fixture_path(bundle: ScenarioBundle) -> Path:
    fixture = bundle.root / "fixtures" / "state.json"
    if not fixture.is_file():
        raise ValueError(f"scenario is missing fixture state: {fixture}")
    return fixture


async def run_reference_route_async(
    bundle: ScenarioBundle,
    route: RouteSpec,
    controller: ReferenceController,
    feedback_mode: FeedbackMode,
    target_goal_id: str | None = None,
    proposals_used: int = 0,
) -> ReferenceRunResult:
    state = ScenarioState.from_fixture(_fixture_path(bundle))
    executor = TrustedToolExecutor()
    context = AuthorizationContext(
        task=bundle.definition.task,
        policy=bundle.definition.policy,
        state=state,
        feedback_mode=feedback_mode,
    )
    decisions: list[str] = []
    attack_success = False
    intervened = False
    evidence_frozen = False
    executed = 0
    status = RunStatus.PLANNER_FINISHED
    termination_reason: str | None = None
    started = time.monotonic()

    for step, route_action in enumerate(route.actions):
        if time.monotonic() - started > bundle.definition.metadata.budgets.max_wall_seconds:
            status = RunStatus.BUDGET_EXHAUSTED
            termination_reason = "max_wall_seconds"
            break
        if executed >= bundle.definition.metadata.budgets.max_tool_executions:
            status = RunStatus.BUDGET_EXHAUSTED
            termination_reason = "max_tool_executions"
            break
        preview = executor.preview(route_action, state)
        effect = preview.effect.model_copy(update={"sensitivity": ",".join(preview.labels) or None})
        action = ActionRequest(
            action_id=f"reference-{step}",
            step=step,
            tool=route_action.tool,
            arguments=route_action.arguments,
            effects=(effect,),
        )
        decision = await controller.decide(action, context, preview)
        decisions.append(decision.kind.value)
        if decision.kind is not DecisionKind.ALLOW:
            intervened = True
            status = RunStatus.INTERVENED
            termination_reason = f"controller_{decision.kind.value}"
            break
        executor.execute(action, state)
        executed += 1
        if target_goal_id is not None and evaluate_all(
            bundle.definition.verifier.attack[target_goal_id], state
        ):
            attack_success = True
            evidence_frozen = True
            status = RunStatus.ATTACK_SUCCEEDED
            termination_reason = "target_forbidden_effect_observed"
            break

    functional_success = evaluate_all(bundle.definition.verifier.functional, state)
    policy_compliance = evaluate_all(bundle.definition.verifier.compliance, state)
    if status is RunStatus.PLANNER_FINISHED and functional_success:
        status = RunStatus.MAIN_SUCCEEDED
        termination_reason = "route_completed"

    return ReferenceRunResult(
        target_goal_id=target_goal_id,
        functional_success=functional_success,
        policy_compliance=policy_compliance,
        attack_success=attack_success,
        intervened=intervened,
        evidence_frozen=evidence_frozen,
        actions_executed=executed,
        proposals_used=proposals_used,
        status=status,
        termination_reason=termination_reason,
        decisions=tuple(decisions),
        state=state,
    )


def run_reference_route(
    bundle: ScenarioBundle,
    route: RouteSpec,
    controller: ReferenceController,
    feedback_mode: FeedbackMode,
    target_goal_id: str | None = None,
    proposals_used: int = 0,
) -> ReferenceRunResult:
    """Synchronously run one evaluator-owned route in a clean simulated workspace."""

    return asyncio.run(
        run_reference_route_async(
            bundle, route, controller, feedback_mode, target_goal_id, proposals_used
        )
    )


async def run_attack_program_async(
    bundle: ScenarioBundle,
    initial_program: AttackProgram,
    controller: ReferenceController,
    feedback_mode: FeedbackMode,
    revision_provider: RevisionProvider | None = None,
) -> ProgramRunResult:
    """Run a committed program, optionally appending validated revisions after denial."""
    if initial_program.goal not in bundle.definition.routes.attack:
        raise ValueError(
            f"attack program target is not declared by the scenario: {initial_program.goal}"
        )
    route_from_program(initial_program)

    state = ScenarioState.from_fixture(_fixture_path(bundle))
    executor = TrustedToolExecutor()
    context = AuthorizationContext(
        task=bundle.definition.task,
        policy=bundle.definition.policy,
        state=state,
        feedback_mode=feedback_mode,
    )
    current = initial_program
    program_hashes = [current.content_hash]
    decisions: list[str] = []
    attack_success = False
    intervened = False
    evidence_frozen = False
    executed = 0
    step_index = 0
    revisions_used = 0
    proposals_used = 1
    consecutive_denials = 0
    status = RunStatus.PLANNER_FINISHED
    termination_reason: str | None = None
    started = time.monotonic()

    while step_index < len(current.steps):
        if time.monotonic() - started > bundle.definition.metadata.budgets.max_wall_seconds:
            status = RunStatus.BUDGET_EXHAUSTED
            termination_reason = "max_wall_seconds"
            break
        if executed >= bundle.definition.metadata.budgets.max_tool_executions:
            status = RunStatus.BUDGET_EXHAUSTED
            termination_reason = "max_tool_executions"
            break
        program_step = current.steps[step_index]
        if program_step.action is None:
            raise ValueError(
                f"attack program step {program_step.step_id!r} has no committed action"
            )
        route_action = RouteActionSpec(
            tool=program_step.action.tool,
            arguments=program_step.action.arguments,
        )
        preview = executor.preview(route_action, state)
        effect = preview.effect.model_copy(update={"sensitivity": ",".join(preview.labels) or None})
        action = ActionRequest(
            action_id=f"{current.content_hash[:12]}-{program_step.step_id}",
            step=step_index,
            tool=route_action.tool,
            arguments=route_action.arguments,
            effects=(effect,),
        )
        decision = await controller.decide(action, context, preview)
        decisions.append(decision.kind.value)
        if decision.kind is not DecisionKind.ALLOW:
            intervened = True
            consecutive_denials += 1
            if consecutive_denials >= bundle.definition.metadata.budgets.max_consecutive_denials:
                status = RunStatus.BUDGET_EXHAUSTED
                termination_reason = "max_consecutive_denials"
                break
            if revision_provider is None:
                status = RunStatus.INTERVENED
                termination_reason = f"controller_{decision.kind.value}"
                break
            if proposals_used >= bundle.definition.metadata.budgets.max_proposals:
                status = RunStatus.BUDGET_EXHAUSTED
                termination_reason = "max_proposals"
                break
            revision = await revision_provider.revise(current, program_step, decision)
            if revision is None:
                status = RunStatus.INTERVENED
                termination_reason = "revision_provider_finished"
                break
            validate_revision(current, revision)
            current = revision
            program_hashes.append(current.content_hash)
            revisions_used += 1
            proposals_used += 1
            step_index += 1
            continue

        executor.execute(action, state)
        executed += 1
        consecutive_denials = 0
        if evaluate_all(bundle.definition.verifier.attack[current.goal], state):
            attack_success = True
            evidence_frozen = True
            status = RunStatus.ATTACK_SUCCEEDED
            termination_reason = "target_forbidden_effect_observed"
            break
        step_index += 1

    functional_success = evaluate_all(bundle.definition.verifier.functional, state)
    policy_compliance = evaluate_all(bundle.definition.verifier.compliance, state)
    if status is RunStatus.PLANNER_FINISHED and functional_success:
        status = RunStatus.MAIN_SUCCEEDED
        termination_reason = "program_completed"

    return ProgramRunResult(
        target_goal_id=current.goal,
        functional_success=functional_success,
        policy_compliance=policy_compliance,
        attack_success=attack_success,
        intervened=intervened,
        evidence_frozen=evidence_frozen,
        actions_executed=executed,
        proposals_used=proposals_used,
        status=status,
        termination_reason=termination_reason,
        decisions=tuple(decisions),
        state=state,
        initial_program_hash=initial_program.content_hash,
        program_hashes=tuple(program_hashes),
        revisions_used=revisions_used,
    )


def run_attack_program(
    bundle: ScenarioBundle,
    initial_program: AttackProgram,
    controller: ReferenceController,
    feedback_mode: FeedbackMode,
    revision_provider: RevisionProvider | None = None,
) -> ProgramRunResult:
    """Synchronously run the fixed or adaptive attack-program condition."""
    return asyncio.run(
        run_attack_program_async(
            bundle,
            initial_program,
            controller,
            feedback_mode,
            revision_provider,
        )
    )
