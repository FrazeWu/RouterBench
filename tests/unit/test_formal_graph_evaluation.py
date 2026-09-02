from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from routebench.authorization import NoAuthorizationController
from routebench.contracts import FeedbackMode, GraphPathSelection
from routebench.evaluation.graph_evaluation import (
    FormalGraphAttempt,
    build_formal_graph_summary,
    write_formal_graph_report,
    write_private_formal_graph_attempt_manifest,
)
from routebench.evaluation.graph_selection import GraphSelectionResult, run_graph_selection
from routebench.scenarios import load_scenario

PROJECT_ROOT = Path(__file__).parents[2]
GRAPH_SCENARIO = PROJECT_ROOT / "scenarios/formal_v1/test/rbv1_f1_001_multi_source_reconciliation"


class _FixedGraphPlanner:
    def __init__(self, edge_ids: tuple[str, ...]) -> None:
        self.edge_ids = edge_ids

    async def select_graph_path(
        self, task: object, graph: object, seed: int | None = None
    ) -> GraphPathSelection:
        del task, graph, seed
        return GraphPathSelection(edge_ids=self.edge_ids)


def test_formal_summary_counts_model_and_infrastructure_failures_separately(
    tmp_path: Path,
) -> None:
    bundle = load_scenario(GRAPH_SCENARIO)
    certificates = bundle.definition.routes.certificates
    assert certificates is not None
    reference = asyncio.run(
        run_graph_selection(
            bundle,
            _FixedGraphPlanner(certificates.safe.edge_ids),
            NoAuthorizationController(),
            FeedbackMode.MINIMAL,
            1701,
        )
    )

    def result_for(scenario_id: str, seed: int) -> GraphSelectionResult:
        return GraphSelectionResult(
            scenario_id=scenario_id,
            seed=seed,
            selected_edge_ids=reference.selected_edge_ids,
            selected_authority_footprint=reference.selected_authority_footprint,
            matches_hidden_certificate=True,
            execution=reference.execution,
        )

    attempts: list[FormalGraphAttempt] = []
    for seed in (1701, 1702, 1703):
        attempts.append(
            FormalGraphAttempt(
                scenario_id="case_capable",
                scenario_digest="digest-capable",
                seed=seed,
                primary_effect_family="f1_unauthorized_observation",
                route_length="l2_three_actions",
                duration_seconds=1.0,
                status="valid",
                result=result_for("case_capable", seed),
            )
        )
    for seed in (1704, 1705):
        attempts.append(
            FormalGraphAttempt(
                scenario_id="case_capable",
                scenario_digest="digest-capable",
                seed=seed,
                primary_effect_family="f1_unauthorized_observation",
                route_length="l2_three_actions",
                duration_seconds=1.0,
                status="invalid_output",
                failure_kind="planner_response_invalid",
                response_hash="a" * 64,
            )
        )
    for seed in (1701, 1702, 1703, 1704):
        attempts.append(
            FormalGraphAttempt(
                scenario_id="case_backend",
                scenario_digest="digest-backend",
                seed=seed,
                primary_effect_family="f2_unauthorized_transfer",
                route_length="l1_two_actions",
                duration_seconds=1.0,
                status="valid",
                result=result_for("case_backend", seed),
            )
        )
    attempts.append(
        FormalGraphAttempt(
            scenario_id="case_backend",
            scenario_digest="digest-backend",
            seed=1705,
            primary_effect_family="f2_unauthorized_transfer",
            route_length="l1_two_actions",
            duration_seconds=1.0,
            status="backend_failure",
            failure_kind="planner_backend_error",
        )
    )
    metadata: dict[str, Any] = {
        "planner": {
            "model": "test-model",
            "backend": "vllm",
            "endpoint": "http://127.0.0.1:8000/v1",
            "config_hash": "config-hash",
        },
        "material_passport": {
            "scenario_count": 2,
            "scenario_set_digest": "set-digest",
        },
        "dependency_lock_hash": "lock-hash",
        "git": {"commit": "b" * 40, "dirty": False},
        "model_weight_hash": "c" * 64,
        "rootfs_status": "not_applicable",
        "publishable": True,
    }

    summary = build_formal_graph_summary(
        attempts=tuple(attempts),
        scenario_ids=("case_capable", "case_backend"),
        seeds=(1701, 1702, 1703, 1704, 1705),
        metadata=metadata,
    )

    overall = cast(dict[str, Any], summary["overall"])
    assert overall["assessed_cases"] == 1
    assert overall["capable_cases"] == 1
    assert overall["unassessed_cases"] == 1
    assert overall["invalid_outputs"] == 2
    assert overall["backend_failures"] == 1
    assert overall["optimal_path_successes"] == 3
    assert "cases" not in summary

    failure_manifest = write_private_formal_graph_attempt_manifest(attempts[3], tmp_path, metadata)
    failure_payload = failure_manifest.read_text(encoding="utf-8")
    assert '"raw_planner_response_hash"' in failure_payload
    assert '"raw_planner_response"' not in failure_payload

    report = write_formal_graph_report(summary, tmp_path / "report.md")
    report_text = report.read_text(encoding="utf-8")
    assert "formal_prefix" in report_text
    assert "case_capable" not in report_text
    assert "case_backend" not in report_text
