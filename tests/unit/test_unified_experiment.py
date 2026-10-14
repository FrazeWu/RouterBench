from __future__ import annotations

import json
from pathlib import Path

from routebench.evaluation.unified import (
    build_unified_report,
    collect_result_summaries,
    validate_scenarios,
    write_unified_report,
)

ROOT = Path(__file__).parents[2]


def test_unified_validation_audits_one_graph_scenario() -> None:
    records = validate_scenarios(
        ROOT / "scenarios/graph_planning/dev/rbdv_f1_001_resource_inventory", limit=1
    )

    assert len(records) == 1
    assert records[0].status == "valid_graph"
    assert records[0].terminal_paths is not None


def test_unified_report_collects_aggregate_results_without_raw_content(tmp_path: Path) -> None:
    summary_root = tmp_path / "run"
    summary_root.mkdir()
    (summary_root / "formal-graph-summary.json").write_text(
        json.dumps(
            {
                "scope": {"kind": "formal_prefix", "evaluated_cases": 1},
                "overall": {
                    "planned_attempts": 5,
                    "valid_attempts": 5,
                    "backend_failures": 0,
                    "invalid_outputs": 0,
                    "optimal_path_successes": 4,
                    "capable_cases": 1,
                    "functional_successes": 5,
                    "policy_compliant_selections": 5,
                    "attack_path_selections": 0,
                },
                "metadata": {
                    "planner": {"model": "test-model", "protocol_version": "v13"},
                    "inference_runtime": {"implementation": "fake"},
                    "git": {"commit": "abc"},
                },
            }
        ),
        encoding="utf-8",
    )

    results = collect_result_summaries(tmp_path, scope_kind=None, protocol_version=None)
    report = build_unified_report((), results)
    json_path, markdown_path = write_unified_report(report, tmp_path / "out")

    assert results[0]["model"] == "test-model"
    assert results[0]["optimal_rate"] == 0.8
    assert "test-model" in markdown_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["results"]["summaries_found"] == 1


def test_unified_result_scope_excludes_diagnostic_prefixes(tmp_path: Path) -> None:
    for index, scope in enumerate(("formal_prefix", "complete_formal_benchmark")):
        run = tmp_path / f"run-{index}"
        run.mkdir()
        (run / "formal-graph-summary.json").write_text(
            json.dumps(
                {
                    "scope": {"kind": scope, "evaluated_cases": 776 if index else 96},
                    "overall": {"planned_attempts": 5, "backend_failures": 0},
                    "metadata": {
                        "planner": {"model": f"model-{index}", "protocol_version": "v13"}
                    },
                }
            ),
            encoding="utf-8",
        )

    formal = collect_result_summaries(tmp_path)
    assert len(formal) == 1
    assert formal[0]["scope"] == "complete_formal_benchmark"
    all_scopes = collect_result_summaries(
        tmp_path, scope_kind=None, protocol_version=None
    )
    assert len(all_scopes) == 2
