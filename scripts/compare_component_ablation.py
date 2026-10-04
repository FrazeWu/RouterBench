#!/usr/bin/env python3
"""Write an aggregate-only report for the graph-component ablation runs."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/private/component-ablation-v1-fixed-comparison-20261004.md"
CONDITIONS = (
    ("complete", ROOT / "artifacts/private/component-ablation-v1-eval-complete-20261003"),
    (
        "danger_decoys_removed",
        ROOT / "artifacts/private/component-ablation-v1-fixed-eval-danger_decoys_removed-20261003",
    ),
    (
        "functional_alternatives_pruned",
        ROOT / "artifacts/private/component-ablation-v1-fixed-eval-functional_alternatives_pruned-20261003",
    ),
    (
        "dependencies_stripped",
        ROOT / "artifacts/private/component-ablation-v1-fixed-eval-dependencies_stripped-20261003",
    ),
    (
        "authority_contrast_flattened",
        ROOT / "artifacts/private/component-ablation-v1-fixed-eval-authority_contrast_flattened-20261003",
    ),
)


def read_summary(path: Path) -> dict:
    summary = json.loads((path / "formal-graph-summary.json").read_text(encoding="utf-8"))
    overall = summary["overall"]
    if (
        overall["planned_attempts"] != 480
        or overall["assessed_attempts"] != 480
        or overall["invalid_outputs"] != 0
        or overall["backend_failures"] != 0
    ):
        raise SystemExit(f"incomplete or invalid run: {path}")
    return summary


def rate(value: int, denominator: int) -> str:
    return f"{100 * value / denominator:.2f}%"


def main() -> None:
    summaries = {name: read_summary(path) for name, path in CONDITIONS}
    base = summaries["complete"]["overall"]
    lines = [
        "# RouteBench v13 Graph-Component Ablation",
        "",
        "## Scope",
        "",
        "- Diagnostic subset: 96 cases selected by effect family x route-length cell.",
        "- Conditions: 5 graph variants x 96 cases x 5 seeds = 2,400 attempts.",
        "- Model: Qwen3-14B; temperature 0; vLLM; v13 incremental-edge protocol.",
        "- Case gate: at least 3/5 OptimalPathSuccess.",
        "- All conditions completed 480/480 valid attempts with zero backend failures.",
        "- The `complete` result was run before rematerialization; its complete graph digest matches the fixed materialization.",
        "- This is a controlled diagnostic, not a replacement for the 776-case formal result.",
        "",
        "## Overall Results",
        "",
        "| Condition | Optimal | Capable cases | Functional | Policy compliant | Attack path |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, _ in CONDITIONS:
        overall = summaries[name]["overall"]
        lines.append(
            f"| `{name}` | {overall['optimal_path_successes']}/480 ({rate(overall['optimal_path_successes'], 480)}) | "
            f"{overall['capable_cases']}/96 ({rate(overall['capable_cases'], 96)}) | "
            f"{overall['functional_successes']}/480 ({rate(overall['functional_successes'], 480)}) | "
            f"{overall['policy_compliant_selections']}/480 ({rate(overall['policy_compliant_selections'], 480)}) | "
            f"{overall['attack_path_selections']}/480 ({rate(overall['attack_path_selections'], 480)}) |"
        )

    lines.extend(["", "## Change From Complete", "", "| Condition | Delta optimal | Delta capable cases | Delta functional | Delta attack path |", "|---|---:|---:|---:|---:|"])
    for name, _ in CONDITIONS[1:]:
        overall = summaries[name]["overall"]
        lines.append(
            f"| `{name}` | {overall['optimal_path_successes'] - base['optimal_path_successes']:+d} attempts "
            f"({100 * (overall['optimal_path_successes'] - base['optimal_path_successes']) / 480:+.2f} pp) | "
            f"{overall['capable_cases'] - base['capable_cases']:+d} cases "
            f"({100 * (overall['capable_cases'] - base['capable_cases']) / 96:+.2f} pp) | "
            f"{overall['functional_successes'] - base['functional_successes']:+d} attempts "
            f"({100 * (overall['functional_successes'] - base['functional_successes']) / 480:+.2f} pp) | "
            f"{overall['attack_path_selections'] - base['attack_path_selections']:+d} attempts "
            f"({100 * (overall['attack_path_selections'] - base['attack_path_selections']) / 480:+.2f} pp) |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Removing dangerous decoys produced the same aggregate result as the complete condition on this model/subset; the condition is therefore not a strong causal manipulation of model behavior in aggregate.",
            "- Pruning benign functional alternatives produced a small increase in optimal attempts and capable cases; this should be treated as a weak diagnostic signal, not evidence that alternatives help the model.",
            "- Removing explicit prior-action requirements left attempt-level optimality nearly unchanged but reduced capable cases, suggesting that the case gate is sensitive to a small number of scenario-level failures.",
            "- Flattening public authority contrasts reduced capable cases and increased attack-path selections. This is the strongest evidence in this ablation that visible authority distinctions are used for safe route selection.",
            "- These are descriptive aggregate comparisons. Paired case-level confidence intervals and per-family/per-length tables should be added before using the ablation for a causal claim.",
            "",
            "## Provenance",
            "",
            "- Git revision: `94c062ca5941721d806645077d86b24f77244966`.",
            "- Raw prompts and responses are not retained.",
            "- Source materialization: `artifacts/private/component-ablation-v1-fixed-20261003/`.",
        ]
    )
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
