#!/usr/bin/env python3
"""Compute case-level paired bootstrap intervals for the formal v13 models.

Each model has five repeated seed attempts for each of the same 776 cases.  The
case is the independent analysis unit; bootstrap resampling keeps all five
seeds for a sampled case together.  The generated Markdown is aggregate-only.
"""

from __future__ import annotations

import json
import random
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/private/formal-v3-776-20260929/paired-bootstrap-analysis.md"
BOOTSTRAPS = 10_000
BOOTSTRAP_SEED = 20_261_004
SEEDS = (1701, 1702, 1703, 1704, 1705)
CASE_COUNT = 776

MODELS = (
    ("Qwen3-8B", ROOT / "artifacts/private/formal-v3-776-20260929/qwen3-8b-v13"),
    ("Qwen3-14B", ROOT / "artifacts/private/formal-v3-776-20260929/qwen3-14b-v13"),
    (
        "Qwen3-32B-AWQ",
        ROOT / "artifacts/private/formal-v3-776-20260929/qwen3-32b-awq-v13",
    ),
)

COMPARISONS = (
    ("Qwen3-14B", "Qwen3-8B"),
    ("Qwen3-14B", "Qwen3-32B-AWQ"),
    ("Qwen3-32B-AWQ", "Qwen3-8B"),
)

METRICS = (
    ("optimal_attempt_rate", "Optimal"),
    ("capable_case_rate", "Capable cases"),
    ("functional_attempt_rate", "Functional"),
    ("policy_compliance_rate", "Policy compliant"),
    ("attack_attempt_rate", "Attack path"),
)


def load_model(name: str, root: Path) -> dict[str, dict]:
    """Load and validate one model's five seed attempts for every case."""

    paths = sorted(root.glob("attempts/*/manifest.json"))
    expected_attempts = CASE_COUNT * len(SEEDS)
    if len(paths) != expected_attempts:
        raise SystemExit(f"{name}: expected {expected_attempts} manifests, found {len(paths)}")

    cases: dict[str, dict] = {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        case_id = data.get("scenario_id")
        seed = data.get("seed")
        if not isinstance(case_id, str) or not (
            case_id.startswith("rbv1-") or case_id.startswith("rbv1_")
        ):
            raise SystemExit(f"{name}: unexpected scenario ID in {path}")
        if seed not in SEEDS:
            raise SystemExit(f"{name}: unexpected seed {seed!r} in {path}")
        status = data.get("status")
        if status not in {"valid", "invalid_output"}:
            raise SystemExit(f"{name}: unsupported attempt status in {path}: {status!r}")

        case = cases.setdefault(
            case_id,
            {
                "seeds": {},
                "primary_effect_family": data.get("primary_effect_family"),
                "route_length": data.get("route_length"),
            },
        )
        if seed in case["seeds"]:
            raise SystemExit(f"{name}: duplicate case/seed {case_id}/{seed}")
        if case["primary_effect_family"] != data.get("primary_effect_family") or case[
            "route_length"
        ] != data.get("route_length"):
            raise SystemExit(f"{name}: stratum mismatch within case {case_id}")

        outcomes = data.get("outcomes", {})
        if status == "invalid_output":
            outcomes = {
                "optimal_path_success": False,
                "functional_success": False,
                "policy_compliance": False,
                "attack_success": False,
            }
        required = (
            "optimal_path_success",
            "functional_success",
            "policy_compliance",
            "attack_success",
        )
        if any(key not in outcomes for key in required):
            raise SystemExit(f"{name}: incomplete outcomes in {path}")
        case["seeds"][seed] = {
            "optimal": bool(outcomes["optimal_path_success"]),
            "functional": bool(outcomes["functional_success"]),
            "policy": bool(outcomes["policy_compliance"]),
            "attack": bool(outcomes["attack_success"]),
        }

    if len(cases) != CASE_COUNT:
        raise SystemExit(f"{name}: expected {CASE_COUNT} cases, found {len(cases)}")
    for case_id, case in cases.items():
        if tuple(sorted(case["seeds"])) != SEEDS:
            raise SystemExit(f"{name}: case {case_id} does not have exactly five seeds")
    return cases


def summarize_case(case: dict) -> dict[str, float | str]:
    attempts = [case["seeds"][seed] for seed in SEEDS]
    optimal = sum(int(row["optimal"]) for row in attempts)
    return {
        "optimal_attempt_rate": optimal / len(SEEDS),
        "capable_case_rate": float(optimal >= 3),
        "functional_attempt_rate": sum(int(row["functional"]) for row in attempts) / len(SEEDS),
        "policy_compliance_rate": sum(int(row["policy"]) for row in attempts) / len(SEEDS),
        "attack_attempt_rate": sum(int(row["attack"]) for row in attempts) / len(SEEDS),
        "primary_effect_family": case["primary_effect_family"],
        "route_length": case["route_length"],
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def percentile(sorted_values: list[float], quantile: float) -> float:
    position = (len(sorted_values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])


def paired_bootstrap(
    left_rows: list[dict],
    right_rows: list[dict],
    metric: str,
    label: str,
) -> tuple[float, float, float]:
    """Return left-minus-right difference and percentile 95% bootstrap CI."""

    if len(left_rows) != len(right_rows) or not left_rows:
        raise ValueError("paired rows must be non-empty and equal length")
    differences = [
        left[metric] - right[metric] for left, right in zip(left_rows, right_rows, strict=True)
    ]
    observed = mean(differences)
    seed = BOOTSTRAP_SEED ^ zlib.crc32(label.encode("utf-8"))
    rng = random.Random(seed)
    estimates = [mean(rng.choices(differences, k=len(differences))) for _ in range(BOOTSTRAPS)]
    estimates.sort()
    return observed, percentile(estimates, 0.025), percentile(estimates, 0.975)


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def interval(value: tuple[float, float, float]) -> str:
    observed, lower, upper = value
    return f"{100 * observed:+.2f} pp [{100 * lower:+.2f}, {100 * upper:+.2f}]"


def main() -> None:
    loaded = {name: load_model(name, root) for name, root in MODELS}
    model_names = {name for name, _ in MODELS}
    if set(loaded) != model_names:
        raise SystemExit("model inventory mismatch")

    common_ids = set(next(iter(loaded.values())))
    if any(set(cases) != common_ids for cases in loaded.values()):
        raise SystemExit("models do not contain identical case sets")

    rows: dict[str, list[dict]] = {}
    for name, _ in MODELS:
        model_rows = []
        for case_id in sorted(common_ids):
            model_rows.append(summarize_case(loaded[name][case_id]))
        rows[name] = model_rows

    base_rows = rows[MODELS[0][0]]
    strata = {
        "Effect family": (
            "primary_effect_family",
            sorted({row["primary_effect_family"] for row in base_rows}),
        ),
        "Route length": (
            "route_length",
            sorted({row["route_length"] for row in base_rows}),
        ),
    }
    for name, model_rows in rows.items():
        for key, values in strata.values():
            if sorted({row[key] for row in model_rows}) != values:
                raise SystemExit(f"{name}: changed strata for {key}")

    summaries = {
        name: {metric: mean([row[metric] for row in rows[name]]) for metric, _ in METRICS}
        for name, _ in MODELS
    }

    lines = [
        "# RouteBench v13 Formal Benchmark: Paired Model Bootstrap",
        "",
        "## Scope",
        "",
        f"- Held-out test set: 776 shared cases and {len(MODELS)} models; each model has "
        "3,880 planned attempts. Invalid outputs are represented as failed outcomes.",
        f"- Bootstrap: {BOOTSTRAPS:,} paired case resamples, fixed seed `{BOOTSTRAP_SEED}`; "
        "percentile 95% intervals.",
        "- Inference unit: scenario case. The five seeds are repeated measurements within "
        "a case, not independent cases.",
        "- Capable case: at least 3/5 OptimalPathSuccess attempts.",
        "- Attack-path rate records unsafe-branch selection in the trusted simulator; no "
        "real data access or destructive action was executed.",
        "- Intervals are descriptive uncertainty intervals; no p-values or causal claims "
        "are reported.",
        "",
        "## Aggregate Rates",
        "",
        "| Model | Cases | Optimal | Capable cases | Functional | Policy compliant | Attack path |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, _ in MODELS:
        lines.append(
            f"| `{name}` | {CASE_COUNT} | {pct(summaries[name]['optimal_attempt_rate'])} | "
            f"{pct(summaries[name]['capable_case_rate'])} | "
            f"{pct(summaries[name]['functional_attempt_rate'])} | "
            f"{pct(summaries[name]['policy_compliance_rate'])} | "
            f"{pct(summaries[name]['attack_attempt_rate'])} |"
        )

    lines.extend(
        [
            "",
            "## Paired Differences",
            "",
            "Each cell is `left model - right model` in percentage points, followed by "
            "the paired bootstrap 95% CI.",
            "",
            "| Comparison | Optimal | Capable cases | Functional | Policy compliant | "
            "Attack path |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for left_name, right_name in COMPARISONS:
        left_rows = rows[left_name]
        right_rows = rows[right_name]
        cells = []
        for metric, _label in METRICS:
            cells.append(
                interval(
                    paired_bootstrap(
                        left_rows,
                        right_rows,
                        metric,
                        f"overall:{left_name}:{right_name}:{metric}",
                    )
                )
            )
        lines.append(f"| `{left_name} - {right_name}` | " + " | ".join(cells) + " |")

    for stratum_name, (key, values) in strata.items():
        lines.extend(
            [
                "",
                f"## Paired Differences by {stratum_name}",
                "",
                "Rows are descriptive within strata; n is the number of cases and each "
                "case contributes five repeated seeds.",
                "",
                "| Stratum | Comparison | n cases | Optimal | Capable cases | Functional | "
                "Policy compliant | Attack path |",
                "|---|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for value in values:
            for left_name, right_name in COMPARISONS:
                left_subset = [row for row in rows[left_name] if row[key] == value]
                right_subset = [row for row in rows[right_name] if row[key] == value]
                if len(left_subset) != len(right_subset):
                    raise SystemExit(f"{value}: paired stratum size mismatch")
                cells = []
                for metric, _label in METRICS:
                    cells.append(
                        interval(
                            paired_bootstrap(
                                left_subset,
                                right_subset,
                                metric,
                                f"stratum:{key}:{value}:{left_name}:{right_name}:{metric}",
                            )
                        )
                    )
                lines.append(
                    f"| `{value}` | `{left_name} - {right_name}` | {len(left_subset)} | "
                    + " | ".join(cells)
                    + " |"
                )

    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "- The paired comparisons remove between-case difficulty differences because "
            "every model sees the same 776 case IDs.",
            "- They do not establish a causal model-size law: model families, training, "
            "quantization, and serving configurations differ.",
            "- Small stratum intervals are descriptive and should not be used as "
            "standalone ranking claims.",
            "",
            "## Provenance",
            "",
            "- Source roots are the immutable formal-v13 run directories listed by the model "
            "inventory in the generating script.",
            "- Scenario-set digest: `299d3938c4b5bc582e6d1e2ef"
            "778bd2756f44774425a57785313049c436be0ba`.",
            "- Raw prompts, responses, graphs, fixtures, and hidden certificates are not included.",
        ]
    )
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
