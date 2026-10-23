"""Matched split evaluation and tuning-only comparator selection.

Private outcomes never enter a policy. These kernels neither approve sources
nor authorize a formal run; the CLI owns frozen-source and measured-phase gates.
"""

from __future__ import annotations

import json
import random
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import Field

from routebench.defense.agent import JsonRecoveryAgent
from routebench.defense.branching import RecordedRollout
from routebench.defense.collect import DefensePolicy, collect_episode
from routebench.defense.contracts import content_hash
from routebench.defense.development import SimulatedApprover
from routebench.defense.ecpa import ECPAEnvironment
from routebench.defense.evaluation import MenuCoverage, episode_metrics
from routebench.defense.freeze import SHARED_ARMS
from routebench.defense.lora import file_digest, validate_adapter
from routebench.defense.pilot import UnguardedSimulatorReference
from routebench.defense.protocol import PairedResult, paired_family_comparison
from routebench.defense.relay import StagedResponseRelay
from routebench.defense.study import (
    FrozenStudy,
    load_training_phase,
    rollout_record,
    write_exclusive,
)
from routebench.scenarios.schema import StrictModel

EvaluationSplit = Literal["tune", "calibration", "test"]


class ComparisonCase(StrictModel):
    task_id: str
    semantic_family: str
    mode: Literal["text", "structured"]
    attacked: bool
    arm: str
    adapter_seed: int | None
    episode_seed: int

    @property
    def case_id(self) -> str:
        return "comparison-" + content_hash(self.model_dump(mode="json"))[:24]

    @property
    def pair_key(self) -> tuple[str, str, bool]:
        return self.task_id, self.mode, self.attacked


class ComparisonRow(StrictModel):
    case: ComparisonCase
    completed: bool
    safe_recovery: bool
    violation: bool
    attack_success: bool
    truncated: bool
    termination_reason: str | None
    online_budget_units: int = Field(ge=0)
    agent_calls: int = Field(ge=0)
    selector_calls: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    menu_coverage: MenuCoverage
    rollout_file: str
    rollout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass
class PolicySession:
    policy: DefensePolicy
    calls: list[dict[str, object]] = field(default_factory=list)


def comparison_arms(study: FrozenStudy) -> tuple[str, ...]:
    return (*SHARED_ARMS, *(f"compact_lora_seed_{seed}" for seed in study.spec.adapter_seeds))


def comparison_schedule(study: FrozenStudy, split: EvaluationSplit) -> list[ComparisonCase]:
    """Randomized arm blocks allow one model load per arm; no outcome ordering."""
    if split not in {"tune", "calibration", "test"}:
        raise ValueError("comparison accepts only held-out study splits")
    selected = [
        (index, task) for index, task in enumerate(study.tasks) if task.entry.split == split
    ]
    if not selected:
        raise ValueError("comparison requires the declared split sources")
    arms = list(comparison_arms(study))
    random.Random(study.spec.arm_order_seed + ("tune", "calibration", "test").index(split)).shuffle(
        arms
    )
    rows = []
    for arm in arms:
        seed = int(arm.removeprefix("compact_lora_seed_")) if arm not in SHARED_ARMS else None
        for index, task in selected:
            for mode_index, mode in enumerate(study.spec.modes):
                for attacked in (False, True):
                    rows.append(
                        ComparisonCase(
                            task_id=task.entry.task_id,
                            semantic_family=task.entry.semantic_family,
                            mode=mode,
                            attacked=attacked,
                            arm=arm,
                            adapter_seed=seed,
                            episode_seed=study.spec.episode_seed
                            + index * len(study.spec.modes)
                            + mode_index,
                        )
                    )
    return rows


async def run_comparison(
    study: FrozenStudy,
    split: EvaluationSplit,
    output: Path,
    agent_factory: Callable[[StagedResponseRelay], JsonRecoveryAgent],
    policy_session: Callable[[str], AbstractContextManager[PolicySession]],
    *,
    check: Callable[[], None],
) -> dict[str, Any]:
    """Execute all frozen cases, retaining agent failures in their denominators."""
    schedule = comparison_schedule(study, split)
    output.mkdir(exist_ok=False)
    common = {
        "source_revision": study.revision,
        "formal_protocol_id": study.protocol_id,
        "frozen_manifest_digest": study.manifest_digest,
        "split": split,
    }
    write_exclusive(
        output / "schedule.json",
        {**common, "cases": [case.model_dump(mode="json") for case in schedule]},
    )
    tasks = {task.entry.task_id: task for task in study.tasks}
    rows = []
    # A context per arm also bounds compact-model allocation and teardown cost.
    for arm in dict.fromkeys(case.arm for case in schedule):
        check()
        with policy_session(arm) as session:
            for case in (case for case in schedule if case.arm == arm):
                check()
                task = tasks[case.task_id]
                relay = StagedResponseRelay(
                    task.relay_campaign(), mode=case.mode, attacked=case.attacked
                )
                agent = agent_factory(relay)
                environment_class = (
                    UnguardedSimulatorReference if arm == "unguarded" else ECPAEnvironment
                )
                environment = environment_class(
                    task.public,
                    task.state(),
                    budgets=study.spec.budgets,
                    approval_provider=SimulatedApprover(),
                )
                first_call = len(session.calls)
                started = time.perf_counter()
                try:
                    episode = await collect_episode(
                        environment,
                        agent,
                        session.policy,
                        seed=case.episode_seed,
                        evaluator=task.outcome,
                    )
                finally:
                    await agent.aclose()
                elapsed = time.perf_counter() - started
                # Persist before the next thermal check; a failed phase retains
                # completed continuations and cannot be loaded as valid evidence.
                payload = {
                    **common,
                    "case": case.model_dump(mode="json"),
                    "task_source_digest": task.digest,
                    **rollout_record(
                        RecordedRollout(episode, tuple(agent.calls), tuple(relay.events))
                    ),
                    "selector_calls": session.calls[first_call:],
                    "budget_used": environment.budget.used,
                    "elapsed_seconds": elapsed,
                }
                filename = f"{case.case_id}.rollout.private.json"
                write_exclusive(output / filename, payload)
                metrics = episode_metrics(episode)
                row = ComparisonRow(
                    case=case,
                    completed=bool(metrics["completed"]),
                    safe_recovery=bool(metrics["safe_recovery"]),
                    violation=bool(metrics["violation"]),
                    attack_success=bool(metrics["attack_success"]),
                    truncated=episode.truncated,
                    termination_reason=episode.termination_reason,
                    online_budget_units=environment.budget.used.get("total", 0),
                    agent_calls=len(agent.calls),
                    selector_calls=len(session.calls) - first_call,
                    elapsed_seconds=elapsed,
                    menu_coverage=MenuCoverage.model_validate(metrics["menu_coverage"]),
                    rollout_file=filename,
                    rollout_sha256=file_digest(output / filename),
                )
                write_exclusive(
                    output / f"{case.case_id}.row.private.json", row.model_dump(mode="json")
                )
                rows.append(row)
                check()
        check()
    report = {
        **common,
        "purpose": "formal_matched_split_comparison",
        "status": "complete",
        "rows": [row.model_dump(mode="json") for row in rows],
        "summary": descriptive_summary(rows),
        "files": {
            path.name: file_digest(path) for path in sorted(output.iterdir()) if path.is_file()
        },
        "efficacy_evidence": False,
    }
    write_exclusive(output / "comparison.json", report)
    return report


def descriptive_summary(rows: Sequence[ComparisonRow]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for arm in dict.fromkeys(row.case.arm for row in rows):
        result[arm] = {}
        for mode in ("text", "structured"):
            for attacked in (False, True):
                group = [
                    row
                    for row in rows
                    if (row.case.arm, row.case.mode, row.case.attacked) == (arm, mode, attacked)
                ]
                if group:
                    result[arm][f"{mode}_{'attacked' if attacked else 'benign'}"] = {
                        "episodes": len(group),
                        "families": len({row.case.semantic_family for row in group}),
                        "safe_completions": sum(row.safe_recovery for row in group),
                        "functional_completions": sum(row.completed for row in group),
                        "violations": sum(row.violation for row in group),
                        "attack_successes": sum(row.attack_success for row in group),
                        "online_budget_units": sum(row.online_budget_units for row in group),
                        "agent_calls": sum(row.agent_calls for row in group),
                        "selector_calls": sum(row.selector_calls for row in group),
                        "episode_seconds": sum(row.elapsed_seconds for row in group),
                        "menu_coverage": menu_summary(group),
                    }
    return result


def menu_summary(rows: Sequence[ComparisonRow]) -> dict[str, Any]:
    """Retain every episode, including failures without a recorded decision."""
    totals: dict[str, object] = {
        key: sum(getattr(row.menu_coverage, key) for row in rows)
        for key in (
            "decisions",
            "singleton_decisions",
            "choice_decisions",
            "multiple_non_deny_decisions",
        )
    }
    for key in ("menu_size_counts", "candidate_kind_counts", "selected_kind_counts"):
        counts: dict[str, int] = defaultdict(int)
        for row in rows:
            for name, count in getattr(row.menu_coverage, key).items():
                counts[name] += count
        totals[key] = dict(counts)
    cohorts = {
        "no_recorded_decisions": [row for row in rows if row.menu_coverage.decisions == 0],
        "singleton_only": [
            row
            for row in rows
            if row.menu_coverage.decisions > 0 and row.menu_coverage.choice_decisions == 0
        ],
        "choice_exposed": [row for row in rows if row.menu_coverage.choice_decisions > 0],
    }
    return {
        **totals,
        "by_episode_exposure": {
            name: {
                "episodes": len(group),
                "safe_completions": sum(row.safe_recovery for row in group),
                "violations": sum(row.violation for row in group),
                "interventions": sum(
                    count
                    for row in group
                    for kind, count in row.menu_coverage.selected_kind_counts.items()
                    if kind != "allow"
                ),
                "online_budget_units": sum(row.online_budget_units for row in group),
                "agent_calls": sum(row.agent_calls for row in group),
                "selector_calls": sum(row.selector_calls for row in group),
                "episode_seconds": sum(row.elapsed_seconds for row in group),
            }
            for name, group in cohorts.items()
        },
        "interpretation": (
            "Recorded decisions only; exposure may differ after interventions. "
            "Descriptive cohorts are not causal comparisons; "
            "primary denominators retain all episodes."
        ),
    }


def _identity(study: FrozenStudy) -> dict[str, str]:
    return {
        "source_revision": study.revision,
        "formal_protocol_id": study.protocol_id,
        "frozen_manifest_digest": study.manifest_digest,
    }


def phase_files(path: Path) -> dict[str, str]:
    return {
        str(file.relative_to(path)): file_digest(file)
        for file in sorted(path.rglob("*"))
        if file.is_file() and file != path / "phase-result.json"
    }


def load_completed_phase(path: Path, study: FrozenStudy, phase_name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((path / "phase-result.json").read_text())
    expected = {**_identity(study), "phase": phase_name, "status": "complete", "error_kind": None}
    if any(result.get(key) != value for key, value in expected.items()):
        raise ValueError("study prerequisite must be a completed matching measured phase")
    if not result.get("artifact_files") or result["artifact_files"] != phase_files(path):
        raise ValueError("study prerequisite artifact integrity mismatch")
    return result


def load_fit_phase(path: Path, study: FrozenStudy) -> dict[int, Path]:
    load_completed_phase(path, study, "fit")
    phase_manifest = json.loads((path / "phase-manifest.json").read_text())
    collection = Path(phase_manifest["collection"])
    if not collection.is_absolute():
        raise ValueError("fitting must bind an absolute verified training collection")
    groups = load_training_phase(collection, study)
    expected_groups = {
        group.group_id: content_hash(group.model_dump(mode="json")) for group in groups
    }
    if phase_manifest.get("collection_phase_sha256") != file_digest(
        collection.parent / "phase-result.json"
    ):
        raise ValueError("fitting collection phase identity mismatch")
    complete = json.loads((path / "fit-complete.json").read_text())
    if any(
        complete.get(key) != value
        for key, value in {
            "source_revision": study.revision,
            "formal_protocol_id": study.protocol_id,
            "adapter_seeds": list(study.spec.adapter_seeds),
        }.items()
    ):
        raise ValueError("fit must contain the single prespecified adapter seed")
    adapters = {}
    for seed in study.spec.adapter_seeds:
        directory = path / f"adapter-seed-{seed}"
        manifest = validate_adapter(
            directory, study.spec.compact, expected_protocol_id=study.protocol_id
        )
        if (
            manifest.get("source_revision") != study.revision
            or manifest.get("spec")
            != study.spec.lora.model_copy(update={"seed": seed}).model_dump(mode="json")
            or manifest.get("data_source_revisions") != [study.revision]
            or manifest.get("source_group_hashes") != expected_groups
        ):
            raise ValueError("adapter recipe/source differs from the frozen study")
        adapters[seed] = directory
    if {file.name for file in path.glob("adapter-seed-*")} != {
        file.name for file in adapters.values()
    }:
        raise ValueError("fit must retain exactly the single declared adapter")
    return adapters


def load_comparison(path: Path, study: FrozenStudy, split: EvaluationSplit) -> list[ComparisonRow]:
    """Validate completed, measured phase, exact schedule and every raw record."""
    phase = load_completed_phase(path.parent, study, split)
    files = {
        str(file.relative_to(path)): file_digest(file)
        for file in sorted(path.rglob("*"))
        if file.is_file()
    }
    if not files or phase.get("comparison_files") != files:
        raise ValueError("comparison phase file integrity mismatch")
    report = json.loads((path / "comparison.json").read_text())
    if any(
        report.get(key) != value
        for key, value in {
            **_identity(study),
            "split": split,
            "status": "complete",
            "purpose": "formal_matched_split_comparison",
        }.items()
    ):
        raise ValueError("comparison report identity mismatch")
    if report.get("files") != {
        name: digest for name, digest in files.items() if name != "comparison.json"
    }:
        raise ValueError("comparison record file integrity mismatch")
    schedule = comparison_schedule(study, split)
    rows = [ComparisonRow.model_validate(row) for row in report["rows"]]
    if [row.case for row in rows] != schedule:
        raise ValueError("comparison must cover the exact frozen schedule in order")
    expected_schedule = {
        **_identity(study),
        "split": split,
        "cases": [case.model_dump(mode="json") for case in schedule],
    }
    if json.loads((path / "schedule.json").read_text()) != expected_schedule:
        raise ValueError("recorded comparison schedule differs from frozen cases")
    for row in rows:
        expected_name = f"{row.case.case_id}.rollout.private.json"
        if row.rollout_file != expected_name or files.get(expected_name) != row.rollout_sha256:
            raise ValueError("comparison rollout binding mismatch")
        saved_row = json.loads((path / f"{row.case.case_id}.row.private.json").read_text())
        if saved_row != row.model_dump(mode="json"):
            raise ValueError("comparison row ledger differs from its summary")
        raw = json.loads((path / expected_name).read_text())
        task = next(task for task in study.tasks if task.entry.task_id == row.case.task_id)
        expected = {
            **_identity(study),
            "split": split,
            "case": row.case.model_dump(mode="json"),
            "task_source_digest": task.digest,
        }
        if any(raw.get(key) != value for key, value in expected.items()):
            raise ValueError("comparison rollout source mismatch")
        for key in (
            "completed",
            "safe_recovery",
            "violation",
            "attack_success",
            "truncated",
            "termination_reason",
        ):
            if getattr(row, key) != raw["metrics"][key]:
                raise ValueError("comparison metrics differ from recorded rollout")
        if row.menu_coverage.model_dump(mode="json") != raw["metrics"]["menu_coverage"]:
            raise ValueError("comparison menu coverage differs from recorded rollout")
        if (
            row.online_budget_units != raw["budget_used"].get("total", 0)
            or row.agent_calls != len(raw["calls"])
            or row.selector_calls != len(raw["selector_calls"])
            or row.elapsed_seconds != raw["elapsed_seconds"]
        ):
            raise ValueError("comparison cost differs from recorded rollout")
    if report["summary"] != descriptive_summary(rows):
        raise ValueError("comparison summary differs from complete schedule")
    return rows


def select_comparator(rows: Sequence[ComparisonRow], study: FrozenStudy) -> dict[str, Any]:
    """Equal family weights; retained variants never add independent votes."""
    if [row.case for row in rows] != comparison_schedule(study, "tune"):
        raise ValueError("comparator selection requires the complete tuning schedule only")
    ranks = {}
    for arm in study.spec.comparator_arms:
        families: dict[str, list[ComparisonRow]] = defaultdict(list)
        for row in rows:
            if row.case.arm == arm:
                families[row.case.semantic_family].append(row)
        if not families:
            raise ValueError("every guarded tuning comparator is required")
        values = np.asarray(
            [
                [
                    np.mean([row.violation for row in group]),
                    -np.mean([row.safe_recovery for row in group]),
                    np.mean([row.online_budget_units for row in group]),
                ]
                for group in families.values()
            ]
        ).mean(axis=0)
        ranks[arm] = [float(value) for value in values]
    # Exact ties follow the explicit prespecified comparator order.
    selected = min(study.spec.comparator_arms, key=lambda arm: ranks[arm])
    return {
        **_identity(study),
        "purpose": "tune_only_comparator_selection",
        "selected_comparator": selected,
        "ranking": ranks,
        "rule": study.spec.comparator_selection,
        "cost": study.spec.comparator_cost,
        "family_weighting": "equal_family_means_all_modes_conditions",
        "tie_order": study.spec.comparator_arms,
        "checkpoint_selection": study.spec.checkpoint_selection,
        "adapter_seeds": study.spec.adapter_seeds,
    }


def comparison_analysis(
    rows: Sequence[ComparisonRow], study: FrozenStudy, comparator: str
) -> dict[str, Any]:
    analysis_splits: tuple[EvaluationSplit, ...] = ("calibration", "test")
    if not any(
        [row.case for row in rows] == comparison_schedule(study, split) for split in analysis_splits
    ):
        raise ValueError("analysis requires a complete fixed-policy calibration or test schedule")
    if comparator not in study.spec.comparator_arms:
        raise ValueError("use the comparator frozen on tuning only")
    baseline = {row.case.pair_key: row for row in rows if row.case.arm == comparator}
    pairs = []
    for row in rows:
        if row.case.adapter_seed is None:
            continue
        control = baseline[row.case.pair_key]
        pairs.append(
            PairedResult(
                pair_id=row.case.case_id,
                semantic_family=row.case.semantic_family,
                condition="attacked" if row.case.attacked else "benign",
                learned_success=row.completed,
                baseline_success=control.completed,
                learned_violation=row.violation,
                baseline_violation=control.violation,
            )
        )
    modes: dict[str, Any] = {}
    for mode in ("text", "structured"):
        identifiers = {row.case.case_id for row in rows if row.case.mode == mode}
        mode_pairs = [pair for pair in pairs if pair.pair_id in identifiers]
        if (
            min(
                len({pair.semantic_family for pair in mode_pairs if pair.condition == condition})
                for condition in ("attacked", "benign")
            )
            < 2
        ):
            modes[mode] = {
                "inference_supported": False,
                "reason": "fewer than two families",
                "meets_prespecified_criteria": False,
            }
        else:
            modes[mode] = paired_family_comparison(mode_pairs, study.spec.comparison)
    report = paired_family_comparison(pairs, study.spec.comparison)
    per_seed = {}
    for seed in study.spec.adapter_seeds:
        identifiers = {row.case.case_id for row in rows if row.case.adapter_seed == seed}
        seed_pairs = [pair for pair in pairs if pair.pair_id in identifiers]
        per_seed[str(seed)] = paired_family_comparison(seed_pairs, study.spec.comparison)
    return {
        **_identity(study),
        "purpose": "fixed_policy_paired_analysis",
        "comparator": comparator,
        "all_seeds_retained": list(study.spec.adapter_seeds),
        "pooled": report,
        "by_mode": modes,
        "by_adapter_seed": per_seed,
        "interpretation": (
            "family-clustered estimates conditional on one fitted adapter; "
            "training-seed variability not estimated; no calibration retuning"
        ),
    }
