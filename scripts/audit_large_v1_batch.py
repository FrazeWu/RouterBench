#!/usr/bin/env python3
"""Audit every materialized large-v1 scenario and write aggregate inventory."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

from routebench.runtime.graph_difficulty import audit_hard_candidate_graph
from routebench.scenarios import load_scenario

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "examples" / "capability-routing" / "large_v1"
AUDIT_ROOT = ROOT / "artifacts" / "private" / "large-v1-audits"


def _payload(result: Any) -> dict[str, Any]:
    return {
        "scenario_id": result.base.scenario_id,
        "total_terminal_paths": result.base.total_terminal_paths,
        "functional_paths": result.base.functional_paths,
        "compliant_functional_paths": result.base.compliant_functional_paths,
        "attack_paths": result.base.attack_paths,
        "nonoptimal_paths_no_longer_than_optimum": (
            result.base.nonoptimal_paths_no_longer_than_optimum
        ),
        "optimal_action_count": len(result.base.unique_optimal_edge_ids),
        "optimal_branch_points": result.optimal_branch_points,
        "functional_overprivileged_paths": result.functional_overprivileged_paths,
        "nonfunctional_paths": result.nonfunctional_paths,
        "attack_paths_no_longer_than_optimum": result.attack_paths_no_longer_than_optimum,
        "low_authority_nonfunctional_paths": result.low_authority_nonfunctional_paths,
        "shared_prefix_decoys": result.shared_prefix_decoys,
        "same_tool_decoy_branches": result.same_tool_decoy_branches,
        "same_authority_decoy_branches": result.same_authority_decoy_branches,
        "baselines": asdict(result.baselines),
        "observable_optimum": asdict(result.base.observable_optimum),
        "status": "valid",
    }


def _audit(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    try:
        result = audit_hard_candidate_graph(load_scenario(path))
        payload = _payload(result)
    except Exception as error:
        payload = {
            "scenario_id": path.name,
            "status": "invalid",
            "error_type": type(error).__name__,
            "error": str(error),
        }
    output = AUDIT_ROOT / f"{path.name}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()
    paths = sorted(path for path in SCENARIO_ROOT.iterdir() if path.is_dir())
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(pool.map(_audit, (str(path) for path in paths)))
    results.sort(key=lambda item: str(item["scenario_id"]))
    valid = [item for item in results if item["status"] == "valid"]
    invalid = [item for item in results if item["status"] != "valid"]
    by_split = {"dev": 0, "test": 0}
    by_family: dict[str, int] = {}
    for item in valid:
        scenario = load_scenario(SCENARIO_ROOT / str(item["scenario_id"]))
        split = scenario.definition.metadata.split.value
        by_split[split] += 1
        target = scenario.definition.metadata.primary_target_id
        assert target is not None
        family = scenario.definition.metadata.case_profiles[target].primary_effect_family.value
        by_family[family] = by_family.get(family, 0) + 1
    metric_names = (
        "total_terminal_paths",
        "functional_overprivileged_paths",
        "nonfunctional_paths",
        "attack_paths",
        "optimal_action_count",
        "optimal_branch_points",
        "shared_prefix_decoys",
        "same_tool_decoy_branches",
        "same_authority_decoy_branches",
    )
    minima = {name: min(int(item[name]) for item in valid) for name in metric_names}
    maxima = {name: max(int(item[name]) for item in valid) for name in metric_names}
    index = {
        "status": "valid" if not invalid else "invalid",
        "total_cases": len(results),
        "valid_cases": len(valid),
        "invalid_cases": len(invalid),
        "by_split": by_split,
        "by_effect_family": dict(sorted(by_family.items())),
        "minima": minima,
        "maxima": maxima,
        "all_public_optima_unique": all(
            bool(item["observable_optimum"]["public_rule_unique"])
            and not bool(item["observable_optimum"]["decisive_hidden_information"])
            for item in valid
        ),
        "invalid": invalid,
        "audit_directory": str(AUDIT_ROOT.relative_to(ROOT)),
        "model_evaluation": "not_run",
    }
    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    (AUDIT_ROOT / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(index, indent=2, sort_keys=True))
    if invalid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
