"""Prospective precision and cost sensitivity; never observed efficacy or power."""

from __future__ import annotations

import math


def zero_adverse_family_sensitivity(
    independent_families: int, *, maximum_loss: float = 0.02, alpha: float = 0.05
) -> dict[str, float | int | str]:
    """Conservative benign-loss sensitivity under iid sampled families.

    Mark a family adverse if *any* paired case has a learned-only failure. With
    zero adverse sampled families, the exact one-sided binomial upper limit on
    the adverse-family probability is 1 - alpha**(1/n). Treating every adverse
    family as a full loss bounds equal-family mean completion loss conservatively.
    This is a planning scenario, not an alternative success test, a sample-size
    necessity theorem, or a claim that benchmark authors sampled iid families.
    """
    if independent_families <= 0 or not 0 < maximum_loss < 1 or not 0 < alpha < 1:
        raise ValueError("positive family count and probabilities strictly inside (0, 1) required")
    return {
        "independent_families": independent_families,
        "assumed_observed_adverse_families": 0,
        "one_sided_upper_adverse_family_probability": 1 - alpha ** (1 / independent_families),
        "families_for_upper_limit_at_most_loss": math.ceil(
            math.log(alpha) / math.log(1 - maximum_loss)
        ),
        "maximum_loss": maximum_loss,
        "interpretation": "conservative iid-family zero-adverse scenario; not guaranteed power",
    }


def prospective_cost(
    *,
    train_families: int,
    evaluation_families: int,
    adapter_seeds: int = 3,
    branch_states_per_parent: int = 2,
    maximum_candidates: int = 4,
    branch_repeats: int = 1,
    presentations: int = 1,
    seconds_per_episode: float = 78.41825,
    reserved_gpus: int = 2,
) -> dict[str, float | int | str | list[float]]:
    """Extrapolate the measured paced pilot, including explicit branch costs.

    Every task has two modes, each with a benign/attacked pair. Four shared arms
    are run once; only the learned arm repeats across adapter seeds. Applying
    comparison duration to full branch continuations is intentionally transparent
    and conservative relative to shorter branches, but not an upper bound.
    """
    counts = (
        train_families,
        evaluation_families,
        adapter_seeds,
        branch_states_per_parent,
        maximum_candidates,
        branch_repeats,
        presentations,
        reserved_gpus,
    )
    if any(count <= 0 for count in counts) or seconds_per_episode <= 0:
        raise ValueError("planning counts and episode cost must be positive")
    parents = train_families * 4 * presentations
    branches = parents * branch_states_per_parent * maximum_candidates * branch_repeats
    evaluation = evaluation_families * 4 * presentations * (4 + adapter_seeds)
    total = parents + branches + evaluation
    hours = total * seconds_per_episode * reserved_gpus / 3600
    return {
        "training_parents": parents,
        "maximum_branch_continuations": branches,
        "comparison_episodes": evaluation,
        "maximum_total_episodes": total,
        "pilot_seconds_per_comparison_episode": seconds_per_episode,
        "reserved_gpu_device_hours_at_pilot_rate": hours,
        "half_to_double_duration_gpu_hour_range": [hours / 2, hours * 2],
        "excluded": "adapter fits, context audit, source review and server startup/idle",
        "interpretation": "prospective rate sensitivity, not a measured cost or guaranteed bound",
    }
