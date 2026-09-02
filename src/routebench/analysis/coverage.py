"""Aggregate coverage and precision planning for manually authored cases."""

from __future__ import annotations

import math
from collections import Counter
from enum import StrEnum
from pathlib import Path
from statistics import NormalDist
from typing import Literal, Self, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from routebench.scenarios.loader import ScenarioBundle
from routebench.scenarios.schema import ScenarioSplit
from routebench.scenarios.taxonomy import (
    AssetType,
    AttackMechanism,
    ForbiddenEffectFamily,
    PermissionDimension,
    RouteLengthBand,
    RouteTopology,
    TargetComposition,
    TaskGoalCoupling,
    ToolSurface,
)


class PrimaryCoverageAxis(StrEnum):
    EFFECT_FAMILY = "effect_family"
    ASSET_TYPE = "asset_type"
    COUPLING = "coupling"
    ROUTE_LENGTH = "route_length"
    ROUTE_TOPOLOGY = "route_topology"
    PERMISSION_DIMENSION = "permission_dimension"
    TOOL_SURFACE = "tool_surface"
    ATTACK_MECHANISM = "attack_mechanism"
    TARGET_COMPOSITION = "target_composition"


_AXIS_LEVELS: dict[PrimaryCoverageAxis, type[StrEnum]] = {
    PrimaryCoverageAxis.EFFECT_FAMILY: ForbiddenEffectFamily,
    PrimaryCoverageAxis.ASSET_TYPE: AssetType,
    PrimaryCoverageAxis.COUPLING: TaskGoalCoupling,
    PrimaryCoverageAxis.ROUTE_LENGTH: RouteLengthBand,
    PrimaryCoverageAxis.ROUTE_TOPOLOGY: RouteTopology,
    PrimaryCoverageAxis.PERMISSION_DIMENSION: PermissionDimension,
    PrimaryCoverageAxis.TOOL_SURFACE: ToolSurface,
    PrimaryCoverageAxis.ATTACK_MECHANISM: AttackMechanism,
    PrimaryCoverageAxis.TARGET_COMPOSITION: TargetComposition,
}


class FormalSamplingContract(BaseModel):
    """Frozen independent-case precision target for the formal benchmark."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    confidence_level: float = Field(gt=0.5, lt=1)
    margin_of_error: float = Field(gt=0, lt=0.5)
    expected_rate: float = Field(gt=0, lt=1)
    primary_axis: PrimaryCoverageAxis
    required_strata: tuple[str, ...] = Field(min_length=1)
    independent_cases_per_stratum: int = Field(gt=0)
    formal_primary_cases: int = Field(gt=0)
    independent_unit: Literal["scenario_primary_target"]
    secondary_targets_count_toward_precision: Literal[False]
    legacy_scenarios_count_toward_precision: Literal[False]

    @model_validator(mode="after")
    def validate_frozen_total(self) -> Self:
        expected_levels = {level.value for level in _AXIS_LEVELS[self.primary_axis]}
        if set(self.required_strata) != expected_levels:
            raise ValueError("required_strata must exactly cover the selected primary axis")
        if len(self.required_strata) != len(set(self.required_strata)):
            raise ValueError("required_strata must not contain duplicates")
        estimated = estimate_binomial_cases_per_stratum(
            confidence_level=self.confidence_level,
            margin_of_error=self.margin_of_error,
            expected_rate=self.expected_rate,
        )
        if self.independent_cases_per_stratum != estimated:
            raise ValueError(
                "independent_cases_per_stratum does not match the declared precision inputs"
            )
        expected_total = estimated * len(self.required_strata)
        if self.formal_primary_cases != expected_total:
            raise ValueError("formal_primary_cases does not match strata times cases per stratum")
        return self


def load_sampling_contract(path: str | Path) -> FormalSamplingContract:
    contract_path = Path(path).expanduser().resolve(strict=True)
    with contract_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"sampling contract must contain a YAML mapping: {contract_path}")
    return FormalSamplingContract.model_validate(raw)


def _empty_primary_counts() -> dict[PrimaryCoverageAxis, Counter[str]]:
    return {
        axis: Counter({level.value: 0 for level in enum_type})
        for axis, enum_type in _AXIS_LEVELS.items()
    }


def summarize_benchmark_inventory(bundles: tuple[ScenarioBundle, ...]) -> dict[str, object]:
    """Return only aggregate taxonomy coverage; never expose scenario contents."""
    all_case_counts = _empty_primary_counts()
    formal_primary_counts = _empty_primary_counts()
    profiled_scenarios = 0
    profiled_development_scenarios = 0
    formal_test_scenarios = 0
    legacy_scenarios = 0
    atomic_cases = 0
    compound_cases = 0
    atomic_primary_cases = 0
    compound_primary_cases = 0
    development_primary_cases = 0
    primary_cases = 0

    for bundle in bundles:
        metadata = bundle.definition.metadata
        if metadata.schema_version < 3:
            legacy_scenarios += 1
            continue
        profiled_scenarios += 1
        is_formal = metadata.split is ScenarioSplit.TEST
        if is_formal:
            formal_test_scenarios += 1
        else:
            profiled_development_scenarios += 1
        targets = {target.target_id: target for target in bundle.definition.policy.targets}
        for target_id, profile in metadata.case_profiles.items():
            target = targets[target_id]
            if len(target.effect_goal_ids) == 1:
                atomic_cases += 1
                if target_id == metadata.primary_target_id:
                    primary_cases += 1
                    if is_formal:
                        atomic_primary_cases += 1
                    else:
                        development_primary_cases += 1
            else:
                compound_cases += 1
                if target_id == metadata.primary_target_id:
                    primary_cases += 1
                    if is_formal:
                        compound_primary_cases += 1
                    else:
                        development_primary_cases += 1
            values = {
                PrimaryCoverageAxis.EFFECT_FAMILY: profile.primary_effect_family.value,
                PrimaryCoverageAxis.ASSET_TYPE: profile.primary_asset_type.value,
                PrimaryCoverageAxis.COUPLING: profile.coupling.value,
                PrimaryCoverageAxis.ROUTE_LENGTH: profile.route_length.value,
                PrimaryCoverageAxis.ROUTE_TOPOLOGY: profile.primary_topology.value,
                PrimaryCoverageAxis.PERMISSION_DIMENSION: (
                    profile.primary_permission_dimension.value
                ),
                PrimaryCoverageAxis.TOOL_SURFACE: profile.primary_tool_surface.value,
                PrimaryCoverageAxis.ATTACK_MECHANISM: (profile.primary_attack_mechanism.value),
                PrimaryCoverageAxis.TARGET_COMPOSITION: profile.target_composition.value,
            }
            for axis, value in values.items():
                all_case_counts[axis][value] += 1
                if target_id == metadata.primary_target_id and is_formal:
                    formal_primary_counts[axis][value] += 1

    case_count = atomic_cases + compound_cases
    formal_primary_case_count = atomic_primary_cases + compound_primary_cases
    return {
        "scenario_files": len(bundles),
        "profiled_scenarios": profiled_scenarios,
        "profiled_development_scenarios": profiled_development_scenarios,
        "formal_test_scenarios": formal_test_scenarios,
        "legacy_scenarios": legacy_scenarios,
        "benchmark_cases": case_count,
        "atomic_cases": atomic_cases,
        "compound_cases": compound_cases,
        "formal_primary_cases": formal_primary_case_count,
        "development_primary_cases": development_primary_cases,
        "atomic_primary_cases": atomic_primary_cases,
        "compound_primary_cases": compound_primary_cases,
        "secondary_cases": case_count - primary_cases,
        "formal_primary_coverage": {
            axis.value: dict(sorted(counts.items()))
            for axis, counts in formal_primary_counts.items()
        },
        "all_case_primary_labels": {
            axis.value: dict(sorted(counts.items())) for axis, counts in all_case_counts.items()
        },
    }


def estimate_binomial_cases_per_stratum(
    *, confidence_level: float, margin_of_error: float, expected_rate: float = 0.5
) -> int:
    """Estimate independent cases for a proportion using a normal-approximation bound."""
    if not 0.5 < confidence_level < 1:
        raise ValueError("confidence_level must be between 0.5 and 1")
    if not 0 < margin_of_error < 0.5:
        raise ValueError("margin_of_error must be between 0 and 0.5")
    if not 0 < expected_rate < 1:
        raise ValueError("expected_rate must be between 0 and 1")
    z_score = NormalDist().inv_cdf(0.5 + confidence_level / 2)
    return math.ceil(z_score**2 * expected_rate * (1 - expected_rate) / margin_of_error**2)


def estimate_total_independent_cases(
    *,
    confidence_level: float,
    margin_of_error: float,
    strata: int,
    expected_rate: float = 0.5,
) -> dict[str, int]:
    """Report a precision lower bound without treating seeds as independent cases."""
    if strata < 1:
        raise ValueError("strata must be positive")
    per_stratum = estimate_binomial_cases_per_stratum(
        confidence_level=confidence_level,
        margin_of_error=margin_of_error,
        expected_rate=expected_rate,
    )
    return {
        "independent_cases_per_stratum": per_stratum,
        "strata": strata,
        "independent_case_lower_bound": per_stratum * strata,
    }


def audit_inventory_against_sampling_contract(
    inventory: dict[str, object], contract: FormalSamplingContract
) -> dict[str, object]:
    """Compare aggregate primary-case counts with the frozen sampling contract."""
    coverage = cast(dict[str, object], inventory["formal_primary_coverage"])
    axis_counts = cast(dict[str, int], coverage[contract.primary_axis.value])
    deficits = {
        stratum: max(0, contract.independent_cases_per_stratum - axis_counts[stratum])
        for stratum in contract.required_strata
    }
    primary_cases = cast(int, inventory["formal_primary_cases"])
    return {
        "status": "complete" if not any(deficits.values()) else "incomplete",
        "independent_unit": contract.independent_unit,
        "required_primary_cases": contract.formal_primary_cases,
        "observed_primary_cases": primary_cases,
        "remaining_primary_cases": max(0, contract.formal_primary_cases - primary_cases),
        "per_stratum_deficits": dict(sorted(deficits.items())),
    }
