"""Actual parent rollouts and uniformly sampled, independently replayed branches.

This simulator collection kernel does not freeze a protocol or authorize a formal
run. Its caller owns source/review/model gates and private artifact persistence.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Callable
from dataclasses import dataclass

from routebench.defense.agent import AgentCall, JsonRecoveryAgent
from routebench.defense.collect import (
    CollectedEpisode,
    DefensePolicy,
    OutcomeLabel,
    PolicyChoice,
    collect_episode,
)
from routebench.defense.ecpa import DefenseObservation, ECPAEnvironment
from routebench.defense.evaluation import episode_metrics
from routebench.defense.lora import BranchOutcome
from routebench.defense.relay import StagedResponseRelay
from routebench.defense.traces import build_transitions
from routebench.runtime.reference import ScenarioState


@dataclass(frozen=True)
class RecordedRollout:
    episode: CollectedEpisode
    calls: tuple[AgentCall, ...]
    relay_events: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class RecordedBranch:
    outcome: BranchOutcome
    rollout: RecordedRollout


@dataclass(frozen=True)
class SampledComparison:
    encountered_index: int
    observation: DefenseObservation
    state_inclusion_probability: float
    branch_assignment_probability: float
    branches: tuple[RecordedBranch, ...]


@dataclass(frozen=True)
class ParentBranches:
    parent: RecordedRollout
    encountered_choice_states: int
    state_selection_seed: int
    comparisons: tuple[SampledComparison, ...]


@dataclass(frozen=True)
class _Snapshot:
    environment: ECPAEnvironment
    observation: DefenseObservation
    relay: StagedResponseRelay
    violation: bool
    attack_success: bool


class _StickyEvaluator:
    def __init__(
        self,
        evaluate: Callable[[ScenarioState], OutcomeLabel],
        *,
        violation: bool = False,
        attack_success: bool = False,
    ) -> None:
        self.evaluate, self.violation, self.attack_success = evaluate, violation, attack_success

    def __call__(self, state: ScenarioState) -> OutcomeLabel:
        result = self.evaluate(state)
        self.violation |= result.violation
        self.attack_success |= result.attack_success
        return result.model_copy(
            update={
                "violation": self.violation,
                "attack_success": self.attack_success,
            }
        )


async def _rollout(
    env: ECPAEnvironment,
    agent: JsonRecoveryAgent,
    relay: StagedResponseRelay,
    policy: DefensePolicy,
    *,
    evaluator: Callable[[ScenarioState], OutcomeLabel],
    seed: int,
    proposal_sampling_probability: float,
    max_collection_steps: int | None,
    observation: DefenseObservation | None = None,
    choice: PolicyChoice | None = None,
    snapshots: list[_Snapshot] | None = None,
) -> RecordedRollout:
    sticky = _StickyEvaluator(evaluator)
    sticky(env.state)

    async def observed(environment: ECPAEnvironment, view: DefenseObservation) -> None:
        if snapshots is not None and len(view.menu) > 1:
            snapshots.append(
                _Snapshot(
                    environment.clone_for_collection(),
                    view.model_copy(deep=True),
                    copy.deepcopy(relay),
                    sticky.violation,
                    sticky.attack_success,
                )
            )

    try:
        episode = await collect_episode(
            env,
            agent,
            policy,
            seed=seed,
            evaluator=sticky,
            proposal_sampling_probability=proposal_sampling_probability,
            max_collection_steps=max_collection_steps,
            first_observation=observation,
            first_choice=choice,
            observation_callback=observed,
        )
    finally:
        await agent.aclose()
    return RecordedRollout(episode, tuple(agent.calls), tuple(copy.deepcopy(relay.events)))


async def collect_parent_branches(
    environment: ECPAEnvironment,
    relay: StagedResponseRelay,
    agent_factory: Callable[[StagedResponseRelay], JsonRecoveryAgent],
    logging_policy: DefensePolicy,
    *,
    evaluator: Callable[[ScenarioState], OutcomeLabel],
    seed: int,
    state_selection_seed: int,
    continuation_seed: int,
    maximum_states: int = 2,
    repeats: int = 1,
    proposal_sampling_probability: float = 1.0,
    max_collection_steps: int | None = None,
) -> ParentBranches:
    """Finish parent, sample states uniformly, enumerate each complete menu.

    State inclusion, task acquisition and continuation behavior probabilities are
    separate quantities. All candidates within a repeat share the continuation
    seed. Relay consumption is restored to that decision point, never reset.
    Censored/failed branches are retained, so downstream preparation can exclude
    the entire incomplete group. Single-option menus are not learning decisions.
    """
    if maximum_states <= 0 or repeats <= 0:
        raise ValueError("state and repeat counts must be positive")
    snapshots: list[_Snapshot] = []
    parent = await _rollout(
        environment,
        agent_factory(relay),
        relay,
        logging_policy,
        seed=seed,
        evaluator=evaluator,
        proposal_sampling_probability=proposal_sampling_probability,
        max_collection_steps=max_collection_steps,
        snapshots=snapshots,
    )
    count = len(snapshots)
    indices = sorted(
        random.Random(state_selection_seed).sample(range(count), k=min(maximum_states, count))
    )
    comparisons = []
    for index in indices:
        snapshot = snapshots[index]
        branches = []
        for repeat in range(repeats):
            common_seed = continuation_seed + repeat
            for candidate in snapshot.observation.menu:
                branch_env = snapshot.environment.clone_for_collection()
                branch_relay = copy.deepcopy(snapshot.relay)
                sticky = _StickyEvaluator(
                    evaluator, violation=snapshot.violation, attack_success=snapshot.attack_success
                )
                rollout = await _rollout(
                    branch_env,
                    agent_factory(branch_relay),
                    branch_relay,
                    logging_policy,
                    seed=common_seed,
                    evaluator=sticky,
                    proposal_sampling_probability=proposal_sampling_probability,
                    max_collection_steps=max_collection_steps,
                    observation=snapshot.observation,
                    choice=PolicyChoice(candidate.candidate_id),
                )
                episode = rollout.episode
                metrics, transitions = episode_metrics(episode), build_transitions(episode)
                branches.append(
                    RecordedBranch(
                        BranchOutcome(
                            candidate_id=candidate.candidate_id,
                            repeat=repeat,
                            continuation_seed=common_seed,
                            terminated=episode.terminated,
                            truncated=episode.truncated,
                            safe_completion=bool(metrics["safe_recovery"])
                            if episode.terminated
                            else None,
                            violation=bool(metrics["violation"]) if episode.terminated else None,
                            cost=transitions[0].remaining_cost if transitions else None,
                            termination_reason=episode.termination_reason,
                        ),
                        rollout,
                    )
                )
        comparisons.append(
            SampledComparison(
                index, snapshot.observation, min(1.0, maximum_states / count), 1.0, tuple(branches)
            )
        )
    return ParentBranches(parent, count, state_selection_seed, tuple(comparisons))
