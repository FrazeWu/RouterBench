#!/usr/bin/env python3
"""Export the frozen v1 slot assignment as a manual-authoring ledger.

The ledger contains taxonomy and split assignments only.  It deliberately does not
generate task prompts, providers, bindings, graphs, fixtures, routes, or certificates.
Those fields remain human-authored per the capability-routing contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from routebench.analysis import (
    allocate_primary_case_slots,
    allocate_template_families,
    load_compatibility_contract,
    load_sampling_contract,
    load_split_contract,
    summarize_primary_case_allocation,
    summarize_template_family_allocation,
)
from routebench.scenarios import load_scenario

ROOT = Path(__file__).resolve().parents[1]
SAMPLING_PATH = ROOT / "configs/benchmark/v1-sampling.yaml"
COMPATIBILITY_PATH = ROOT / "configs/benchmark/v1-compatibility.yaml"
SPLIT_PATH = ROOT / "configs/benchmark/v1-splits.yaml"
SCENARIO_ROOT = ROOT / "scenarios/formal_v1/test"
OUTPUT_PATH = ROOT / "configs/benchmark/v1-formal-authoring-ledger.json"


def _authored_cases() -> dict[str, str]:
    authored: dict[str, str] = {}
    for scenario_path in sorted(SCENARIO_ROOT.rglob("scenario.yaml")):
        bundle = load_scenario(scenario_path.parent)
        metadata = bundle.definition.metadata
        slot_id = metadata.allocation_slot_id
        if slot_id is not None:
            authored[slot_id] = metadata.scenario_id
    return authored


def _slot_payload(slot: Any) -> dict[str, str | int]:
    return {
        "slot_id": slot.slot_id,
        "family_slot": slot.family_slot,
        "triple_replication": slot.triple_replication,
        "primary_effect_family": slot.primary_effect_family.value,
        "primary_asset_type": slot.primary_asset_type.value,
        "primary_tool_surface": slot.primary_tool_surface.value,
        "coupling": slot.coupling.value,
        "route_length": slot.route_length.value,
        "primary_topology": slot.primary_topology.value,
        "primary_permission_dimension": slot.primary_permission_dimension.value,
        "primary_attack_mechanism": slot.primary_attack_mechanism.value,
        "target_composition": slot.target_composition.value,
    }


def main() -> None:
    sampling = load_sampling_contract(SAMPLING_PATH)
    compatibility = load_compatibility_contract(COMPATIBILITY_PATH)
    split = load_split_contract(SPLIT_PATH)
    slots = allocate_primary_case_slots(sampling, compatibility)
    assignments = allocate_template_families(slots, split)
    authored = _authored_cases()
    assignment_by_slot = {item.slot_id: item for item in assignments}

    entries: list[dict[str, object]] = []
    for slot in slots:
        assignment = assignment_by_slot[slot.slot_id]
        entry: dict[str, object] = {
            **_slot_payload(slot),
            "split": assignment.split.value,
            "template_family_id": assignment.template_family_id,
            "status": "authored" if slot.slot_id in authored else "pending_manual_authoring",
        }
        if slot.slot_id in authored:
            entry["scenario_id"] = authored[slot.slot_id]
        entries.append(entry)

    authored_count = sum(entry["status"] == "authored" for entry in entries)
    payload = {
        "schema_version": 1,
        "kind": "routebench_v1_formal_authoring_ledger",
        "status": "incomplete_manual_authoring",
        "authorship": "manual",
        "scenario_generation": "none",
        "formal_primary_cases": len(entries),
        "authored_formal_cases": authored_count,
        "pending_manual_authoring": len(entries) - authored_count,
        "source_contracts": {
            "sampling": str(SAMPLING_PATH.relative_to(ROOT)),
            "compatibility": str(COMPATIBILITY_PATH.relative_to(ROOT)),
            "split": str(SPLIT_PATH.relative_to(ROOT)),
        },
        "allocation_summary": summarize_primary_case_allocation(slots, compatibility),
        "template_family_summary": summarize_template_family_allocation(assignments, split),
        "entries": entries,
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT_PATH.relative_to(ROOT)),
                "formal_primary_cases": len(entries),
                "authored_formal_cases": authored_count,
                "pending_manual_authoring": len(entries) - authored_count,
                "allocation_sha256": payload["allocation_summary"]["allocation_sha256"],
                "assignment_sha256": payload["template_family_summary"]["assignment_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
