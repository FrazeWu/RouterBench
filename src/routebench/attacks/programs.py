"""Immutable attack-program construction and revision validation."""

from __future__ import annotations

from collections.abc import Iterable

from routebench.contracts import AttackProgram, AttackStep, PlannedAction
from routebench.scenarios.schema import RouteActionSpec, RouteSpec


def program_from_route(goal: str, route: RouteSpec) -> AttackProgram:
    """Commit a declarative reference route as a fixed, controller-visible program."""
    steps = tuple(
        AttackStep(
            step_id=f"step_{index}",
            primitive=action.tool,
            target=_target_for(action),
            action=PlannedAction(tool=action.tool, arguments=action.arguments),
        )
        for index, action in enumerate(route.actions)
    )
    return AttackProgram(goal=goal, steps=steps, committed_at_step=0)


def route_from_program(program: AttackProgram) -> RouteSpec:
    """Materialize the exact committed actions and reject semantic-only programs."""
    actions: list[RouteActionSpec] = []
    for step in program.steps:
        if step.action is None:
            raise ValueError(f"attack program step {step.step_id!r} has no committed action")
        actions.append(RouteActionSpec(tool=step.action.tool, arguments=step.action.arguments))
    return RouteSpec(actions=tuple(actions))


def revise_program(
    current: AttackProgram,
    additions: Iterable[AttackStep],
    committed_at_step: int,
) -> AttackProgram:
    """Append online-discovered actions while preserving the committed prefix exactly."""
    added_steps = tuple(additions)
    if not added_steps:
        raise ValueError("adaptive revisions must add at least one step")
    existing_ids = {step.step_id for step in current.steps}
    duplicate_ids = existing_ids.intersection(step.step_id for step in added_steps)
    if duplicate_ids:
        raise ValueError(f"adaptive revision reuses committed step IDs: {sorted(duplicate_ids)}")
    if committed_at_step < current.committed_at_step:
        raise ValueError("adaptive revision cannot move committed_at_step backward")
    return AttackProgram(
        goal=current.goal,
        steps=current.steps + added_steps,
        parent_hash=current.content_hash,
        committed_at_step=committed_at_step,
    )


def validate_revision(current: AttackProgram, revision: AttackProgram) -> None:
    """Check a received adaptive revision before it can replace the active program."""
    if revision.parent_hash != current.content_hash:
        raise ValueError("adaptive revision parent hash does not match the active program")
    if revision.goal != current.goal:
        raise ValueError("adaptive revision changed the forbidden goal")
    prefix = revision.steps[: len(current.steps)]
    if prefix != current.steps:
        raise ValueError("adaptive revision changed a committed action prefix")
    if len(revision.steps) <= len(current.steps):
        raise ValueError("adaptive revision must add at least one action")
    if revision.committed_at_step < current.committed_at_step:
        raise ValueError("adaptive revision moved committed_at_step backward")


def _target_for(action: RouteActionSpec) -> str:
    for key in ("path", "name", "table", "endpoint", "destination", "resource_id"):
        if key in action.arguments:
            return str(action.arguments[key])
    return action.tool
