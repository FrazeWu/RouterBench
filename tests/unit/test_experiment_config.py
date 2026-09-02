from __future__ import annotations

import json
from pathlib import Path

from routebench.evaluation.experiment_config import (
    expand_experiment_jobs,
    load_experiment_matrix,
    write_experiment_plan,
)
from routebench.storage.manifests import build_private_run_metadata, file_sha256

PROJECT_ROOT = Path(__file__).parents[2]


def test_pilot_config_expands_to_stable_paired_blocks(tmp_path: Path) -> None:
    matrix = load_experiment_matrix(PROJECT_ROOT / "configs/experiments/pilot.yaml")

    first = expand_experiment_jobs(matrix)
    second = expand_experiment_jobs(matrix)

    assert len(first) == 216
    assert first == second
    assert len({job.job_id for job in first}) == len(first)
    assert {job.scenario_id for job in first}
    assert sum(job.stage_id == "p1_calibration" for job in first) == 72
    assert sum(job.stage_id == "p2_core" for job in first) == 144
    assert all(len(job.conditions) in {2, 3} for job in first)

    plan = write_experiment_plan(matrix, first, tmp_path / "pilot-plan.json")
    payload = json.loads(plan.read_text(encoding="utf-8"))
    assert payload["experiment_id"] == "routebench-pilot-v2"
    assert len(payload["jobs"]) == 216
    assert payload["jobs"][0]["job_id"] == first[0].job_id


def test_private_metadata_declares_missing_formal_requirements() -> None:
    metadata = build_private_run_metadata(
        workspace_root=PROJECT_ROOT,
        scenario_digest="a" * 64,
        planner_config=PROJECT_ROOT / "configs/planners/qwen2.5-7b-ollama-gpu1.yaml",
        controller_config=PROJECT_ROOT / "configs/controllers/path-state.yaml",
        controller="path-state",
        feedback_mode="minimal",
        model="qwen2.5:7b",
        formal_run=False,
    )

    assert metadata["scenario_digest"] == "a" * 64
    assert metadata["dependency_lock_hash"] == file_sha256(PROJECT_ROOT / "uv.lock")
    assert metadata["publishable"] is False
    assert "model_weight_hash" in metadata["missing_formal_fields"]
    assert "rootfs_hash" in metadata["missing_formal_fields"]
    assert "formal_run_required" in metadata["missing_formal_fields"]
