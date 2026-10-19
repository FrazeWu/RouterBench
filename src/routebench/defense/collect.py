"""Deterministic, probability-accounted ECPA data collection helpers."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from routebench.defense.ecpa import (
    DefenseDecision,
    DefenseObservation,
    ECPAEnvironment,
    ECPAStep,
)
from routebench.defense.traces import ECPARewardSpec, ECPATransition, build_transitions
from routebench.scenarios.schema import RouteActionSpec


class CollectionMode(StrEnum):
    UNIFORM = "uniform"
    DIAGNOSTIC_GUIDED = "diagnostic_guided"


class DefensePolicy(Protocol):
    def decide(
        self,
        observation: DefenseObservation,
        replacements: tuple[RouteActionSpec, ...] = (),
    ) -> DefenseDecision: ...


@dataclass(frozen=True, slots=True)
class DefenseProposal:
    """One proposal and its registered replacement menu."""

    stratum: str
    action: RouteActionSpec
    replacements: tuple[RouteActionSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class SampledProposal:
    proposal: DefenseProposal
    behavior_probability: float


@dataclass(frozen=True, slots=True)
class CollectedEpisode:
    steps: tuple[ECPAStep, ...]
    transitions: tuple[ECPATransition, ...]


def sample_proposals(
    proposals: tuple[DefenseProposal, ...],
    *,
    budget: int,
    mode: CollectionMode,
    diagnostic_scores: dict[str, float] | None = None,
    seed: int = 0,
) -> tuple[SampledProposal, ...]:
    """Sample a fixed-budget collection mixture and record its true probabilities."""

    if not proposals:
        raise ValueError("proposal collection cannot be empty")
    if budget <= 0:
        raise ValueError("collection budget must be positive")
    scores = diagnostic_scores or {}
    if any(score < 0 for score in scores.values()):
        raise ValueError("diagnostic scores must be nonnegative")
    count = len(proposals)
    if mode is CollectionMode.UNIFORM:
        probabilities = [1.0 / count] * count
    else:
        weights = [max(scores.get(item.stratum, 0.0), 0.1) for item in proposals]
        total = sum(weights)
        diagnostic = [weight / total for weight in weights]
        probabilities = [0.5 / count + 0.5 * value for value in diagnostic]
    rng = random.Random(seed)
    sampled_indices = rng.choices(range(count), weights=probabilities, k=budget)
    return tuple(
        SampledProposal(
            proposal=proposals[index], behavior_probability=probabilities[index]
        )
        for index in sampled_indices
    )


async def collect_episode(
    environment: ECPAEnvironment,
    proposals: tuple[SampledProposal, ...],
    policy: DefensePolicy,
    *,
    reward_spec: ECPARewardSpec | None = None,
) -> CollectedEpisode:
    """Run sampled proposals through the environment and materialize transitions."""

    steps: list[ECPAStep] = []
    probabilities: list[float] = []
    for sampled in proposals:
        observation = await environment.observe(sampled.proposal.action)
        decision = policy.decide(observation, sampled.proposal.replacements)
        step = await environment.step(
            sampled.proposal.action,
            decision,
            registered_replacements=sampled.proposal.replacements,
        )
        steps.append(step)
        probabilities.append(sampled.behavior_probability)
        if environment.terminated:
            break
    frozen_steps = tuple(steps)
    return CollectedEpisode(
        steps=frozen_steps,
        transitions=build_transitions(
            frozen_steps,
            reward_spec=reward_spec,
            behavior_probabilities=tuple(probabilities),
        ),
    )
