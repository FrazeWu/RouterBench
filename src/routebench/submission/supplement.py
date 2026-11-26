"""Fixed ECPA supplements with a separate identity and unchanged training parent."""

from __future__ import annotations

import random
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from routebench.defense.collect import DefensePolicy, PolicyChoice
from routebench.defense.comparison import EvaluationSplit, comparison_schedule, load_comparison
from routebench.defense.contracts import PublicRecoveryTask, content_hash
from routebench.defense.corpus import CorpusTask
from routebench.defense.ecpa import DefenseDecisionKind, DefenseObservation
from routebench.defense.lora import file_digest
from routebench.defense.pilot import ThermalPacer
from routebench.defense.study import FrozenStudy, load_frozen_study
from scripts.run_defense_study import evaluation_inputs


def validate_parent(protocol: dict[str, Any]) -> tuple[FrozenStudy, dict[str, Any]]:
    """Validate native fit/tune/calibration/test without modifying their identity."""
    from argparse import Namespace

    parent = protocol["ecpa_parent"]
    root = Path(parent["source_root"])
    study = load_frozen_study(root, Path(parent["frozen_study"]["path"]))
    # The new entry point must reuse byte-identical native kernels.
    current = Path(protocol["source_root"])
    for relative, expected in parent["kernel_files"].items():
        if file_digest(current / relative) != expected or file_digest(root / relative) != expected:
            raise ValueError("supplement native kernel differs from its training parent")
    inputs = evaluation_inputs(
        study,
        Namespace(
            phase="test",
            fit=Path(parent["fit_result"]["path"]).parent,
            tune=Path(parent["tune_result"]["path"]).parent,
            calibration=Path(parent["calibration_result"]["path"]).parent,
        ),
        root,
    )
    load_comparison(Path(parent["test_result"]["path"]).parent / "comparison", study, "test")
    if inputs["selection"]["selected_comparator"] != protocol["original_tune_comparator"]:
        raise ValueError("the original tuning comparator cannot change")
    return study, inputs


def schedule(study: FrozenStudy, phase: str, split: EvaluationSplit, comparator: str) -> list[Any]:
    arms: tuple[str, ...]
    if phase == "E4":
        arms = ("public_search",)
    elif phase == "E5" and split == "test":
        arms = ("compact_lora_seed_29",)
    elif phase == "E6" and split == "test":
        arms = ("compact_lora_seed_29", comparator, "public_search")
    else:
        raise ValueError("undeclared supplementary schedule")
    base = [case for case in comparison_schedule(study, split) if case.arm == "path_rule"]
    return [
        case.model_copy(
            update={"arm": arm, "adapter_seed": 29 if arm == "compact_lora_seed_29" else None}
        )
        for arm in arms
        for case in base
    ]


def paraphrase(task: CorpusTask, specification: dict[str, Any]) -> CorpusTask:
    row = specification["tasks"][task.entry.task_id]
    if row["original_public_digest"] != task.public.digest:
        raise ValueError("wording transformation source changed")
    descriptions = row["policy_descriptions"]
    if len(descriptions) != len(task.public.policy.forbidden_effects):
        raise ValueError("wording transformation omitted a policy description")
    public = task.public.model_dump(mode="json")
    public["prompt"] = row["prompt"]
    for effect, description in zip(
        public["policy"]["forbidden_effects"], descriptions, strict=True
    ):
        effect["description"] = description
    transformed = PublicRecoveryTask.model_validate(public)
    return replace(task, public=transformed)


class TransformedPolicy:
    """Change only a selector copy; never mutate the trusted runtime observation."""

    def __init__(self, policy: DefensePolicy, transformation: str, seed: int = 20261116):
        self.policy, self.transformation, self.seed = policy, transformation, seed
        self.events: list[dict[str, Any]] = []

    def choose(self, observation: DefenseObservation, *, rng: random.Random) -> PolicyChoice:
        supplied = observation.model_copy(deep=True)
        reverse: dict[str, str] = {}
        if self.transformation == "no_receipts":
            supplied = supplied.model_copy(update={"receipts": ()})
        elif self.transformation == "menu_permutation":
            identity = {
                "task": observation.task.contract.task_id,
                "step": observation.step,
                "menu": [item.candidate_id for item in observation.menu],
                "seed": self.seed,
            }
            local = random.Random(int(content_hash(identity), 16))
            menu = list(supplied.menu)
            local.shuffle(menu)
            for index, item in enumerate(menu):
                code = f"option_{index}_{content_hash([identity, item.candidate_id])[:8]}"
                reverse[code] = item.candidate_id
                menu[index] = item.model_copy(update={"candidate_id": code})
            supplied = supplied.model_copy(update={"menu": tuple(menu)})
        elif self.transformation != "none":
            raise ValueError("unknown selector transformation")
        cpu_began, wall_began = time.process_time(), time.perf_counter()
        choice = self.policy.choose(supplied, rng=rng)
        cpu_elapsed, wall_elapsed = (
            time.process_time() - cpu_began,
            time.perf_counter() - wall_began,
        )
        selected = choice.candidate_id
        if reverse:
            if selected in reverse:
                selected = reverse[selected]
            elif selected == "deny":
                # Native public policies use this logical fallback at a completed goal.
                selected = next(
                    item.candidate_id
                    for item in observation.menu
                    if item.kind is DefenseDecisionKind.DENY
                )
            else:
                raise ValueError("selector returned an unregistered display ID")
        self.events.append(
            {
                "step": observation.step,
                "transformation": self.transformation,
                "reverse_map": reverse,
                "original_receipts": len(observation.receipts),
                "supplied_receipts": len(supplied.receipts),
                "selected_original_id": selected,
                "selector_cpu_seconds": cpu_elapsed,
                "selector_wall_seconds": wall_elapsed,
            }
        )
        return replace(choice, candidate_id=selected)


class SupplementPacer(ThermalPacer):
    def before(self, gpu_id: int) -> None:
        self.pause_celsius, self.resume_celsius = (73, 71) if gpu_id == 0 else (60, 55)
        self.telemetry.sample()
        super().before(gpu_id)
