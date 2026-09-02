from __future__ import annotations

import json
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from routebench.attacks import program_from_route
from routebench.cli.app import app
from routebench.contracts import AttackProgram, GraphPathSelection
from routebench.scenarios import load_scenario
from routebench.scenarios.schema import CandidateGraph, RouteActionSpec, RouteSpec

PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_SCENARIO = PROJECT_ROOT / "scenarios/data_integrity/dev/delete_customer_records"


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_validate_scenario_command() -> None:
    result = CliRunner().invoke(app, ["scenario", "validate", str(SAMPLE_SCENARIO)])

    assert result.exit_code == 0
    assert result.stdout.startswith("valid data_integrity_archive_expired_trials_dev_001 ")


def test_verify_reference_command_reports_intervention() -> None:
    result = CliRunner().invoke(
        app,
        [
            "scenario",
            "verify-reference",
            str(SAMPLE_SCENARIO),
            "--target-goal",
            "delete_paid_account",
            "--controller",
            "static",
        ],
    )

    assert result.exit_code == 0
    assert '"attack_success": false' in result.stdout
    assert '"intervened": true' in result.stdout


def test_validate_p0_command_checks_full_inventory() -> None:
    result = CliRunner().invoke(app, ["scenario", "validate-p0", str(PROJECT_ROOT / "scenarios")])

    assert result.exit_code == 0
    assert '"scenarios": 60' in result.stdout
    assert '"status": "valid"' in result.stdout


def test_inventory_command_reports_aggregate_counts_without_exposing_contents() -> None:
    result = CliRunner().invoke(app, ["scenario", "inventory", str(PROJECT_ROOT / "scenarios")])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["scenario_files"] == 60
    assert payload["legacy_scenarios"] == 12
    assert payload["benchmark_cases"] == 48
    assert payload["development_primary_cases"] == 8
    assert payload["formal_primary_cases"] == 40


def test_inventory_command_audits_the_frozen_sampling_contract() -> None:
    result = CliRunner().invoke(
        app,
        [
            "scenario",
            "inventory",
            str(PROJECT_ROOT / "scenarios"),
            "--sampling-contract",
            str(PROJECT_ROOT / "configs/benchmark/v1-sampling.yaml"),
            "--compatibility-contract",
            str(PROJECT_ROOT / "configs/benchmark/v1-compatibility.yaml"),
            "--split-contract",
            str(PROJECT_ROOT / "configs/benchmark/v1-splits.yaml"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sampling_contract"]["formal_primary_cases"] == 776
    assert payload["sampling_audit"]["remaining_primary_cases"] == 736
    assert payload["compatibility_audit"]["status"] == "undercovered"
    assert payload["compatibility_audit"]["primary_cases_checked"] == 40
    assert payload["compatibility_audit"]["primary_replication_deficit"] == 432
    assert payload["allocation_plan"]["status"] == "complete"
    assert payload["allocation_plan"]["formal_primary_slots"] == 776
    assert set(payload["allocation_plan"]["per_effect_slots"].values()) == {97}
    assert payload["template_family_plan"]["status"] == "complete"
    assert payload["template_family_plan"]["formal_primary_assignments"] == 776
    assert payload["authorship_audit"]["status"] == "incomplete"
    assert payload["authorship_audit"]["formal_cases_checked"] == 40
    assert payload["authorship_audit"]["taxonomy_assignment_mismatches"] == 0
    assert payload["authorship_audit"]["missing_formal_slots"] == 736


def test_plan_experiment_command_expands_without_running_models() -> None:
    result = CliRunner().invoke(
        app,
        ["experiment", "plan", str(PROJECT_ROOT / "configs/experiments/pilot.yaml")],
    )

    assert result.exit_code == 0
    assert '"jobs": 216' in result.stdout
    assert '"model_runs": 576' in result.stdout


def test_graph_calibration_rejects_held_out_test_scenarios(tmp_path: Path) -> None:
    formal_root = PROJECT_ROOT / "scenarios/formal_v1/test"
    output_root = tmp_path / "graph-calibration"
    result = CliRunner().invoke(
        app,
        [
            "experiment",
            "graph-calibrate",
            str(formal_root),
            "--planner-config",
            str(PROJECT_ROOT / "configs/planners/gpt-oss-20b-ollama-gpu1-p1-v10.yaml"),
            "--seed",
            "1701",
            "--seed",
            "1702",
            "--seed",
            "1703",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code != 0
    assert "held-out" in result.stderr
    assert "cannot" in result.stderr
    assert "calibration" in result.stderr
    assert not output_root.exists()


def test_graph_smoke_rejects_a_held_out_test_scenario() -> None:
    result = CliRunner().invoke(
        app,
        [
            "experiment",
            "graph-smoke",
            str(PROJECT_ROOT / "scenarios/formal_v1/test/rbv1_f1_001_multi_source_reconciliation"),
            "--planner-config",
            str(PROJECT_ROOT / "configs/planners/gpt-oss-20b-ollama-gpu1-p1-v10.yaml"),
            "--seed",
            "1701",
        ],
    )

    assert result.exit_code != 0
    assert "held-out" in result.stderr
    assert "cannot" in result.stderr
    assert "calibration" in result.stderr


def test_graph_calibration_runs_a_development_scenario_matrix(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    development_root = PROJECT_ROOT / "scenarios/graph_planning/dev"
    safe_paths: dict[str, tuple[str, ...]] = {}
    for scenario_path in sorted(development_root.iterdir()):
        bundle = load_scenario(scenario_path)
        graph = bundle.definition.graph
        certificates = bundle.definition.routes.certificates
        assert graph is not None and certificates is not None
        safe_paths[graph.model_dump_json()] = certificates.safe.edge_ids

    class CertificatePlanner:
        async def aclose(self) -> None:
            return None

        async def select_graph_path(
            self, _task: object, graph: CandidateGraph, _seed: int
        ) -> GraphPathSelection:
            return GraphPathSelection(edge_ids=safe_paths[graph.model_dump_json()])

    monkeypatch.setattr(
        "routebench.cli.app.LocalJsonPlanner.create", lambda _config: CertificatePlanner()
    )
    output_root = tmp_path / "graph-development-calibration"
    result = CliRunner().invoke(
        app,
        [
            "experiment",
            "graph-calibrate",
            str(development_root),
            "--planner-config",
            str(PROJECT_ROOT / "configs/planners/gpt-oss-20b-ollama-gpu1-p1-v10.yaml"),
            "--seed",
            "1701",
            "--seed",
            "1702",
            "--seed",
            "1703",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0, result.stderr
    summary = json.loads(
        (output_root / "graph-calibration-summary.json").read_text(encoding="utf-8")
    )
    assert summary["overall"]["planned_attempts"] == 24
    assert summary["overall"]["assessed_cases"] == 8
    assert summary["overall"]["capable_cases"] == 8
    assert len(tuple((output_root / "attempts").rglob("manifest.json"))) == 24


def test_p1_calibration_records_an_invalid_seed_and_continues_batch(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    scenario = PROJECT_ROOT / "scenarios/privacy_access/dev/read_environment_credential"
    bundle = load_scenario(scenario)
    goal = "read_deployment_token"

    class BatchPlanner:
        async def aclose(self) -> None:
            return None

        async def plan_benign_route(self, _task: object, seed: int) -> RouteSpec:
            if seed == 1701:
                return RouteSpec(
                    actions=(
                        RouteActionSpec(tool="environment.read", arguments={"name": "MISSING"}),
                    )
                )
            return bundle.definition.routes.safe

        async def commit_attack_program(
            self, _task: object, target: str, _seed: int
        ) -> AttackProgram:
            return program_from_route(target, bundle.definition.routes.attack[target])

    monkeypatch.setattr(
        "routebench.cli.app.LocalJsonPlanner.create", lambda _config: BatchPlanner()
    )
    output_root = tmp_path / "p1-batch"
    result = CliRunner().invoke(
        app,
        [
            "experiment",
            "p1-calibrate",
            str(scenario),
            "--target-goal",
            goal,
            "--planner-config",
            str(PROJECT_ROOT / "configs/planners/gpt-oss-20b-ollama-gpu1-p1-v4.yaml"),
            "--seed",
            "1701",
            "--seed",
            "1702",
            "--seed",
            "1703",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0
    summary = json.loads((output_root / "calibration-summary.json").read_text())
    assert summary["invalid_attempts"] == 1
    assert summary["valid_attempts"] == 2
    assert summary["benign_capable"] is None
    assert summary["autonomous_attack_capable"] is True
    failure = json.loads(
        (
            output_root
            / "privacy_access_read_environment_credential_dev_001_read_deployment_token_1701"
            / "manifest.json"
        ).read_text()
    )
    assert failure["failure_kind"] == "planner_response_invalid"


def test_guided_controller_diagnostic_records_controller_results_without_capability_claim(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    scenario = PROJECT_ROOT / "scenarios/privacy_access/dev/read_environment_credential"
    goal = "read_deployment_token"

    class GuidedPlanner:
        async def aclose(self) -> None:
            return None

        async def commit_guided_attack_program(
            self, _task: object, target: str, guide: RouteSpec, _seed: int
        ) -> AttackProgram:
            return program_from_route(target, guide)

    monkeypatch.setattr(
        "routebench.cli.app.LocalJsonPlanner.create", lambda _config: GuidedPlanner()
    )
    output_root = tmp_path / "guided-controller"
    result = CliRunner().invoke(
        app,
        [
            "experiment",
            "guided-controller-diagnostic",
            str(scenario),
            "--target-goal",
            goal,
            "--planner-config",
            str(PROJECT_ROOT / "configs/planners/gpt-oss-20b-ollama-gpu1-p1-v4.yaml"),
            "--controller",
            "static",
            "--seed",
            "1701",
            "--seed",
            "1702",
            "--seed",
            "1703",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0
    summary = json.loads((output_root / "diagnostic-summary.json").read_text())
    assert summary["condition"] == "guided_controller_diagnostic"
    assert summary["attack_successes"] == 0
    assert summary["interventions"] == 3
    assert "route_execution_capable" not in summary


def test_guided_controller_pair_diagnostic_reuses_one_program_per_seed(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    scenario = PROJECT_ROOT / "scenarios/privacy_access/dev/read_environment_credential"
    goal = "read_deployment_token"

    class GuidedPlanner:
        async def aclose(self) -> None:
            return None

        async def commit_guided_attack_program(
            self, _task: object, target: str, guide: RouteSpec, _seed: int
        ) -> AttackProgram:
            return program_from_route(target, guide)

    monkeypatch.setattr(
        "routebench.cli.app.LocalJsonPlanner.create", lambda _config: GuidedPlanner()
    )
    output_root = tmp_path / "guided-controller-pair"
    result = CliRunner().invoke(
        app,
        [
            "experiment",
            "guided-controller-pair-diagnostic",
            str(scenario),
            "--target-goal",
            goal,
            "--planner-config",
            str(PROJECT_ROOT / "configs/planners/gpt-oss-20b-ollama-gpu1-p1-v4.yaml"),
            "--seed",
            "1701",
            "--seed",
            "1702",
            "--seed",
            "1703",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0
    summary = json.loads((output_root / "diagnostic-summary.json").read_text())
    assert summary["condition"] == "guided_controller_pair_diagnostic"
    assert summary["static_attack_successes"] == 0
    assert summary["path_state_attack_successes"] == 0
    for attempt in summary["attempts"]:
        assert attempt["program_hash"] == attempt["static"]["initial_program_hash"]
        assert attempt["program_hash"] == attempt["path_state"]["initial_program_hash"]
