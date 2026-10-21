"""Private learning records with real state/menu features and censoring semantics."""

from __future__ import annotations

from dataclasses import dataclass

from routebench.defense.collect import CollectedEpisode
from routebench.defense.contracts import content_hash
from routebench.defense.ecpa import DefenseDecisionKind, DefenseObservation
from routebench.scenarios.schema import StrictModel


@dataclass(frozen=True, slots=True)
class ECPARewardSpec:
    task_success: float = 1.0
    violation: float = -10.0
    execution_cost: float = -0.01
    intervention_cost: float = -0.02
    approval_cost: float = -0.02
    agent_call_cost: float = -0.001
    preview_cost: float = -0.0001
    search_cost: float = -0.0001


class ECPATransition(StrictModel):
    state_hash: str
    state: DefenseObservation
    candidate_id: str
    next_state: DefenseObservation | None
    reward: float
    violation_increment: int
    dispatched: bool
    terminal: bool
    truncated: bool
    bootstrap_available: bool
    proposal_sampling_probability: float
    intervention_behavior_probability: float
    remaining_safe_success: float | None
    remaining_cost: float | None
    eventual_violation: float | None = None


def observation_hash(observation: DefenseObservation) -> str:
    return content_hash(observation.model_dump(mode="json", exclude={"state_token"}))


def build_transitions(
    episode: CollectedEpisode,
    *,
    reward_spec: ECPARewardSpec | None = None,
) -> tuple[ECPATransition, ...]:
    if episode.final_outcome is None or len(episode.outcomes) != len(episode.steps):
        raise ValueError("learning records require separately evaluated actual outcomes")
    if len(episode.intervention_probabilities) != len(episode.steps):
        raise ValueError("intervention probabilities must match the collected steps")
    reward_spec = reward_spec or ECPARewardSpec()
    safe_success = (
        episode.terminated
        and episode.termination_reason == "agent_stop"
        and episode.final_outcome.functional_success
        and not episode.final_outcome.violation
        and not any(outcome.violation for outcome in episode.outcomes)
    )
    records = []
    violated = False
    step_costs: list[float] = []
    for index, step in enumerate(episode.steps):
        before = step.observation.remaining
        # Include the next proposal/STOP call in the preceding transition's cost.
        after = (
            episode.steps[index + 1].observation.remaining
            if index + 1 < len(episode.steps)
            else episode.final_state["remaining"]
        )
        if not isinstance(after, dict):
            raise ValueError("missing final resource ledger")
        cost = (
            reward_spec.execution_cost * (before["executions"] - int(after["executions"]))
            + reward_spec.approval_cost * (before["approvals"] - int(after["approvals"]))
            + reward_spec.agent_call_cost * (before["agent_calls"] - int(after["agent_calls"]))
            + reward_spec.preview_cost * (before["previews"] - int(after["previews"]))
            + reward_spec.search_cost * (before["searches"] - int(after["searches"]))
            + reward_spec.intervention_cost
            * int(step.selected.kind is not DefenseDecisionKind.ALLOW)
        )
        step_costs.append(cost)
        outcome = episode.outcomes[index]
        increment = int(outcome.violation and not violated)
        violated = violated or outcome.violation
        last = index + 1 == len(episode.steps)
        terminal = last and episode.terminated
        records.append(
            ECPATransition(
                state_hash=observation_hash(step.observation),
                state=step.observation,
                candidate_id=step.selected.candidate_id,
                next_state=episode.steps[index + 1].observation if not last else None,
                reward=cost
                + reward_spec.violation * increment
                + reward_spec.task_success * int(terminal and safe_success),
                violation_increment=increment,
                dispatched=step.dispatched,
                terminal=terminal,
                truncated=last and episode.truncated,
                bootstrap_available=not last or terminal,
                proposal_sampling_probability=episode.proposal_sampling_probability,
                intervention_behavior_probability=episode.intervention_probabilities[index],
                remaining_safe_success=float(safe_success) if episode.terminated else None,
                remaining_cost=None,
                eventual_violation=(
                    float(
                        episode.final_outcome.violation
                        or any(item.violation for item in episode.outcomes)
                    )
                    if episode.terminated
                    else None
                ),
            )
        )
    cumulative_cost = 0.0
    result = []
    for record, cost in zip(reversed(records), reversed(step_costs), strict=True):
        cumulative_cost += cost
        result.append(
            record.model_copy(
                update={
                    "remaining_cost": -cumulative_cost if episode.terminated else None,
                }
            )
        )
    return tuple(reversed(result))
