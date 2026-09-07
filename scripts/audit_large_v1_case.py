#!/usr/bin/env python3
"""Run the deterministic hard-graph audit for one materialized large-v1 case."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from routebench.runtime.graph_difficulty import audit_hard_candidate_graph
from routebench.scenarios import load_scenario


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_hard_candidate_graph(load_scenario(args.scenario))
    payload = {
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
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
