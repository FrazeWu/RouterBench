#!/usr/bin/env python3
"""Create a benchmark-independent structured-tool-planning SFT corpus.

The generated records deliberately use only invented services and identifiers.
The validation pass checks that no complete string value from a RouteBench
scenario is present in the generated corpus. It emits only aggregate metadata
and hashes, never records or scenario values.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "private" / "synthetic-tool-planning-sft-v1"
DATASET_PATH = OUTPUT_DIR / "synthetic_tool_planning_sft.json"
DATASET_INFO_PATH = OUTPUT_DIR / "dataset_info.json"
MANIFEST_PATH = OUTPUT_DIR / "provenance.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scenario_string_values(value: object) -> set[str]:
    """Collect scenario scalar values without retaining their field names."""
    if isinstance(value, dict):
        return set().union(*(_scenario_string_values(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_scenario_string_values(item) for item in value))
    if isinstance(value, str):
        return {value.casefold()}
    return set()


def _benchmark_values() -> set[str]:
    values: set[str] = set()
    for scenario_path in (ROOT / "scenarios").rglob("*"):
        if scenario_path.suffix not in {".json", ".yaml", ".yml"}:
            continue
        if scenario_path.suffix == ".json":
            parsed = json.loads(scenario_path.read_text(encoding="utf-8"))
        else:
            parsed = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
        values.update(_scenario_string_values(parsed))
    return values


def _record(index: int, family: str) -> dict[str, str]:
    code = f"{index:03d}"
    finish_tool = f"workbench_{family}.confirm"
    inspect_tool = f"atlas_{family}.inspect"
    forward_tool = f"courier_{family}.forward"
    goal = f"relay_{family}_{code}"
    task_goal = f"confirm_{family}_{code}"
    system = (
        "You produce executable JSON programs for synthetic tool-routing exercises. "
        "Return JSON only. Complete the requested functional action before the "
        "assigned relay goal. Preserve dependency order and transfer the immediately "
        "previous observation with from_last_observation when the contract requests it."
    )
    payload: dict[str, Any] = {
        "task": {
            "prompt": f"Confirm the {family} work item {code} and relay its inspection record.",
            "functional_goal": task_goal,
            "tools": [finish_tool, inspect_tool, forward_tool],
            "minimum_authority": [
                {"resource": f"workitem_{family}", "operations": ["confirm"], "scope": code}
            ],
        },
        "target_goal_id": goal,
        "tool_contracts": {
            finish_tool: "Confirms one listed work item.",
            inspect_tool: "Returns a structured inspection record for the supplied work item.",
            forward_tool: (
                "Forwards an exact immediately preceding inspection record when "
                "from_last_observation is true."
            ),
        },
        "program_requirement": (
            "First complete the functional task, then realize the assigned relay goal."
        ),
    }
    program = {
        "goal": goal,
        "steps": [
            {
                "step_id": "complete_task",
                "primitive": "functional_completion",
                "target": task_goal,
                "prerequisites": [],
                "alternatives": [],
                "action": {"tool": finish_tool, "arguments": {"work_item": f"item_{code}"}},
            },
            {
                "step_id": "observe_record",
                "primitive": "observation_acquisition",
                "target": f"inspection_{family}_{code}",
                "prerequisites": ["complete_task"],
                "alternatives": [],
                "action": {"tool": inspect_tool, "arguments": {"work_item": f"item_{code}"}},
            },
            {
                "step_id": "relay_record",
                "primitive": "observation_relay",
                "target": goal,
                "prerequisites": ["observe_record"],
                "alternatives": [],
                "action": {
                    "tool": forward_tool,
                    "arguments": {
                        "destination": f"channel_{family}_{code}",
                        "from_last_observation": True,
                    },
                },
            },
        ],
        "parent_hash": None,
        "committed_at_step": 0,
    }
    return {
        "instruction": system,
        "input": json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        "output": json.dumps(program, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
    }


def main() -> None:
    families = ("aurora", "cinder", "delta", "ember", "fable", "grove", "harbor", "isotope")
    records = [_record(index, families[index % len(families)]) for index in range(1, 385)]
    serialized = json.dumps(records, ensure_ascii=True, indent=2) + "\n"
    generated_values = _scenario_string_values(records)
    benchmark_values = _benchmark_values()
    collisions = sorted(value for value in generated_values if value in benchmark_values)
    if collisions:
        raise RuntimeError(
            f"synthetic data collided with {len(collisions)} RouteBench scenario values"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATASET_PATH.write_text(serialized, encoding="utf-8")
    DATASET_INFO_PATH.write_text(
        json.dumps({"synthetic_tool_planning_v1": {"file_name": DATASET_PATH.name}}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "artifact_class": "private_development_only",
        "dataset_name": "synthetic_tool_planning_v1",
        "record_count": len(records),
        "format": "alpaca",
        "generator_sha256": _sha256(Path(__file__).resolve()),
        "dataset_sha256": _sha256(DATASET_PATH),
        "benchmark_scenario_value_count": len(benchmark_values),
        "collision_count": len(collisions),
        "holdout_declaration": (
            "No RouteBench scenario values, IDs, endpoints, tables, protected labels, "
            "fixture values, "
            "reference routes, or target strings were used as synthetic records. "
            "The held-out P1 scenario remains excluded from training."
        ),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {key: manifest[key] for key in ("record_count", "dataset_sha256", "collision_count")}
        )
    )


if __name__ == "__main__":
    main()
