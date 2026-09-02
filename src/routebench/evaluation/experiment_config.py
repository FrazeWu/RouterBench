"""Validated experiment-matrix expansion without invoking a planner or GPU."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from routebench.contracts import AttackCondition, FeedbackMode
from routebench.planners.config import load_planner_config
from routebench.scenarios.loader import ScenarioBundle, load_scenario


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ControllerConfig(_StrictModel):
    schema_version: int = Field(ge=2)
    controller: str = Field(min_length=1)
    context_projection: str = Field(min_length=1)
    feedback_mode: FeedbackMode


class ExperimentStage(_StrictModel):
    stage_id: str = Field(min_length=1)
    controllers: tuple[str, ...] = Field(min_length=1)
    conditions: tuple[AttackCondition, ...] = Field(min_length=1)
    feedback_modes: tuple[FeedbackMode, ...] = Field(min_length=1)


class ExperimentConfig(_StrictModel):
    schema_version: int = Field(ge=2)
    experiment_id: str = Field(min_length=1)
    publishable: bool
    scenario_globs: tuple[str, ...] = Field(min_length=1)
    planners: tuple[str, ...] = Field(min_length=1)
    controllers: tuple[str, ...] = Field(min_length=1)
    conditions: tuple[AttackCondition, ...] = Field(min_length=1)
    feedback_modes: tuple[FeedbackMode, ...] = Field(min_length=1)
    seeds: tuple[int, ...] = Field(min_length=1)
    pairing_keys: tuple[str, ...] = Field(min_length=1)
    stages: tuple[ExperimentStage, ...] = ()

    @model_validator(mode="after")
    def require_paired_identity(self) -> ExperimentConfig:
        required = {
            "scenario",
            "target_goal",
            "planner",
            "controller",
            "feedback_mode",
            "seed",
        }
        missing = required - set(self.pairing_keys)
        if missing:
            raise ValueError(f"pairing_keys omit required identity fields: {sorted(missing)}")
        if len(self.seeds) != len(set(self.seeds)):
            raise ValueError("experiment seeds must be unique")
        stage_ids = [stage.stage_id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("experiment stage IDs must be unique")
        known_conditions = set(self.conditions)
        known_feedback = set(self.feedback_modes)
        for stage in self.stages:
            if not set(stage.conditions).issubset(known_conditions):
                raise ValueError(f"stage {stage.stage_id!r} declares unknown conditions")
            if not set(stage.feedback_modes).issubset(known_feedback):
                raise ValueError(f"stage {stage.stage_id!r} declares unknown feedback modes")
        return self


@dataclass(frozen=True, slots=True)
class ExperimentMatrix:
    config: ExperimentConfig
    workspace_root: Path
    config_path: Path
    config_digest: str


@dataclass(frozen=True, slots=True)
class ExperimentJob:
    """One paired block; its conditions share the same initial attack program."""

    job_id: str
    experiment_id: str
    stage_id: str
    scenario_id: str
    scenario_path: Path
    scenario_digest: str
    target_goal_id: str
    planner_config: Path
    planner_digest: str
    planner_model: str
    controller_config: Path
    controller_digest: str
    controller: str
    feedback_mode: FeedbackMode
    seed: int
    conditions: tuple[AttackCondition, ...]

    def payload(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "experiment_id": self.experiment_id,
            "stage_id": self.stage_id,
            "scenario_id": self.scenario_id,
            "scenario_path": str(self.scenario_path),
            "scenario_digest": self.scenario_digest,
            "target_goal_id": self.target_goal_id,
            "planner_config": str(self.planner_config),
            "planner_digest": self.planner_digest,
            "planner_model": self.planner_model,
            "controller_config": str(self.controller_config),
            "controller_digest": self.controller_digest,
            "controller": self.controller,
            "feedback_mode": self.feedback_mode.value,
            "seed": self.seed,
            "conditions": [condition.value for condition in self.conditions],
        }


def load_experiment_matrix(path: str | Path) -> ExperimentMatrix:
    config_path = Path(path).expanduser().resolve(strict=True)
    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"experiment config must contain a YAML mapping: {config_path}")
    workspace_root = _find_workspace_root(config_path)
    return ExperimentMatrix(
        config=ExperimentConfig.model_validate(raw),
        workspace_root=workspace_root,
        config_path=config_path,
        config_digest=_file_digest(config_path),
    )


def expand_experiment_jobs(matrix: ExperimentMatrix) -> tuple[ExperimentJob, ...]:
    """Create deterministic paired blocks and validate each referenced local config."""
    scenario_bundles = _load_scenarios(matrix)
    planner_paths = tuple(
        _resolve_workspace_path(matrix.workspace_root, item) for item in matrix.config.planners
    )
    controller_paths = tuple(
        _resolve_workspace_path(matrix.workspace_root, item) for item in matrix.config.controllers
    )
    planners = tuple(
        (path, load_planner_config(path), _file_digest(path)) for path in planner_paths
    )
    controllers = tuple(
        (path, _load_controller(path), _file_digest(path)) for path in controller_paths
    )
    jobs: list[ExperimentJob] = []
    stages = matrix.config.stages or (
        ExperimentStage(
            stage_id="unpartitioned",
            controllers=tuple(controller.controller for _, controller, _ in controllers),
            conditions=matrix.config.conditions,
            feedback_modes=matrix.config.feedback_modes,
        ),
    )
    for stage in stages:
        selected_controllers = tuple(
            item for item in controllers if item[1].controller in stage.controllers
        )
        if not selected_controllers:
            raise ValueError(f"stage {stage.stage_id!r} selects no configured controllers")
        for bundle in scenario_bundles:
            for target_goal_id in sorted(bundle.definition.routes.attack):
                for planner_path, planner, planner_digest in planners:
                    for controller_path, controller, controller_digest in selected_controllers:
                        for feedback_mode in stage.feedback_modes:
                            for seed in matrix.config.seeds:
                                identity = {
                                    "experiment_config_digest": matrix.config_digest,
                                    "stage_id": stage.stage_id,
                                    "scenario_id": bundle.definition.metadata.scenario_id,
                                    "scenario_digest": bundle.digest,
                                    "target_goal_id": target_goal_id,
                                    "planner_digest": planner_digest,
                                    "controller_digest": controller_digest,
                                    "feedback_mode": feedback_mode.value,
                                    "seed": seed,
                                }
                                job_id = _canonical_digest(identity)
                                jobs.append(
                                    ExperimentJob(
                                        job_id=job_id,
                                        experiment_id=matrix.config.experiment_id,
                                        stage_id=stage.stage_id,
                                        scenario_id=bundle.definition.metadata.scenario_id,
                                        scenario_path=bundle.root,
                                        scenario_digest=bundle.digest,
                                        target_goal_id=target_goal_id,
                                        planner_config=planner_path,
                                        planner_digest=planner_digest,
                                        planner_model=planner.model,
                                        controller_config=controller_path,
                                        controller_digest=controller_digest,
                                        controller=controller.controller,
                                        feedback_mode=feedback_mode,
                                        seed=seed,
                                        conditions=stage.conditions,
                                    )
                                )
    return tuple(sorted(jobs, key=lambda job: job.job_id))


def write_experiment_plan(
    matrix: ExperimentMatrix, jobs: tuple[ExperimentJob, ...], output: str | Path
) -> Path:
    """Write an immutable planning artifact before any model-backed execution."""
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment_id": matrix.config.experiment_id,
        "experiment_config": str(matrix.config_path),
        "experiment_config_digest": matrix.config_digest,
        "publishable": matrix.config.publishable,
        "jobs": [job.payload() for job in jobs],
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _load_scenarios(matrix: ExperimentMatrix) -> tuple[ScenarioBundle, ...]:
    paths: set[Path] = set()
    for pattern in matrix.config.scenario_globs:
        paths.update(
            path
            for path in matrix.workspace_root.glob(pattern)
            if (path / "scenario.yaml").is_file()
        )
    if not paths:
        raise ValueError("experiment scenario_globs did not match any scenario directories")
    return tuple(
        sorted(
            (load_scenario(path) for path in paths),
            key=lambda bundle: bundle.definition.metadata.scenario_id,
        )
    )


def _load_controller(path: Path) -> ControllerConfig:
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"controller config must contain a YAML mapping: {path}")
    return ControllerConfig.model_validate(raw)


def _resolve_workspace_path(workspace_root: Path, value: str) -> Path:
    path = Path(value)
    resolved = path if path.is_absolute() else workspace_root / path
    return resolved.resolve(strict=True)


def _find_workspace_root(path: Path) -> Path:
    for candidate in (path.parent, *path.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise ValueError(f"could not find a workspace pyproject.toml above {path}")


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
