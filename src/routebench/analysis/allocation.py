"""Deterministic metadata-slot allocation for manually authored benchmark cases."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from enum import StrEnum
from itertools import combinations
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from routebench.analysis.compatibility import CompatibilityContract
from routebench.analysis.coverage import FormalSamplingContract, PrimaryCoverageAxis
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

Triple = tuple[ForbiddenEffectFamily, AssetType, ToolSurface]


class PrimaryCaseSlot(BaseModel):
    """Taxonomy labels reserved for one human-authored independent case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_id: str = Field(pattern=r"^rbv1-f[1-8]-\d{3}$")
    family_slot: int = Field(ge=1)
    triple_replication: int = Field(ge=1)
    primary_effect_family: ForbiddenEffectFamily
    primary_asset_type: AssetType
    primary_tool_surface: ToolSurface
    coupling: TaskGoalCoupling
    route_length: RouteLengthBand
    primary_topology: RouteTopology
    primary_permission_dimension: PermissionDimension
    primary_attack_mechanism: AttackMechanism
    target_composition: TargetComposition

    @model_validator(mode="after")
    def validate_slot_identity(self) -> Self:
        effect_number = list(ForbiddenEffectFamily).index(self.primary_effect_family) + 1
        expected_id = f"rbv1-f{effect_number}-{self.family_slot:03d}"
        if self.slot_id != expected_id:
            raise ValueError("slot_id must encode the effect family and family slot")
        return self


_BALANCE_AXES: tuple[tuple[str, type[StrEnum]], ...] = (
    ("coupling", TaskGoalCoupling),
    ("route_length", RouteLengthBand),
    ("primary_topology", RouteTopology),
    ("primary_permission_dimension", PermissionDimension),
    ("primary_attack_mechanism", AttackMechanism),
    ("target_composition", TargetComposition),
)

_ALL_AXIS_NAMES = (
    "primary_effect_family",
    "primary_asset_type",
    "primary_tool_surface",
    *[name for name, _ in _BALANCE_AXES],
)
_AXIS_ORDER = {name: index for index, name in enumerate(_ALL_AXIS_NAMES)}


def _allowed_triples(
    contract: CompatibilityContract, effect: ForbiddenEffectFamily
) -> tuple[Triple, ...]:
    return tuple(
        (effect, asset, tool)
        for asset in AssetType
        for tool in ToolSurface
        if contract.allows(effect, asset, tool)
    )


def _allocate_effect_triples(
    effect: ForbiddenEffectFamily,
    case_count: int,
    contract: CompatibilityContract,
) -> tuple[Triple, ...]:
    triples = _allowed_triples(contract, effect)
    minimum = contract.minimum_primary_cases_per_allowed_triple
    required = len(triples) * minimum
    if required > case_count:
        raise ValueError(
            f"{effect.value} needs {required} primary cases for triple replication, "
            f"but the sampling contract provides {case_count}"
        )

    allocated = [triple for _ in range(minimum) for triple in triples]
    triple_counts: Counter[Triple] = Counter(allocated)
    asset_counts: Counter[AssetType] = Counter(triple[1] for triple in allocated)
    tool_counts: Counter[ToolSurface] = Counter(triple[2] for triple in allocated)
    for extra_index in range(case_count - required):
        chosen = min(
            enumerate(triples),
            key=lambda item: (
                triple_counts[item[1]],
                asset_counts[item[1][1]],
                tool_counts[item[1][2]],
                (item[0] - extra_index) % len(triples),
            ),
        )[1]
        allocated.append(chosen)
        triple_counts[chosen] += 1
        asset_counts[chosen[1]] += 1
        tool_counts[chosen[2]] += 1
    return tuple(allocated)


def _pair_key(
    first_axis: str,
    first_value: StrEnum,
    second_axis: str,
    second_value: StrEnum,
) -> tuple[str, str, str, str]:
    if _AXIS_ORDER[first_axis] <= _AXIS_ORDER[second_axis]:
        return first_axis, first_value.value, second_axis, second_value.value
    return second_axis, second_value.value, first_axis, first_value.value


def _choose_level(
    *,
    axis_name: str,
    enum_type: type[StrEnum],
    context: dict[str, StrEnum],
    marginal_counts: Counter[tuple[str, str]],
    pair_counts: Counter[tuple[str, str, str, str]],
    rotation: int,
) -> StrEnum:
    levels = tuple(enum_type)

    def score(item: tuple[int, StrEnum]) -> tuple[int, int, int, int]:
        index, candidate = item
        candidate_pairs = tuple(
            pair_counts[_pair_key(axis_name, candidate, other_axis, other_value)]
            for other_axis, other_value in context.items()
        )
        return (
            marginal_counts[(axis_name, candidate.value)],
            max(candidate_pairs, default=0),
            sum(candidate_pairs),
            (index - rotation) % len(levels),
        )

    return min(enumerate(levels), key=score)[1]


def _assign_balance_axes(skeletons: tuple[Triple, ...]) -> tuple[dict[str, StrEnum], ...]:
    marginal_counts: Counter[tuple[str, str]] = Counter()
    pair_counts: Counter[tuple[str, str, str, str]] = Counter()
    assignments: list[dict[str, StrEnum]] = []

    for slot_index, (effect, asset, tool) in enumerate(skeletons):
        values: dict[str, StrEnum] = {
            "primary_effect_family": effect,
            "primary_asset_type": asset,
            "primary_tool_surface": tool,
        }
        for axis_index, (axis_name, enum_type) in enumerate(_BALANCE_AXES):
            values[axis_name] = _choose_level(
                axis_name=axis_name,
                enum_type=enum_type,
                context=values,
                marginal_counts=marginal_counts,
                pair_counts=pair_counts,
                rotation=slot_index + axis_index,
            )

        for axis_name, value in values.items():
            marginal_counts[(axis_name, value.value)] += 1
        for (first_axis, first_value), (second_axis, second_value) in combinations(
            values.items(), 2
        ):
            pair_counts[_pair_key(first_axis, first_value, second_axis, second_value)] += 1
        assignments.append(values)
    return tuple(assignments)


def allocate_primary_case_slots(
    sampling: FormalSamplingContract,
    compatibility: CompatibilityContract,
) -> tuple[PrimaryCaseSlot, ...]:
    """Reserve deterministic taxonomy slots without generating scenario content."""
    if sampling.primary_axis is not PrimaryCoverageAxis.EFFECT_FAMILY:
        raise ValueError("v1 slot allocation requires effect_family as the primary axis")
    if compatibility.minimum_required_primary_cases > sampling.formal_primary_cases:
        raise ValueError("the minimum compatible-triple coverage exceeds the formal case budget")

    effect_sequences = {
        effect: _allocate_effect_triples(
            effect,
            sampling.independent_cases_per_stratum,
            compatibility,
        )
        for effect in ForbiddenEffectFamily
    }
    ordered_skeletons = tuple(
        effect_sequences[effect][family_slot - 1]
        for family_slot in range(1, sampling.independent_cases_per_stratum + 1)
        for effect in ForbiddenEffectFamily
    )
    assignments = _assign_balance_axes(ordered_skeletons)

    family_slot_counts: Counter[ForbiddenEffectFamily] = Counter()
    triple_counts: Counter[Triple] = Counter()
    slots: list[PrimaryCaseSlot] = []
    for values in assignments:
        effect = ForbiddenEffectFamily(values["primary_effect_family"].value)
        asset = AssetType(values["primary_asset_type"].value)
        tool = ToolSurface(values["primary_tool_surface"].value)
        triple = effect, asset, tool
        family_slot_counts[effect] += 1
        triple_counts[triple] += 1
        effect_number = list(ForbiddenEffectFamily).index(effect) + 1
        slots.append(
            PrimaryCaseSlot(
                slot_id=f"rbv1-f{effect_number}-{family_slot_counts[effect]:03d}",
                family_slot=family_slot_counts[effect],
                triple_replication=triple_counts[triple],
                primary_effect_family=effect,
                primary_asset_type=asset,
                primary_tool_surface=tool,
                coupling=TaskGoalCoupling(values["coupling"].value),
                route_length=RouteLengthBand(values["route_length"].value),
                primary_topology=RouteTopology(values["primary_topology"].value),
                primary_permission_dimension=PermissionDimension(
                    values["primary_permission_dimension"].value
                ),
                primary_attack_mechanism=AttackMechanism(
                    values["primary_attack_mechanism"].value
                ),
                target_composition=TargetComposition(values["target_composition"].value),
            )
        )
    if len(slots) != sampling.formal_primary_cases:
        raise ValueError("allocated slot count does not match the formal sampling contract")
    return tuple(slots)


def summarize_primary_case_allocation(
    slots: tuple[PrimaryCaseSlot, ...],
    compatibility: CompatibilityContract,
) -> dict[str, object]:
    """Return structural allocation counts and a digest, never scenario content."""
    effect_counts = Counter(slot.primary_effect_family.value for slot in slots)
    triple_counts = Counter(
        (slot.primary_effect_family, slot.primary_asset_type, slot.primary_tool_surface)
        for slot in slots
    )
    triples_meeting_minimum = sum(
        triple_counts[(effect, asset, tool)]
        >= compatibility.minimum_primary_cases_per_allowed_triple
        for effect in ForbiddenEffectFamily
        for asset in AssetType
        for tool in ToolSurface
        if compatibility.allows(effect, asset, tool)
    )
    axis_spreads: dict[str, int] = {}
    for axis_name, enum_type in _BALANCE_AXES:
        counts = Counter(getattr(slot, axis_name).value for slot in slots)
        axis_spreads[axis_name] = max(counts[level.value] for level in enum_type) - min(
            counts[level.value] for level in enum_type
        )
    serialized = json.dumps(
        [slot.model_dump(mode="json") for slot in slots],
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return {
        "status": (
            "complete"
            if triples_meeting_minimum == compatibility.allowed_triple_count
            else "undercovered"
        ),
        "formal_primary_slots": len(slots),
        "per_effect_slots": dict(sorted(effect_counts.items())),
        "allowed_primary_triples": compatibility.allowed_triple_count,
        "triples_meeting_minimum": triples_meeting_minimum,
        "minimum_primary_cases_per_allowed_triple": (
            compatibility.minimum_primary_cases_per_allowed_triple
        ),
        "balance_axis_global_spreads": dict(sorted(axis_spreads.items())),
        "allocation_sha256": hashlib.sha256(serialized).hexdigest(),
    }
