from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

SCRIPT = Path(__file__).parents[2] / "scripts/report_v13_evidence.py"
SPEC = importlib.util.spec_from_file_location("v13_evidence_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(root: Path) -> None:
    stratum = {"primary_effect_family": "f1", "route_length": "l1"}
    metadata = {
        "git": {"dirty": False},
        "publishable": True,
        "material_passport": {"scenario_digests": {"case": "digest"}},
        "planner": {"formal_run": True},
    }
    overall = {
        "optimal_path_successes": 5,
        "functional_successes": 5,
        "policy_compliant_selections": 5,
        "attack_path_selections": 0,
        "functional_but_nonoptimal": 0,
        "policy_noncompliant_selections": 0,
        "nonfunctional_valid_selections": 0,
        "total_cases": 1,
        "planned_attempts": 5,
        "assessed_attempts": 5,
        "assessed_cases": 1,
        "backend_failures": 0,
        "unassessed_cases": 0,
        "valid_attempts": 5,
        "invalid_outputs": 0,
        "capable_cases": 1,
        "not_capable_cases": 0,
    }
    summary = {
        "seeds": list(MODULE.SEEDS),
        "minimum_successes": 3,
        "scope": {"evaluated_cases": 1},
        "overall": overall,
        "by_primary_effect_family": {"f1": overall},
        "by_route_length": {"l1": overall},
    }
    _save(root / "formal-graph-summary.json", summary)
    _save(root / "run-manifest.json", {"metadata": metadata})
    for seed in MODULE.SEEDS:
        _save(
            root / f"attempts/case_{seed}/manifest.json",
            {
                "scenario_id": "case",
                "scenario_digest": "digest",
                "seed": seed,
                "status": "valid",
                "metadata": metadata,
                **stratum,
                "outcomes": {
                    "optimal_path_success": True,
                    "functional_success": True,
                    "policy_compliance": True,
                    "attack_success": False,
                },
            },
        )


def test_validates_attempts_against_summary_and_builds_case_matrix(tmp_path: Path) -> None:
    _fixture(tmp_path)
    run = MODULE.load_run("fixture", tmp_path, 1)
    np.testing.assert_array_equal(MODULE.matrix(run, ["case"]), [[1, 1, 1, 0, 1]])
    assert run.diagnostics["partition"] == {"optimal": 5}
    assert len(run.record_digest) == 64


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("seed", 42, "unexpected seed"),
        ("scenario_digest", "incorrect", "digest mismatch"),
        ("status", "backend_failure", "backend failure/status"),
        ("scenario_id", "unexpected", "unexpected case"),
    ],
)
def test_rejects_corrupt_record(tmp_path: Path, field: str, value: Any, message: str) -> None:
    _fixture(tmp_path)
    path = tmp_path / "attempts/case_1701/manifest.json"
    record = json.loads(path.read_text())
    record[field] = value
    _save(path, record)
    with pytest.raises(ValueError, match=message):
        MODULE.load_run("fixture", tmp_path, 1)


def test_rejects_non_boolean_and_aggregate_mismatch(tmp_path: Path) -> None:
    _fixture(tmp_path)
    path = tmp_path / "attempts/case_1701/manifest.json"
    record = json.loads(path.read_text())
    record["outcomes"]["optimal_path_success"] = "false"
    _save(path, record)
    with pytest.raises(ValueError, match="non-boolean"):
        MODULE.load_run("fixture", tmp_path, 1)
    record["outcomes"]["optimal_path_success"] = False
    _save(path, record)
    with pytest.raises(ValueError, match="aggregate mismatch optimal"):
        MODULE.load_run("fixture", tmp_path, 1)


def test_rejects_missing_and_duplicate_seed(tmp_path: Path) -> None:
    _fixture(tmp_path)
    path = tmp_path / "attempts/case_1701/manifest.json"
    original = json.loads(path.read_text())
    path.unlink()
    with pytest.raises(ValueError, match="missing seed"):
        MODULE.load_run("fixture", tmp_path, 1)
    _save(path, original)
    _save(tmp_path / "attempts/duplicate/manifest.json", original)
    with pytest.raises(ValueError, match="duplicate case/seed"):
        MODULE.load_run("fixture", tmp_path, 1)


def test_invalid_output_is_assessed_capability_failure(tmp_path: Path) -> None:
    _fixture(tmp_path)
    path = tmp_path / "attempts/case_1701/manifest.json"
    record = json.loads(path.read_text())
    record["status"] = "invalid_output"
    record.pop("outcomes")
    _save(path, record)
    path = tmp_path / "formal-graph-summary.json"
    summary = json.loads(path.read_text())
    for counts in (
        summary["overall"],
        summary["by_primary_effect_family"]["f1"],
        summary["by_route_length"]["l1"],
    ):
        for key in (
            "optimal_path_successes",
            "functional_successes",
            "policy_compliant_selections",
            "valid_attempts",
        ):
            counts[key] = 4
        counts["invalid_outputs"] = 1
    _save(path, summary)
    run = MODULE.load_run("fixture", tmp_path, 1)
    np.testing.assert_array_equal(MODULE.matrix(run, ["case"]), [[0.8, 0.8, 0.8, 0, 1]])
    assert run.diagnostics["partition"]["invalid_output"] == 1


def test_bootstrap_constant_and_reproducible_case_clusters() -> None:
    values = np.array([[1, 0], [1, 0]])
    np.testing.assert_array_equal(
        MODULE.bootstrap(values, "constant", 100), [[100, 100, 100], [0, 0, 0]]
    )
    varied = np.array([[0.2, 1], [-0.4, -1], [0.6, 0]])
    np.testing.assert_array_equal(
        MODULE.bootstrap(varied, "same", 100), MODULE.bootstrap(varied, "same", 100)
    )
    with pytest.raises(ValueError, match="empty"):
        MODULE.bootstrap(np.empty((0, 2)), "empty", 100)


def test_refuses_overwriting_existing_artifact(tmp_path: Path) -> None:
    path = tmp_path / "result.md"
    MODULE.write_new(path, "original")
    with pytest.raises(FileExistsError):
        MODULE.write_new(path, "replacement")
    assert path.read_text() == "original\n"


def test_inventory_separates_audited_generation_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "formal-v13-diagnostic"
    _fixture(root)
    path = root / "run-manifest.json"
    manifest = json.loads(path.read_text())
    manifest["metadata"]["planner"]["protocol_version"] = "v13"
    _save(path, manifest)
    lines = MODULE.inventory(tmp_path, {root}, {root})
    row = next(line for line in lines if line.startswith("| formal-v13-diagnostic |"))
    assert "attempt-audited diagnostic only" in row
    assert "canonical attempt-audited" not in row


def test_pairing_requires_matching_case_ids_strata_and_contracts(tmp_path: Path) -> None:
    _fixture(tmp_path)
    left = MODULE.load_run("left", tmp_path, 1)
    left.metadata["planner"].update(
        {
            "generation": {"temperature": 0},
            "graph_selection_interface": "incremental_edge",
            "anonymize_graph_labels": True,
            "graph_incremental_static_prefix": True,
            "protocol_version": "v13",
            "graph_presentation_seeded_permutation": True,
        }
    )
    left.metadata["formal_evaluation_contract"] = {"controller": "none"}
    right = deepcopy(left)
    right.name = "right"
    lines = MODULE.paired(left, right, 100)
    assert len(lines) == 3
    assert all("+0.00 [+0.00, +0.00]" in row for row in lines)
    right.cases["case"]["stratum"] = ("different", "l1")
    with pytest.raises(ValueError, match="paired strata"):
        MODULE.paired(left, right, 100)
    right = deepcopy(left)
    right.cases["other"] = right.cases.pop("case")
    with pytest.raises(ValueError, match="paired case sets"):
        MODULE.paired(left, right, 100)
    right = deepcopy(left)
    right.metadata["planner"]["generation"]["temperature"] = 1
    with pytest.raises(ValueError, match="planner contract"):
        MODULE.paired(left, right, 100)
    right = deepcopy(left)
    right.metadata["material_passport"]["scenario_digests"]["case"] = "changed"
    with pytest.raises(ValueError, match="case material"):
        MODULE.paired(left, right, 100)
