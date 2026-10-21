"""Actual agent continuations, independent branches and probability accounting."""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from routebench.defense.ecpa import (
    AgentReplyKind,
    BudgetExhausted,
    DefenseObservation,
    ECPAEnvironment,
    ECPAStep,
    RecoveryAgent,
)
from routebench.runtime.reference import ScenarioState
from routebench.scenarios.schema import StrictModel


class CollectionMode(StrEnum):
    UNIFORM = "uniform"
    DIAGNOSTIC_GUIDED = "diagnostic_guided"


@dataclass(frozen=True, slots=True)
class SampledTask:
    task_index: int
    proposal_sampling_probability: float


def sample_tasks(
    strata: tuple[str, ...],
    *,
    budget: int,
    mode: CollectionMode,
    diagnostic_scores: dict[str, float] | None = None,
    seed: int = 0,
) -> tuple[SampledTask, ...]:
    """Task/stratum acquisition probabilities are not intervention probabilities."""
    if not strata or budget <= 0:
        raise ValueError("collection needs tasks and a positive budget")
    scores = diagnostic_scores or {}
    if any(not math.isfinite(score) or score < 0 for score in scores.values()):
        raise ValueError("diagnostic scores must be finite and nonnegative")
    count = len(strata)
    probabilities = [1.0 / count] * count
    if mode is CollectionMode.DIAGNOSTIC_GUIDED:
        weights = [0.1 + scores.get(stratum, 0.0) for stratum in strata]
        total = sum(weights)
        probabilities = [0.5 / count + 0.5 * value / total for value in weights]
    rng = random.Random(seed)
    return tuple(
        SampledTask(index, probabilities[index])
        for index in rng.choices(range(count), weights=probabilities, k=budget)
    )


@dataclass(frozen=True, slots=True)
class PolicyChoice:
    candidate_id: str
    intervention_probability: float = 1.0
    search_expansions: int = 0


class DefensePolicy(Protocol):
    def choose(self, observation: DefenseObservation, *, rng: random.Random) -> PolicyChoice: ...


class OutcomeLabel(StrictModel):
    """Evaluator output: never fed back to the runtime, learner or agent."""

    functional_success: bool
    violation: bool
    attack_success: bool = False


@dataclass(frozen=True, slots=True)
class CollectedEpisode:
    steps: tuple[ECPAStep, ...]
    intervention_probabilities: tuple[float, ...]
    proposal_sampling_probability: float
    terminated: bool
    truncated: bool
    termination_reason: str | None
    final_state: dict[str, object]
    outcomes: tuple[OutcomeLabel, ...] = ()
    final_outcome: OutcomeLabel | None = None


async def collect_episode(
    environment: ECPAEnvironment,
    agent: RecoveryAgent,
    policy: DefensePolicy,
    *,
    seed: int = 0,
    proposal_sampling_probability: float = 1.0,
    max_collection_steps: int | None = None,
    first_choice: PolicyChoice | None = None,
    first_observation: DefenseObservation | None = None,
    evaluator: Callable[[ScenarioState], OutcomeLabel] | None = None,
) -> CollectedEpisode:
    """Every intervention changes the rollout; no preset post-rejection proposals.

    A collection cutoff is censored, not an MDP terminal. A branch's forced first
    action has conditional probability one given its explicit branch assignment;
    callers retain the separate branch assignment probability in their manifest.
    """
    if not 0 < proposal_sampling_probability <= 1:
        raise ValueError("proposal sampling probability must be in (0, 1]")
    if max_collection_steps is not None and max_collection_steps <= 0:
        raise ValueError("collection cutoff must be positive")
    rng = random.Random(seed)
    steps: list[ECPAStep] = []
    probabilities: list[float] = []
    outcomes: list[OutcomeLabel] = []
    observation = first_observation
    while not environment.terminated:
        if max_collection_steps is not None and len(steps) >= max_collection_steps:
            break
        if observation is None:
            proposal = environment.pending_proposal
            environment.pending_proposal = None
            if proposal is None:
                proposal = await environment.call_agent(agent, seed=rng.randrange(2**31))
            if proposal is None:
                break
            if proposal.kind is AgentReplyKind.STOP:
                environment.handle_stop()
                break
            if proposal.kind is not AgentReplyKind.PROPOSE:
                environment.finish("invalid_agent_reply")
                break
            observation = await environment.observe(proposal)
        if observation is None:
            break
        choice = (
            first_choice
            if not steps and first_choice is not None
            else policy.choose(observation, rng=rng)
        )
        if not math.isfinite(choice.intervention_probability) or not (
            0 < choice.intervention_probability <= 1
        ):
            raise ValueError("intervention probability must be in (0, 1]")
        try:
            environment.budget.charge("searches", choice.search_expansions)
        except BudgetExhausted as error:
            environment.finish(f"budget_exhausted:{error}")
            break
        step = await environment.step(
            observation, choice.candidate_id, agent=agent, seed=rng.randrange(2**31)
        )
        steps.append(step)
        probabilities.append(choice.intervention_probability)
        if evaluator is not None:
            outcomes.append(evaluator(environment.state))
        observation = None
    return CollectedEpisode(
        steps=tuple(steps),
        intervention_probabilities=tuple(probabilities),
        proposal_sampling_probability=proposal_sampling_probability,
        terminated=environment.terminated,
        truncated=not environment.terminated,
        termination_reason=environment.termination_reason,
        final_state=environment.agent_view().model_dump(mode="json"),
        outcomes=tuple(outcomes),
        final_outcome=evaluator(environment.state) if evaluator is not None else None,
    )


async def branch_interventions(
    environment: ECPAEnvironment,
    observation: DefenseObservation,
    agent_factory: Callable[[], RecoveryAgent],
    continuation_policy: DefensePolicy,
    *,
    seed: int = 0,
    evaluator: Callable[[ScenarioState], OutcomeLabel] | None = None,
) -> tuple[CollectedEpisode, ...]:
    """Branch an identical collected state; preserve real accept/reject failures.

    These enumerated branches are a designed experiment, not samples from the
    ordinary behavior mixture. No live effectful service implements this API.
    """
    episodes = []
    for index, candidate in enumerate(observation.menu):
        branch = environment.clone_for_collection()
        branch_agent = agent_factory()
        episode = await collect_episode(
            branch,
            branch_agent,
            continuation_policy,
            seed=seed + index,
            first_choice=PolicyChoice(candidate.candidate_id),
            first_observation=observation,
            evaluator=evaluator,
        )
        episodes.append(episode)
    return tuple(episodes)
