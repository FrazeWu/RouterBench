#!/usr/bin/env python3
"""Audit existing ablation labels and changed subsets without new model inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
from report_v13_evidence import (
    ABLATIONS,
    LABELS,
    ROOT,
    bootstrap,
    check,
    load_run,
    matrix,
    read_json,
    write_new,
)

from routebench.evaluation.interventions import (
    compare_intervention,
    path_outcomes,
    snapshot,
)
from routebench.scenarios import load_scenario


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    check(not args.output_root.exists(), "choose a new immutable output directory")
    artifacts = args.artifacts_root.resolve()
    material = artifacts / "component-ablation-v1-fixed-20261003"
    manifest = read_json(material / "manifest.json")
    check(manifest["status"] == "valid", "material was not validated")
    runs = {
        name: load_run(name, artifacts / path, 96, f"ablation_{name}_") for name, path in ABLATIONS
    }
    base_run = runs["complete"]
    ids = sorted(base_run.cases)
    bases = {key: snapshot(load_scenario(material / "complete" / key)) for key in ids}
    rows = {}
    summary = {}
    subsets = {}
    provenance = {}
    for name, run in runs.items():
        check(run.cases.keys() == base_run.cases.keys(), "case inventories differ")
        for key in ("planner", "formal_evaluation_contract"):
            check(run.metadata[key] == base_run.metadata[key], f"{name}: {key} differs")
        variants = (
            bases
            if name == "complete"
            else {key: snapshot(load_scenario(material / name / key)) for key in ids}
        )
        rows[name] = {}
        for key in ids:
            state = variants[key]
            expected = run.metadata["material_passport"]["scenario_digests"]
            check(
                expected[state.bundle.definition.metadata.scenario_id] == state.bundle.digest,
                f"{name}: material digest differs",
            )
            check(run.cases[key]["stratum"] == base_run.cases[key]["stratum"], "strata differ")
            rows[name][key] = compare_intervention(bases[key], state)
        mismatches: Counter[str] = Counter()
        exposure: Counter[str] = Counter()
        for path in sorted(run.root.glob("attempts/*/manifest.json")):
            record = read_json(path)
            if record["status"] != "valid":
                continue
            key = record["scenario_id"].removeprefix(f"ablation_{name}_")
            selected = tuple(record["selection"]["edge_ids"])
            state = variants[key]
            replay = path_outcomes(state, selected)
            for index, label in enumerate(("optimal", "functional", "policy", "unsafe")):
                mismatches[label] += replay[index] != run.cases[key]["seeds"][record["seed"]][index]
            certificate = state.bundle.definition.routes.certificates
            assert certificate is not None
            mismatches["hidden_certificate_flag"] += record["outcomes"][
                "matches_hidden_certificate"
            ] != (selected == certificate.safe.edge_ids)
            mismatches["public_exact_flag"] += record["outcomes"]["public_exact_optimal"] != (
                selected in state.exact
            )
            mismatches["public_pareto_flag"] += record["outcomes"]["public_pareto_optimal"] != (
                selected in state.pareto
            )
            if selected in bases[key].paths:
                before = path_outcomes(bases[key], selected)[0]
                exposure["changed_optimal_label_on_selected_route"] += before != replay[0]
                exposure["newly_accepted_selected_route"] += not before and replay[0]
                exposure["newly_rejected_selected_route"] += before and not replay[0]
            else:
                exposure["selected_route_absent_from_base"] += 1
        summary[name] = {
            "cases": len(ids),
            "flags": dict(
                Counter(
                    flag
                    for row in rows[name].values()
                    for flag, value in row.items()
                    if value is True
                )
            ),
            "label_paths_changed": sum(r["changed_label_paths"] for r in rows[name].values()),
            "exact_count_before": sum(r["base_exact_count"] for r in rows[name].values()),
            "exact_count_after": sum(r["variant_exact_count"] for r in rows[name].values()),
            "replay_mismatches": dict(mismatches),
            "selected_route_label_exposure": dict(exposure),
        }
        subsets[name] = {
            "all": ids,
            "graph_changed": [key for key in ids if rows[name][key]["graph_changed"]],
            "fixed_objective_effective": [
                key for key in ids if rows[name][key]["fixed_objective_effective"]
            ],
        }
        provenance[name] = {
            "source": str(run.root),
            "record_digest": run.record_digest,
            "source_git": run.metadata["git"],
            "material_digests": {key: variants[key].bundle.digest for key in ids},
        }
    lines = [
        "# Existing ablation: label alignment and effective subsets",
        "",
        "Read-only audit of 96 cases x 5 conditions x 5 seeds (2,400 saved attempts).",
        "Subsets are defined from materials only, never from observed model scores.",
        "Primary labels follow public exact optima, including ties, not certificate identity.",
        "Goal, policy, verifier, fixture, certificates and retained bindings must stay fixed.",
        "An unchanged exact optimum set does not by itself prove construct-valid isolation.",
        "The fixed-objective subset is a strict screening rule, not a causal-validity certificate.",
        "",
        "| Condition | Changed | Eligible set same | Exact set same | Tied cases | "
        "Reference accepted | Effective fixed-objective | Private costs changed |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in runs:
        flags = summary[name]["flags"]
        tied = sum(row["variant_exact_count"] > 1 for row in rows[name].values())
        lines.append(
            f"| {name} | {flags.get('graph_changed', 0)}/96 | "
            f"{flags.get('eligible_set_same', 0)}/96 | {flags.get('exact_set_same', 0)}/96 | "
            f"{tied}/96 | {flags.get('reference_accepted', 0)}/96 | "
            f"{len(subsets[name]['fixed_objective_effective'])}/96 | "
            f"{flags.get('private_costs_changed', 0)}/96 |"
        )
    lines += [
        "",
        "## Reproduction and label exposure",
        "",
        "Label exposure re-scores the same selected route in base material. It is not a "
        "counterfactual model run and must not replace the saved score.",
        "",
        "| Condition | Replay mismatches (all flags) | Newly accepted attempts | "
        "Newly rejected attempts | Exact paths before / after |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in runs:
        info = summary[name]
        exposure = info["selected_route_label_exposure"]
        lines.append(
            f"| {name} | {sum(info['replay_mismatches'].values())} | "
            f"{exposure.get('newly_accepted_selected_route', 0)} | "
            f"{exposure.get('newly_rejected_selected_route', 0)} | "
            f"{info['exact_count_before']} / {info['exact_count_after']} |"
        )
    lines += [
        "",
        "## Paired descriptive differences by material-defined subset",
        "",
        "10,000 paired case-cluster bootstrap resamples, PCG64; seed 20261021 XOR label CRC32.",
        "All five seeds stay within the case; values are variant minus complete in pp.",
        "Exploratory intervals are not multiplicity adjusted; n=1 intervals are degenerate, "
        "not evidence of precision. Empty subsets have no estimate.",
        "",
        "| Condition | Subset | Cases | " + " | ".join(LABELS) + " |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, run in runs.items():
        if name == "complete":
            continue
        for label, selected in subsets[name].items():
            if selected:
                values = bootstrap(
                    matrix(run, selected) - matrix(base_run, selected), f"alignment:{name}:{label}"
                )
                cells = [f"{value:+.2f} [{lo:+.2f}, {hi:+.2f}]" for value, lo, hi in values]
            else:
                cells = ["not estimable"] * len(LABELS)
            lines.append(f"| {name} | {label} | {len(selected)} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Interpretation boundary",
        "",
        "- Nearly null interventions cannot support claims of invariance or robustness.",
        "- Changed eligible/optimal sets confound planning difficulty with task/label changes.",
        "- For candidate-count interventions, changing nonoptimal eligible alternatives may be "
        "intentional; report that separately from changing the optimal answer set.",
        "- Removing redundant dependency annotations does not demonstrate a reduction in "
        "execution-feasibility complexity when every terminal path outcome stays the same.",
        "- Private-cost removal is checked in actual materials, not inferred from script intent.",
        "- Do not rewrite saved labels or tune the held-out 776 cases against these results.",
        "- Author new matched development tasks and validate goals, bindings, outcomes and "
        "mapped optimum sets before new inference. Keep the evaluator fixed.",
    ]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    args.output_root.mkdir(parents=True)
    write_new(args.output_root / "alignment-report.md", "\n".join(lines))
    write_new(args.output_root / "audit-summary.json", json.dumps(summary, indent=2))
    write_new(args.output_root / "private-material-flags.json", json.dumps(rows, indent=2))
    write_new(
        args.output_root / "analysis-provenance.json",
        json.dumps(
            {
                "kind": "existing_ablation_alignment_not_inference",
                "analysis_revision": revision,
                "analysis_dirty": dirty,
                "numpy_version": np.__version__,
                "bootstrap_draws": 10_000,
                "bootstrap_seed": 20261021,
                "runs": provenance,
                "material_manifest_sha256": hashlib.sha256(
                    (material / "manifest.json").read_bytes()
                ).hexdigest(),
                "analysis_source_sha256": {
                    str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (
                        Path(__file__),
                        ROOT / "scripts/report_v13_evidence.py",
                        ROOT / "src/routebench/evaluation/interventions.py",
                    )
                },
                "saved_outcomes_reproduced": not any(
                    any(info["replay_mismatches"].values()) for info in summary.values()
                ),
            },
            indent=2,
        ),
    )
    print(
        json.dumps(
            {
                "output_root": str(args.output_root.resolve()),
                "replay_mismatches": {
                    name: info["replay_mismatches"] for name, info in summary.items()
                },
            },
            indent=2,
        )
    )
    if any(any(info["replay_mismatches"].values()) for info in summary.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
