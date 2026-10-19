"""Private, value-free transition records for ECPA data collection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from routebench.defense.ecpa import DefenseDecisionKind, DefenseObservation, ECPAStep


@dataclass(frozen=True, slots=True)
class ECPARewardSpec:
    """Fixed reward accounting used before collection; it is not tuned on tests."""

    task_success: float = 1.0
    violation: float = -10.0
    dispatch_cost: float = -0.01
    intervention_cost: float = -0.02
    approval_cost: float = -0.02


@dataclass(frozen=True, slots=True)
class ECPATransition:
    """One simulator-derived transition without private action arguments."""

    state_hash: str
    action: DefenseDecisionKind
    next_state_hash: str | None
    reward: float
    violation_increment: int
    dispatched: bool
    terminal: bool
    behavior_probability: float


def observation_hash(observation: DefenseObservation) -> str:
    payload = json.dumps(
        {
            "step": observation.step,
            "proposal_hash": observation.proposal_hash,
            "tool": observation.tool,
            "effect_resource": observation.effect_resource,
            "effect_operation": observation.effect_operation,
            "effect_target": observation.effect_target,
            "labels": observation.labels,
            "executed_actions": observation.executed_actions,
            "decision_budget_remaining": observation.decision_budget_remaining,
            "approval_epoch": observation.approval_epoch,
            "first_violation": observation.first_violation,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_transitions(
    steps: tuple[ECPAStep, ...],
    *,
    reward_spec: ECPARewardSpec | None = None,
    behavior_probabilities: tuple[float, ...] | None = None,
) -> tuple[ECPATransition, ...]:
    """Convert actual steps into CQL-ready records with checked probabilities."""

    if reward_spec is None:
        reward_spec = ECPARewardSpec()
    if behavior_probabilities is None:
        behavior_probabilities = tuple(1.0 for _ in steps)
    if len(behavior_probabilities) != len(steps):
        raise ValueError("behavior probabilities must match the number of ECPA steps")
    transitions: list[ECPATransition] = []
    for index, step in enumerate(steps):
        probability = behavior_probabilities[index]
        if not 0.0 < probability <= 1.0:
            raise ValueError("behavior probabilities must be in (0, 1]")
        reward = 0.0
        if step.functional_success:
            reward += reward_spec.task_success
        if step.violation:
            reward += reward_spec.violation
        if step.dispatched:
            reward += reward_spec.dispatch_cost
        if step.decision is not DefenseDecisionKind.ALLOW:
            reward += reward_spec.intervention_cost
        if step.approved:
            reward += reward_spec.approval_cost
        next_hash = (
            observation_hash(steps[index + 1].observation)
            if index + 1 < len(steps)
            else None
        )
        transitions.append(
            ECPATransition(
                state_hash=observation_hash(step.observation),
                action=step.decision,
                next_state_hash=next_hash,
                reward=reward,
                violation_increment=int(step.first_violation),
                dispatched=step.dispatched,
                terminal=step.termination_reason == "task_completed"
                or index + 1 == len(steps),
                behavior_probability=probability,
            )
        )
    return tuple(transitions)
