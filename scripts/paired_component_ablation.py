#!/usr/bin/env python3
"""Compute case-level paired bootstrap intervals for component ablations.

The five seeds are repeated measurements for each case.  The bootstrap unit is
therefore the case, and each resample keeps all five seeds together.  The
script emits aggregate-only Markdown: no case identifiers, prompts, routes, or
model responses are written to the report.
"""

from __future__ import annotations

import json
import random
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/private/component-ablation-v1-fixed-paired-bootstrap-20261004.md"
BOOTSTRAPS = 10_000
BOOTSTRAP_SEED = 2_026_100_4
SEEDS = (1701, 1702, 1703, 1704, 1705)

CONDITIONS = (
    ("complete", ROOT / "artifacts/private/component-ablation-v1-eval-complete-20261003"),
    (
        "danger_decoys_removed",
        ROOT / "artifacts/private/component-ablation-v1-fixed-eval-danger_decoys_removed-20261003",
    ),
    (
        "functional_alternatives_pruned",
        ROOT
        / (
            "artifacts/private/"
            "component-ablation-v1-fixed-eval-functional_alternatives_pruned-20261003"
        ),
    ),
    (
        "dependencies_stripped",
        ROOT / "artifacts/private/component-ablation-v1-fixed-eval-dependencies_stripped-20261003",
    ),
    (
        "authority_contrast_flattened",
        ROOT
        / (
            "artifacts/private/"
            "component-ablation-v1-fixed-eval-authority_contrast_flattened-20261003"
        ),
    ),
)

METRICS = (
    ("optimal_attempt_rate", "Optimal attempt rate"),
    ("capable_case_rate", "Capable-case rate"),
    ("functional_attempt_rate", "Functional attempt rate"),
    ("policy_compliance_rate", "Policy-compliance rate"),
    ("attack_attempt_rate", "Attack-path rate"),
)


def load_condition(name: str, root: Path) -> dict[str, dict]:
    """Load and validate one condition, returning seed-level rows by case."""

    paths = sorted(root.glob("attempts/*/manifest.json"))
    expected_attempts = 96 * len(SEEDS)
    if len(paths) != expected_attempts:
        raise SystemExit(f"{name}: expected {expected_attempts} manifests, found {len(paths)}")

    prefix = f"ablation_{name}_"
    cases: dict[str, dict] = {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        scenario_id = data.get("scenario_id")
        seed = data.get("seed")
        if not isinstance(scenario_id, str) or not scenario_id.startswith(prefix):
            raise SystemExit(f"{name}: unexpected scenario prefix in {path}")
        if seed not in SEEDS:
            raise SystemExit(f"{name}: unexpected seed {seed!r} in {path}")
        if data.get("status") != "valid":
            raise SystemExit(f"{name}: non-valid attempt in {path}")

        case_id = scenario_id[len(prefix) :]
        if case_id in cases and seed in cases[case_id]["seeds"]:
            raise SystemExit(f"{name}: duplicate case/seed {case_id}/{seed}")
        outcomes = data.get("outcomes", {})
        required = (
            "optimal_path_success",
            "functional_success",
            "policy_compliance",
            "attack_success",
        )
        if any(key not in outcomes for key in required):
            raise SystemExit(f"{name}: incomplete outcomes in {path}")

        case = cases.setdefault(
            case_id,
            {
                "seeds": {},
                "primary_effect_family": data.get("primary_effect_family"),
                "route_length": data.get("route_length"),
            },
        )
        if case["primary_effect_family"] != data.get("primary_effect_family") or case[
            "route_length"
        ] != data.get("route_length"):
            raise SystemExit(f"{name}: stratum mismatch within case {case_id}")
        case["seeds"][seed] = {
            "optimal": bool(outcomes["optimal_path_success"]),
            "functional": bool(outcomes["functional_success"]),
            "policy": bool(outcomes["policy_compliance"]),
            "attack": bool(outcomes["attack_success"]),
        }

    if len(cases) != 96:
        raise SystemExit(f"{name}: expected 96 cases, found {len(cases)}")
    for case_id, case in cases.items():
        if tuple(sorted(case["seeds"])) != SEEDS:
            raise SystemExit(f"{name}: case {case_id} does not have exactly five expected seeds")
    return cases


def summarize_case(case: dict) -> dict[str, float]:
    attempts = [case["seeds"][seed] for seed in SEEDS]
    optimal = sum(int(row["optimal"]) for row in attempts)
    return {
        "optimal_attempt_rate": optimal / len(SEEDS),
        "capable_case_rate": float(optimal >= 3),
        "functional_attempt_rate": sum(int(row["functional"]) for row in attempts) / len(SEEDS),
        "policy_compliance_rate": sum(int(row["policy"]) for row in attempts) / len(SEEDS),
        "attack_attempt_rate": sum(int(row["attack"]) for row in attempts) / len(SEEDS),
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def percentile(sorted_values: list[float], quantile: float) -> float:
    """Linear-interpolated percentile, matching common statistical software."""

    position = (len(sorted_values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])


def paired_bootstrap(
    base_rows: list[dict[str, float]],
    variant_rows: list[dict[str, float]],
    metric: str,
    label: str,
) -> tuple[float, float, float]:
    """Return observed paired difference and percentile 95% bootstrap CI."""

    if len(base_rows) != len(variant_rows) or not base_rows:
        raise ValueError("paired rows must be non-empty and equal length")
    differences = [
        variant[metric] - base[metric]
        for base, variant in zip(base_rows, variant_rows, strict=True)
    ]
    observed = mean(differences)
    seed = BOOTSTRAP_SEED ^ zlib.crc32(label.encode("utf-8"))
    rng = random.Random(seed)
    n = len(differences)
    estimates = []
    for _ in range(BOOTSTRAPS):
        sample = rng.choices(differences, k=n)
        estimates.append(mean(sample))
    estimates.sort()
    return observed, percentile(estimates, 0.025), percentile(estimates, 0.975)


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def pp(value: float) -> str:
    return f"{100 * value:+.2f} pp"


def interval(value: tuple[float, float, float]) -> str:
    observed, lower, upper = value
    return f"{pp(observed)} [{100 * lower:+.2f}, {100 * upper:+.2f}]"


def main() -> None:
    loaded = {name: load_condition(name, path) for name, path in CONDITIONS}
    base_name = CONDITIONS[0][0]
    base_cases = loaded[base_name]
    common_ids = set(base_cases)
    if any(set(cases) != common_ids for name, cases in loaded.items()):
        raise SystemExit("conditions do not contain identical case sets")

    # Materialize one aggregate row per case and condition.  This is the only
    # representation used for inference; the five seed attempts stay nested.
    rows: dict[str, list[dict]] = {}
    for name, _ in CONDITIONS:
        condition_rows = []
        for case_id in sorted(common_ids):
            case = loaded[name][case_id]
            row = summarize_case(case)
            row["primary_effect_family"] = case["primary_effect_family"]
            row["route_length"] = case["route_length"]
            condition_rows.append(row)
        rows[name] = condition_rows

    strata = {
        "effect family": (
            "primary_effect_family",
            sorted({r["primary_effect_family"] for r in rows[base_name]}),
        ),
        "route length": ("route_length", sorted({r["route_length"] for r in rows[base_name]})),
    }

    # Every condition must preserve the same strata and case-level metadata.
    for name in rows:
        for key, values in strata.values():
            observed = sorted({row[key] for row in rows[name]})
            if observed != values:
                raise SystemExit(f"{name}: changed stratum labels for {key}")

    summaries = {
        name: {metric: mean([row[metric] for row in rows[name]]) for metric, _ in METRICS}
        for name, _ in CONDITIONS
    }

    lines = [
        "# RouteBench v13 Graph-Component Ablation: Paired Bootstrap",
        "",
        "## Scope",
        "",
        "- Diagnostic subset: 96 shared cases, balanced across effect family and route length.",
        "- Conditions: 5 graph variants x 96 cases x 5 seeds = 2,400 valid attempts.",
        "- Model: Qwen3-14B; temperature 0; vLLM; v13 incremental-edge protocol.",
        f"- Bootstrap: {BOOTSTRAPS:,} paired resamples, fixed seed `{BOOTSTRAP_SEED}`; "
        "percentile 95% intervals.",
        "- Inference unit: case. The five seeds are repeated measurements within a case "
        "and are never treated as independent cases.",
        "- `Capable-case rate` is the fraction of cases with at least 3/5 optimal attempts.",
        "- All intervals are descriptive uncertainty intervals; no p-values or causal "
        "claims are reported.",
        "",
        "## Aggregate Rates",
        "",
        "| Condition | Cases | Optimal attempts | Capable cases | Functional attempts | "
        "Policy compliant | Attack-path attempts |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, _ in CONDITIONS:
        lines.append(
            f"| `{name}` | 96 | {pct(summaries[name]['optimal_attempt_rate'])} | "
            f"{pct(summaries[name]['capable_case_rate'])} | "
            f"{pct(summaries[name]['functional_attempt_rate'])} | "
            f"{pct(summaries[name]['policy_compliance_rate'])} | "
            f"{pct(summaries[name]['attack_attempt_rate'])} |"
        )

    lines.extend(
        [
            "",
            "## Paired Difference From `complete`",
            "",
            "Each cell is `variant - complete` in percentage points, followed by the "
            "paired bootstrap 95% CI.",
            "",
            "| Condition | Optimal | Capable cases | Functional | Policy compliant | Attack path |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, _ in CONDITIONS[1:]:
        cells = []
        for metric, _label in METRICS:
            result = paired_bootstrap(
                [summarize_case(loaded[base_name][case_id]) for case_id in sorted(common_ids)],
                [summarize_case(loaded[name][case_id]) for case_id in sorted(common_ids)],
                metric,
                f"overall:{name}:{metric}",
            )
            cells.append(interval(result))
        lines.append(f"| `{name}` | " + " | ".join(cells) + " |")

    for stratum_name, (key, values) in strata.items():
        lines.extend(
            [
                "",
                f"## Stratified Differences: {stratum_name.title()}",
                "",
                f"Rows use only cases in the named `{key}` stratum; n is the number of "
                "cases (each with five seeds). These small strata are descriptive.",
                "",
                "| Stratum | Condition | n cases | Optimal | Capable cases | Functional | "
                "Policy compliant | Attack path |",
                "|---|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for value in values:
            base_subset = [row for row in rows[base_name] if row[key] == value]
            lines.append(
                f"| `{value}` | `complete` | {len(base_subset)} | "
                + " | ".join(
                    pct(mean([row[metric] for row in base_subset])) for metric, _ in METRICS
                )
                + " |"
            )
            for name, _ in CONDITIONS[1:]:
                variant_subset = [row for row in rows[name] if row[key] == value]
                base_by_case = [row for row in base_subset]
                variant_by_case = [row for row in variant_subset]
                cells = []
                for metric, _label in METRICS:
                    result = paired_bootstrap(
                        base_by_case,
                        variant_by_case,
                        metric,
                        f"stratum:{key}:{value}:{name}:{metric}",
                    )
                    cells.append(interval(result))
                lines.append(
                    f"| `{value}` | `{name}` | {len(variant_subset)} | " + " | ".join(cells) + " |"
                )

    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "- The paired design controls for the same case appearing in every graph "
            "condition; it does not make the diagnostic subset representative of all "
            "776 formal cases.",
            "- Overlapping or wide intervals should be read as limited evidence for a "
            "condition effect, especially in the 12-case strata.",
            "- `Attack-path attempts` is the simulator's unsafe-branch selection "
            "indicator (`attack_success` in the attempt manifest); no real data access, "
            "credential theft, or destructive action was executed.",
            "",
            "## Provenance",
            "",
            "- Complete condition: `artifacts/private/"
            "component-ablation-v1-eval-complete-20261003/`.",
            "- Fixed ablation conditions: `artifacts/private/"
            "component-ablation-v1-fixed-eval-*-20261003/`.",
            "- Source revision recorded by the run manifests: "
            "`94c062ca5941721d806645077d86b24f77244966`.",
            "- Raw prompts, responses, graphs, fixtures, and hidden certificates are "
            "not included in this report.",
        ]
    )
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
