#!/usr/bin/env python3
"""Create a benchmark-independent variable-depth tool-planning SFT corpus."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from generate_synthetic_planner_sft import (
    ROOT,
    _benchmark_values,
    _scenario_string_values,
)

OUTPUT_DIR = ROOT / "artifacts" / "private" / "synthetic-tool-planning-sft-v2"
DATASET_PATH = OUTPUT_DIR / "synthetic_tool_planning_sft_v2.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(index: int, family: str) -> dict[str, str]:
    code = f"{index:03d}"
    depth = 1 + index % 4
    finish_tool = f"forge_{family}.confirm"
    observe_tools = [f"atlas_{family}.observe_{step}" for step in range(1, depth + 1)]
    forward_tool = f"courier_{family}.forward"
    goal = f"relay_{family}_{code}"
    task_goal = f"confirm_{family}_{code}"
    tools = [finish_tool, *observe_tools, forward_tool]
    contracts = {finish_tool: "Confirms one listed work item."}
    contracts.update(
        {
            tool: "Returns a structured record from the supplied work item or prior observation."
            for tool in observe_tools
        }
    )
    contracts[forward_tool] = "Forwards the immediately preceding observation exactly."
    payload: dict[str, Any] = {
        "task": {
            "prompt": f"Confirm abstract work item {code} and relay the final observation.",
            "functional_goal": task_goal,
            "tools": tools,
            "minimum_authority": [
                {"resource": f"workitem_{family}", "operations": ["confirm"], "scope": code}
            ],
        },
        "target_goal_id": goal,
        "tool_contracts": contracts,
        "program_requirement": (
            "Complete the functional task, traverse every required observation, then relay."
        ),
    }
    steps: list[dict[str, Any]] = [
        {
            "step_id": "complete_task",
            "primitive": "functional_completion",
            "target": task_goal,
            "prerequisites": [],
            "alternatives": [],
            "action": {"tool": finish_tool, "arguments": {"work_item": f"item_{code}"}},
        }
    ]
    prior = "complete_task"
    for step, tool in enumerate(observe_tools, start=1):
        step_id = f"observe_{step}"
        arguments: dict[str, Any] = {"work_item": f"item_{code}"}
        if step > 1:
            arguments = {"from_last_observation": True}
        steps.append(
            {
                "step_id": step_id,
                "primitive": "observation_propagation",
                "target": f"observation_{family}_{code}_{step}",
                "prerequisites": [prior],
                "alternatives": [],
                "action": {"tool": tool, "arguments": arguments},
            }
        )
        prior = step_id
    steps.append(
        {
            "step_id": "relay_record",
            "primitive": "observation_relay",
            "target": goal,
            "prerequisites": [prior],
            "alternatives": [],
            "action": {
                "tool": forward_tool,
                "arguments": {
                    "destination": f"channel_{family}_{code}",
                    "from_last_observation": True,
                },
            },
        }
    )
    return {
        "instruction": (
            "Return one executable JSON program for a synthetic routing assignment. "
            "Complete the functional action first, preserve every dependency, and return JSON only."
        ),
        "input": json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        "output": json.dumps(
            {"goal": goal, "steps": steps, "parent_hash": None, "committed_at_step": 0},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def main() -> None:
    families = ("iris", "jade", "kestrel", "lumen", "mosaic", "nova", "onyx", "prism")
    records = [_record(index, families[index % len(families)]) for index in range(1, 513)]
    benchmark_values = _benchmark_values()
    collisions = sorted(
        value for value in _scenario_string_values(records) if value in benchmark_values
    )
    if collisions:
        raise RuntimeError(f"synthetic data collided with {len(collisions)} scenario values")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATASET_PATH.write_text(
        json.dumps(records, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "dataset_info.json").write_text(
        json.dumps({"synthetic_tool_planning_v2": {"file_name": DATASET_PATH.name}}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "artifact_class": "private_development_only",
        "dataset_name": "synthetic_tool_planning_v2",
        "record_count": len(records),
        "dataset_sha256": _sha256(DATASET_PATH),
        "generator_sha256": _sha256(Path(__file__).resolve()),
        "benchmark_scenario_value_count": len(benchmark_values),
        "collision_count": len(collisions),
        "holdout_declaration": "All records use newly invented abstract tasks and identifiers.",
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    (OUTPUT_DIR / "provenance.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: manifest[k] for k in ("record_count", "collision_count", "dataset_sha256")}
        )
    )


if __name__ == "__main__":
    main()
