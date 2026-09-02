"""Held-out template-family contract and aggregate authorship audit."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from routebench.analysis.allocation import PrimaryCaseSlot
from routebench.scenarios.loader import ScenarioBundle
from routebench.scenarios.schema import ScenarioSplit


class TemplateFamilySpec(BaseModel):
    """One semantic workflow family assigned wholly to one split."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    family_id: str = Field(pattern=r"^tf_(dev|test)_[a-z0-9_]+$")
    split: ScenarioSplit
    workflow_class: str = Field(min_length=1)


class BenchmarkSplitContract(BaseModel):
    """Frozen leakage boundary between development and formal evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    split_unit: Literal["scenario_template_family"]
    formal_split: Literal[ScenarioSplit.TEST]
    formal_schema_version: Literal[3]
    formal_primary_cases: int = Field(gt=0)
    development_cases_count_toward_precision: Literal[False]
    legacy_scenarios_count_toward_precision: Literal[False]
    cross_split_family_overlap_allowed: Literal[False]
    renamed_or_parameterized_variant_creates_new_family: Literal[False]
    template_families: tuple[TemplateFamilySpec, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def require_disjoint_nonempty_splits(self) -> Self:
        family_ids = [family.family_id for family in self.template_families]
        if len(family_ids) != len(set(family_ids)):
            raise ValueError("template family IDs must be unique")
        workflow_classes = [family.workflow_class for family in self.template_families]
        if len(workflow_classes) != len(set(workflow_classes)):
            raise ValueError("template family workflow classes must be unique")
        if not self.development_family_ids or not self.formal_family_ids:
            raise ValueError("the split contract must declare development and test families")
        for family in self.template_families:
            expected_prefix = f"tf_{family.split.value}_"
            if not family.family_id.startswith(expected_prefix):
                raise ValueError("template family ID prefix must match its declared split")
        return self

    @property
    def development_family_ids(self) -> tuple[str, ...]:
        return tuple(
            family.family_id
            for family in self.template_families
            if family.split is ScenarioSplit.DEV
        )

    @property
    def formal_family_ids(self) -> tuple[str, ...]:
        return tuple(
            family.family_id
            for family in self.template_families
            if family.split is ScenarioSplit.TEST
        )


class TemplateFamilyAssignment(BaseModel):
    """Held-out template family reserved for one formal metadata slot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_id: str = Field(pattern=r"^rbv1-f[1-8]-\d{3}$")
    split: Literal[ScenarioSplit.TEST]
    template_family_id: str = Field(pattern=r"^tf_test_[a-z0-9_]+$")


def load_split_contract(path: str | Path) -> BenchmarkSplitContract:
    contract_path = Path(path).expanduser().resolve(strict=True)
    with contract_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"split contract must contain a YAML mapping: {contract_path}")
    return BenchmarkSplitContract.model_validate(raw)


def allocate_template_families(
    slots: tuple[PrimaryCaseSlot, ...],
    contract: BenchmarkSplitContract,
) -> tuple[TemplateFamilyAssignment, ...]:
    """Assign formal slots to held-out families with deterministic marginal balance."""
    if len(slots) != contract.formal_primary_cases:
        raise ValueError("slot count does not match the split contract's formal case count")
    family_ids = contract.formal_family_ids
    family_counts: Counter[str] = Counter()
    effect_family_counts: Counter[tuple[str, str]] = Counter()
    axis_family_counts: Counter[tuple[str, str, str]] = Counter()
    assignments: list[TemplateFamilyAssignment] = []

    for slot_index, slot in enumerate(slots):
        axis_values = {
            "asset": slot.primary_asset_type.value,
            "tool": slot.primary_tool_surface.value,
            "coupling": slot.coupling.value,
            "length": slot.route_length.value,
            "topology": slot.primary_topology.value,
            "permission": slot.primary_permission_dimension.value,
            "mechanism": slot.primary_attack_mechanism.value,
            "composition": slot.target_composition.value,
        }

        scored_families: list[tuple[tuple[int, int, int, int, int], str]] = []
        for family_index, candidate_family_id in enumerate(family_ids):
            pair_counts = tuple(
                axis_family_counts[(axis, value, candidate_family_id)]
                for axis, value in axis_values.items()
            )
            scored_families.append(
                (
                    (
                        family_counts[candidate_family_id],
                        effect_family_counts[
                            (slot.primary_effect_family.value, candidate_family_id)
                        ],
                        max(pair_counts, default=0),
                        sum(pair_counts),
                        (family_index - slot_index) % len(family_ids),
                    ),
                    candidate_family_id,
                )
            )
        family_id = min(scored_families)[1]
        assignments.append(
            TemplateFamilyAssignment(
                slot_id=slot.slot_id,
                split=ScenarioSplit.TEST,
                template_family_id=family_id,
            )
        )
        family_counts[family_id] += 1
        effect_family_counts[(slot.primary_effect_family.value, family_id)] += 1
        for axis, value in axis_values.items():
            axis_family_counts[(axis, value, family_id)] += 1
    return tuple(assignments)


def summarize_template_family_allocation(
    assignments: tuple[TemplateFamilyAssignment, ...],
    contract: BenchmarkSplitContract,
) -> dict[str, object]:
    """Return aggregate held-out allocation counts and a reproducibility digest."""
    counts = Counter(assignment.template_family_id for assignment in assignments)
    expected = set(contract.formal_family_ids)
    observed = set(counts)
    serialized = json.dumps(
        [assignment.model_dump(mode="json") for assignment in assignments],
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    spread = max(counts.values(), default=0) - min(
        (counts[family_id] for family_id in expected), default=0
    )
    return {
        "status": (
            "complete"
            if len(assignments) == contract.formal_primary_cases and observed == expected
            else "incomplete"
        ),
        "split_unit": contract.split_unit,
        "formal_split": contract.formal_split.value,
        "formal_primary_assignments": len(assignments),
        "development_template_families": len(contract.development_family_ids),
        "formal_template_families": len(contract.formal_family_ids),
        "formal_family_count_spread": spread,
        "assignment_sha256": hashlib.sha256(serialized).hexdigest(),
    }


def audit_formal_authorship(
    bundles: tuple[ScenarioBundle, ...],
    slots: tuple[PrimaryCaseSlot, ...],
    assignments: tuple[TemplateFamilyAssignment, ...],
    contract: BenchmarkSplitContract,
) -> dict[str, object]:
    """Audit slot and family bindings without returning scenario or slot identities."""
    slot_by_id = {slot.slot_id: slot for slot in slots}
    assignment_by_id = {assignment.slot_id: assignment for assignment in assignments}
    observed_formal_slots: Counter[str] = Counter()
    formal_cases_checked = 0
    development_cases_checked = 0
    unknown_slot_bindings = 0
    duplicate_slot_bindings = 0
    family_split_violations = 0
    family_assignment_mismatches = 0
    taxonomy_assignment_mismatches = 0

    for bundle in bundles:
        metadata = bundle.definition.metadata
        if metadata.schema_version < contract.formal_schema_version:
            continue
        assert metadata.template_family_id is not None
        if metadata.split is ScenarioSplit.DEV:
            development_cases_checked += 1
            family_split_violations += int(
                metadata.template_family_id not in contract.development_family_ids
            )
            continue

        formal_cases_checked += 1
        assert metadata.allocation_slot_id is not None
        observed_formal_slots[metadata.allocation_slot_id] += 1
        if observed_formal_slots[metadata.allocation_slot_id] > 1:
            duplicate_slot_bindings += 1
        slot = slot_by_id.get(metadata.allocation_slot_id)
        assignment = assignment_by_id.get(metadata.allocation_slot_id)
        if slot is None or assignment is None:
            unknown_slot_bindings += 1
            continue
        family_split_violations += int(
            metadata.template_family_id not in contract.formal_family_ids
        )
        family_assignment_mismatches += int(
            metadata.template_family_id != assignment.template_family_id
        )
        primary_target_id = metadata.primary_target_id
        assert primary_target_id is not None
        profile = metadata.case_profiles[primary_target_id]
        taxonomy_assignment_mismatches += int(
            (
                profile.primary_effect_family,
                profile.primary_asset_type,
                profile.primary_tool_surface,
                profile.coupling,
                profile.route_length,
                profile.primary_topology,
                profile.primary_permission_dimension,
                profile.primary_attack_mechanism,
                profile.target_composition,
            )
            != (
                slot.primary_effect_family,
                slot.primary_asset_type,
                slot.primary_tool_surface,
                slot.coupling,
                slot.route_length,
                slot.primary_topology,
                slot.primary_permission_dimension,
                slot.primary_attack_mechanism,
                slot.target_composition,
            )
        )

    planned_slot_ids = set(slot_by_id)
    observed_slot_ids = set(observed_formal_slots) & planned_slot_ids
    missing_formal_slots = len(planned_slot_ids - observed_slot_ids)
    violations = (
        unknown_slot_bindings
        + duplicate_slot_bindings
        + family_split_violations
        + family_assignment_mismatches
        + taxonomy_assignment_mismatches
    )
    status = (
        "incompatible"
        if violations
        else "complete"
        if missing_formal_slots == 0
        else "incomplete"
    )
    return {
        "status": status,
        "formal_cases_checked": formal_cases_checked,
        "development_cases_checked": development_cases_checked,
        "required_formal_cases": contract.formal_primary_cases,
        "missing_formal_slots": missing_formal_slots,
        "unknown_slot_bindings": unknown_slot_bindings,
        "duplicate_slot_bindings": duplicate_slot_bindings,
        "family_split_violations": family_split_violations,
        "family_assignment_mismatches": family_assignment_mismatches,
        "taxonomy_assignment_mismatches": taxonomy_assignment_mismatches,
    }
