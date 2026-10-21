from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import httpx
import pytest
import yaml

from routebench.contracts import GraphPathSelection
from routebench.evaluation.graph_calibration import GraphCalibrationAttempt
from routebench.planners import PlannerResponseError, load_planner_config
from routebench.scenarios import load_scenario

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "run_matched_routing_pilot", ROOT / "scripts/run_matched_routing_pilot.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
EXAMPLE = ROOT / "examples/capability-routing/pilot_v2/pv2_001_public_timeout_repair"


class Planner:
    def __init__(self, route=(), error=None):
        self.route = route
        self.error = error
        self.closed = False

    async def select_graph_path(self, task, graph, seed):
        if self.error:
            raise self.error
        return GraphPathSelection(edge_ids=self.route)

    async def aclose(self):
        self.closed = True


def test_selected_paths_really_execute_and_close_planner() -> None:
    bundle = load_scenario(EXAMPLE)
    cert = bundle.definition.routes.certificates
    assert cert is not None
    for route, expected in (
        (cert.safe.edge_ids, True),
        (next(iter(cert.attack.values())).edge_ids, False),
    ):
        planner = Planner(route)
        result = asyncio.run(
            MODULE.execute_attempt(bundle, None, 1701, lambda _, planner=planner: planner)
        )
        assert planner.closed
        assert result.status == "valid"
        assert result.result.optimal_path_success == expected
        assert result.result.execution.actions_executed == len(route)
        assert result.result.execution.attack_success is not expected


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (PlannerResponseError("invalid response", "non-json"), "invalid_output"),
        (httpx.ConnectError("offline"), "backend_failure"),
    ],
)
def test_failures_are_classified_without_retry_and_close(error, status) -> None:
    bundle = load_scenario(EXAMPLE)
    planner = Planner(error=error)
    attempt = asyncio.run(
        MODULE.execute_attempt(bundle, None, 1701, lambda _, planner=planner: planner)
    )
    assert attempt.status == status
    assert planner.closed
    assert attempt.failure_kind


def test_summary_does_not_treat_backend_failure_as_assessed_capability_failure() -> None:
    bundle = load_scenario(EXAMPLE)
    seeds = [1701, 1702, 1703, 1704, 1705]
    attempts = [
        GraphCalibrationAttempt(
            scenario_id=bundle.definition.metadata.scenario_id,
            scenario_digest=bundle.digest,
            seed=seed,
            primary_effect_family="f1",
            route_length="l3",
            duration_seconds=1,
            status="invalid_output",
            failure_kind="format_error",
        )
        for seed in seeds
    ]
    summary = MODULE.summarize(attempts, {"base": bundle}, seeds)
    assert summary["conditions"]["base"]["assessed"]
    assert summary["conditions"]["base"]["capable_3_of_5"] is False
    attempts[-1] = GraphCalibrationAttempt(
        scenario_id=bundle.definition.metadata.scenario_id,
        scenario_digest=bundle.digest,
        seed=1705,
        primary_effect_family="f1",
        route_length="l3",
        duration_seconds=1,
        status="backend_failure",
        failure_kind="offline",
    )
    summary = MODULE.summarize(attempts, {"base": bundle}, seeds)
    assert not summary["conditions"]["base"]["assessed"]
    assert summary["conditions"]["base"]["capable_3_of_5"] is None
    with pytest.raises(ValueError, match="matrix"):
        MODULE.summarize(attempts[:-1], {"base": bundle}, seeds)
    with pytest.raises(ValueError, match="matrix"):
        MODULE.summarize([attempts[0]] * 5, {"base": bundle}, seeds)


def test_model_configs_share_planning_contract_and_declared_context() -> None:
    protocol = yaml.safe_load(MODULE.DEFAULT_PROTOCOL.read_text())
    configs = [
        load_planner_config(ROOT / row["planner_config"]).model_dump()
        for row in protocol["models"].values()
    ]
    for config in configs:
        config.pop("model")
        config.pop("endpoint")
        assert (
            config["generation"]["context_window"]
            == protocol["serving_declaration"]["max_model_len"]
        )
        assert config["formal_run"] is False
    assert configs[0] == configs[1]


def test_preflight_rejects_dirty_material_before_any_backend_call(tmp_path: Path) -> None:
    import json

    protocol = yaml.safe_load(MODULE.DEFAULT_PROTOCOL.read_text())
    manifest = {
        "protocol_id": protocol["material_protocol_id"],
        "status": "material_gates_passed",
        "source_split": "dev",
        "source_dirty": True,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="clean frozen"):
        MODULE.preflight(tmp_path, protocol)
