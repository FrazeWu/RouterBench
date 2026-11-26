"""Freeze every finite supplementary schedule before opening supplemental outcomes."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from routebench.defense.comparison import EvaluationSplit
from routebench.defense.contracts import content_hash
from routebench.defense.lora import file_digest, model_fingerprint
from routebench.defense.pilot import clean_revision
from routebench.evaluation.graph_evaluation import formal_graph_case_labels
from routebench.scenarios.loader import load_scenario
from routebench.submission.common import durable_json, read_json
from routebench.submission.composition import audit_pair, load_pair
from routebench.submission.supplement import paraphrase, schedule, validate_parent


def structural_subset(bundles: list[Any], seed: int) -> list[Any]:
    cells: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for bundle in bundles:
        cells[formal_graph_case_labels(bundle)].append(bundle)
    if len(cells) != 24:
        raise ValueError("the fixed inventory requires 24 effect/length cells")
    selected = []
    for cell, values in sorted(cells.items()):
        ranked = sorted(
            values, key=lambda b: content_hash([seed, b.definition.metadata.scenario_id])
        )
        wide = [
            b
            for b in ranked
            if max(Counter(e.source for e in b.definition.graph.edges).values()) > 2
        ]
        preferred = wide[:2]
        remainder = [b for b in ranked if b not in preferred]
        chosen = [*preferred, *remainder[: 4 - len(preferred)]]
        if len(chosen) != 4:
            raise ValueError(f"incomplete structural cell: {cell}")
        selected.extend(chosen)
    return sorted(selected, key=lambda b: b.definition.metadata.scenario_id)


def freeze(root: Path, parent: Path, output: Path) -> dict[str, Any]:
    import subprocess

    revision = clean_revision(root)
    configuration = yaml.safe_load((root / "configs/submission/closure-20261126.yaml").read_text())
    recovery = read_json(parent / "test-recovery-20261126-r4/frozen-recovery.json")
    original = Path(recovery["evaluation_source"])
    inputs = recovery["prerequisites"]
    ecpa: dict[str, Any] = {"source_root": str(original)}
    paths = {
        "frozen_study": parent / "frozen-study.json",
        "test_validation_receipt": parent / "test-recovery-20261126-r4/independent-validation.json",
        "test_result": Path(recovery["output"]) / "phase-result.json",
        "fit_result": Path(inputs["fit"]) / "phase-result.json",
        "tune_result": Path(inputs["tune"]) / "phase-result.json",
        "calibration_result": Path(inputs["calibration"]) / "phase-result.json",
        "tuning_decision": Path(inputs["tune"]) / "decision.json",
    }
    for name, path in paths.items():
        ecpa[name] = {"path": str(path), "sha256": file_digest(path)}
    # Every original Python kernel is byte-identical, not just the adapter loader.
    ecpa["kernel_files"] = {
        str(p.relative_to(original)): file_digest(p)
        for p in sorted((original / "src/routebench").rglob("*.py"))
    }
    ecpa["kernel_files"]["scripts/run_defense_study.py"] = file_digest(
        original / "scripts/run_defense_study.py"
    )
    models = configuration["models"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        fingerprints = list(pool.map(model_fingerprint, [m["path"] for m in models.values()]))
    for model, fingerprint in zip(models.values(), fingerprints, strict=True):
        model["fingerprint"] = fingerprint
        index_path = Path(model["path"]) / "model.safetensors.index.json"
        if index_path.exists():
            index = read_json(index_path)
            if any(
                not (Path(model["path"]) / name).is_file()
                for name in set(index["weight_map"].values())
            ):
                raise ValueError("an inference snapshot lacks declared weight shards")
    comparator = read_json(paths["tuning_decision"])["selected_comparator"]
    protocol: dict[str, Any] = {
        "source_root": str(root),
        "source_revision": revision,
        "configuration": configuration,
        "models": models,
        "ecpa_parent": ecpa,
        "original_tune_comparator": comparator,
    }
    protocol["engineering_probes"] = {}
    for key in models:
        probe = root.parent / "engineering-model-probes-r3" / key / "engineering-result.json"
        if read_json(probe)["status"] != "complete":
            raise ValueError("all fixed model snapshots require their engineering probe")
        protocol["engineering_probes"][key] = {"path": str(probe), "sha256": file_digest(probe)}
    study, _ = validate_parent(protocol)
    wording = yaml.safe_load((root / "configs/submission/wording-paraphrases.yaml").read_text())
    for task in study.tasks:
        if task.entry.split == "test":
            paraphrase(task, wording)
    bundles = [
        load_scenario(p.parent)
        for p in sorted((root / "scenarios/formal_v1/test").glob("*/scenario.yaml"))
    ]
    ids = {b.definition.metadata.scenario_id for b in bundles}
    original_inventory = read_json(root / "configs/benchmark/formal-v2-freeze.json")
    if len(bundles) != 776 or ids != set(original_inventory["scenario_digests"]):
        raise ValueError("the original 776-case inventory is required")
    bundles.sort(key=lambda b: b.definition.metadata.scenario_id)
    subset = structural_subset(bundles, configuration["next_hop"]["structural_selection_seed"])
    protocol["graph_cases"] = [str(b.root.relative_to(root)) for b in bundles]
    protocol["next_hop_cases"] = [str(b.root.relative_to(root)) for b in subset]
    protocol["composition_cases"] = {}
    composition_audits: list[dict[str, Any]] = []
    for split, count in (("development", 8), ("test", 40)):
        selected = sorted((root / "scenarios/composition" / split).glob("*/public.yaml"))
        if len(selected) != count:
            raise ValueError("incomplete fixed composition sources")
        protocol["composition_cases"][split] = [str(p.parent.relative_to(root)) for p in selected]
        composition_audits.extend(audit_pair(load_pair(p.parent)) for p in selected)
    protocol["composition_source_audit"] = composition_audits
    protocol["supplement_schedules"] = {}
    for phase in ("E4", "E5", "E6"):
        splits: tuple[EvaluationSplit, ...] = (
            ("tune", "calibration", "test") if phase == "E4" else ("test",)
        )
        protocol["supplement_schedules"][phase] = {
            split: [
                case.model_dump(mode="json") for case in schedule(study, phase, split, comparator)
            ]
            for split in splits
        }
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    protocol["source_files"] = {name: file_digest(root / name) for name in names if name}
    if clean_revision(root) != revision:
        raise ValueError("source changed during freeze")
    protocol["protocol_id"] = "submission-closure-" + content_hash(protocol)
    durable_json(output, protocol)
    return protocol


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ecpa-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = freeze(Path(__file__).resolve().parents[1], args.ecpa_root.resolve(), args.output)
    print(protocol["protocol_id"])


if __name__ == "__main__":
    main()
