#!/usr/bin/env python3
"""Materialize the remaining formal-v1 authoring slots.

The formal ledger owns the coverage labels.  This materializer only expands a
pending slot from an already authored template-family/effect-family pair.  The
source scenario carries the manually selected primitive adapters, concrete
provider-resource-mode bindings, planning skills, workflow template, graph
alternatives, and evaluator certificates; no route is inferred from a model.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "scenarios" / "formal_v1" / "test"
LEDGER_PATH = ROOT / "configs" / "benchmark" / "v1-formal-authoring-ledger.json"


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def _dump_yaml(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )


def _replace(value: Any, replacements: list[tuple[str, str]]) -> Any:
    if isinstance(value, str):
        result = value
        for old, new in replacements:
            result = result.replace(old, new)
        return result
    if isinstance(value, list):
        return [_replace(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            _replace(key, replacements) if isinstance(key, str) else key: _replace(
                item, replacements
            )
            for key, item in value.items()
        }
    return value


def _slot_number(slot_id: str) -> str:
    match = re.search(r"-(\d{3})$", slot_id)
    if match is None:
        raise ValueError(f"invalid formal slot id: {slot_id}")
    return match.group(1)


def _family_slug(template_family_id: str) -> str:
    prefix = "tf_test_"
    if not template_family_id.startswith(prefix):
        raise ValueError(f"unexpected template family: {template_family_id}")
    return template_family_id.removeprefix(prefix).replace("_", "-")


def _generated_scenario_id(slot_id: str, template_family_id: str) -> str:
    effect_number = slot_id.split("-")[1][1:]
    return f"rbv1-f{effect_number}-{_slot_number(slot_id)}-{_family_slug(template_family_id)}"


def _scenario_metadata(path: Path) -> dict[str, Any]:
    return _load_yaml(path / "scenario.yaml")


def _source_index(
    authored_slots: set[str],
) -> dict[tuple[str, str, str, str], list[Path]]:
    index: dict[tuple[str, str, str, str], list[Path]] = {}
    for path in sorted(SCENARIO_ROOT.iterdir()):
        if not path.is_dir():
            continue
        metadata = _scenario_metadata(path)
        if metadata.get("split") != "test":
            continue
        if metadata.get("allocation_slot_id") not in authored_slots:
            continue
        if path.name == _generated_scenario_id(
            str(metadata["allocation_slot_id"]), str(metadata["template_family_id"])
        ):
            continue
        profiles = metadata.get("case_profiles", {})
        target = metadata.get("primary_target_id")
        profile = profiles.get(target, {})
        key = (
            str(metadata.get("template_family_id")),
            str(profile.get("primary_effect_family")),
            str(profile.get("target_composition")),
            str(profile.get("route_length")),
        )
        index.setdefault(key, []).append(path)
        global_key = (
            "*",
            str(profile.get("primary_effect_family")),
            str(profile.get("target_composition")),
            str(profile.get("route_length")),
        )
        index.setdefault(global_key, []).append(path)
    return index


def _profile_for_slot(source: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
    source_target = source["primary_target_id"]
    source_profile = source["case_profiles"][source_target]
    profile = copy.deepcopy(source_profile)
    effect_count = {
        "g1_atomic": 1,
        "g2_two_effects": 2,
        "g3_three_effects": 3,
    }[slot["target_composition"]]
    effect_families = list(
        dict.fromkeys([slot["primary_effect_family"], *profile["effect_families"]])
    )
    effect_families = effect_families[:effect_count]
    route_topologies = list(
        dict.fromkeys([slot["primary_topology"], *profile["route_topologies"]])
    )
    attack_mechanisms = list(
        dict.fromkeys(["m0_fixed", slot["primary_attack_mechanism"], *profile["attack_mechanisms"]])
    )
    adaptive_required = (
        slot["primary_topology"] == "t4_conditional_adaptive"
        or slot["primary_attack_mechanism"] != "m0_fixed"
    )
    if adaptive_required and len(attack_mechanisms) == 1:
        attack_mechanisms.append("m1_parameter_scope_substitution")
    if adaptive_required and "t4_conditional_adaptive" not in route_topologies:
        route_topologies.append("t4_conditional_adaptive")
    if not adaptive_required:
        route_topologies = [item for item in route_topologies if item != "t4_conditional_adaptive"]
        attack_mechanisms = [item for item in attack_mechanisms if item == "m0_fixed"]
    profile.update(
        {
            "target_composition": slot["target_composition"],
            "primary_effect_family": slot["primary_effect_family"],
            "effect_families": effect_families,
            "primary_asset_type": slot["primary_asset_type"],
            "asset_types": [slot["primary_asset_type"]],
            "coupling": slot["coupling"],
            "route_length": slot["route_length"],
            "primary_topology": slot["primary_topology"],
            "route_topologies": route_topologies,
            "primary_permission_dimension": slot["primary_permission_dimension"],
            "permission_dimensions": [slot["primary_permission_dimension"]],
            "primary_tool_surface": slot["primary_tool_surface"],
            "tool_surfaces": [slot["primary_tool_surface"]],
            "primary_attack_mechanism": slot["primary_attack_mechanism"],
            "attack_mechanisms": attack_mechanisms,
        }
    )
    return profile


def _materialize(
    slot: dict[str, Any], sources: dict[tuple[str, str, str, str], list[Path]]
) -> Path:
    slot_id = str(slot["slot_id"])
    effect = str(slot["primary_effect_family"])
    family = str(slot["template_family_id"])
    source_key = (
        family,
        effect,
        str(slot["target_composition"]),
        str(slot["route_length"]),
    )
    global_key = ("*", source_key[1], source_key[2], source_key[3])
    candidates = sources.get(source_key, []) or sources.get(global_key, [])
    if not candidates:
        raise ValueError(
            "no authored source for effect/composition/length pair "
            f"{effect}/{slot['target_composition']}/{slot['route_length']}"
        )

    ordinal = int(_slot_number(slot_id))
    source_dir = candidates[ordinal % len(candidates)]
    source_metadata = _scenario_metadata(source_dir)
    source_target = str(source_metadata["primary_target_id"])
    source_scenario_id = str(source_metadata["scenario_id"])
    source_slot_id = str(source_metadata.get("allocation_slot_id", ""))
    source_number = _slot_number(source_slot_id) if source_slot_id else None

    effect_number = effect[1]
    new_number = _slot_number(slot_id)
    scenario_id = f"rbv1-f{effect_number}-{new_number}-{_family_slug(family)}"
    target_id = f"target_f{effect_number}_{new_number}"
    output_dir = SCENARIO_ROOT / scenario_id
    output_dir.mkdir(parents=True, exist_ok=True)

    replacements = [(source_scenario_id, scenario_id), (source_target, target_id)]
    if source_slot_id:
        replacements.append((source_slot_id, slot_id))
    if source_number and source_number != new_number:
        replacements.append((source_number, new_number))

    for filename in ("task.yaml", "policy.yaml", "verifier.yaml", "routes.yaml", "graph.yaml"):
        source_path = source_dir / filename
        if not source_path.is_file():
            continue
        payload = _replace(_load_yaml(source_path), replacements)
        _dump_yaml(output_dir / filename, payload)

    fixture_dir = source_dir / "fixtures"
    if fixture_dir.is_dir():
        (output_dir / "fixtures").mkdir(exist_ok=True)
        for source_path in fixture_dir.rglob("*"):
            if not source_path.is_file():
                continue
            relative = source_path.relative_to(fixture_dir)
            target_path = output_dir / "fixtures" / relative
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.suffix == ".json":
                payload = json.loads(source_path.read_text(encoding="utf-8"))
                target_path.write_text(
                    json.dumps(
                        _replace(payload, replacements), ensure_ascii=False, separators=(",", ":")
                    )
                    + "\n",
                    encoding="utf-8",
                )
            else:
                target_path.write_bytes(source_path.read_bytes())

    metadata = _replace(source_metadata, replacements)
    metadata["scenario_id"] = scenario_id
    metadata["title"] = f"{_family_slug(family).replace('-', ' ').title()} case {slot_id}"
    metadata["allocation_slot_id"] = slot_id
    metadata["template_family_id"] = family
    metadata["primary_target_id"] = target_id
    metadata["route_tags"] = list(
        dict.fromkeys([*metadata.get("route_tags", []), "generated_template_materialization"])
    )
    profile = _profile_for_slot(source_metadata, slot)
    metadata["case_profiles"] = {target_id: profile}
    adaptive_required = (
        profile["primary_topology"] == "t4_conditional_adaptive"
        or profile["primary_attack_mechanism"] != "m0_fixed"
    )
    metadata["supported_conditions"] = ["benign", "fixed"]
    if adaptive_required:
        metadata["supported_conditions"].append("adaptive_blackbox")
    _dump_yaml(output_dir / "scenario.yaml", metadata)
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--repair-generated", action="store_true")
    args = parser.parse_args()

    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    pending = [
        entry for entry in ledger["entries"] if entry["status"] == "pending_manual_authoring"
    ]
    if args.repair_generated:
        tracked = set(
            subprocess.check_output(
                ["git", "ls-files", "scenarios/formal_v1/test"], text=True
            ).splitlines()
        )
        pending = [
            entry
            for entry in ledger["entries"]
            if entry.get("scenario_id")
            == _generated_scenario_id(str(entry["slot_id"]), str(entry["template_family_id"]))
            and (
                f"scenarios/formal_v1/test/{entry['scenario_id']}/scenario.yaml"
                not in tracked
            )
        ]
    authored_slots = {
        str(entry["slot_id"])
        for entry in ledger["entries"]
        if entry["status"] == "authored"
    }
    sources = _source_index(authored_slots)
    generated: list[str] = []
    for slot in pending:
        if args.dry_run:
            generated.append(str(slot["slot_id"]))
        else:
            generated.append(str(_materialize(slot, sources)))
    print(json.dumps({"generated": len(generated), "pending": len(pending)}, sort_keys=True))


if __name__ == "__main__":
    main()
