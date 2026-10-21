#!/usr/bin/env python3
"""Create the current v13 aggregate model comparison and audit report.

Recovery runs retain private per-attempt manifests as well as aggregate summaries.
Use report_v13_evidence.py for validated current-run pairing and provenance audits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/private/formal-v13-current-analysis.md"
EXPECTED_CASES = 776
EXPECTED_ATTEMPTS = 3880


@dataclass(frozen=True)
class Model:
    name: str
    family: str
    scale: str
    root: Path
    status: str = "formal"


MODELS = (
    Model(
        "Qwen3-8B",
        "Qwen3",
        "8B",
        ROOT / "artifacts/private/formal-v13-qwen3-8b-recovery-20261020",
    ),
    Model(
        "Qwen3-14B",
        "Qwen3",
        "14B",
        ROOT / "artifacts/private/formal-v13-qwen3-14b-cu124-20261015-detached",
    ),
    Model(
        "Qwen3-32B-AWQ",
        "Qwen3",
        "32B",
        ROOT / "artifacts/private/formal-v3-776-20260929/qwen3-32b-awq-v13",
    ),
    Model(
        "Qwen2.5-7B",
        "Qwen2.5",
        "7B",
        ROOT / "artifacts/private/formal-v13-qwen25-7b-20261004",
    ),
    Model(
        "Llama3.1-8B",
        "Llama",
        "8B",
        ROOT / "artifacts/private/formal-v13-llama31-8b-20261004",
    ),
    Model(
        "Gemma3-1B",
        "Gemma",
        "1B",
        ROOT / "artifacts/private/formal-v13-gemma3-1b-776-20261005",
    ),
)


def load(model: Model) -> tuple[dict, dict]:
    summary = json.loads((model.root / "formal-graph-summary.json").read_text())
    manifest = json.loads((model.root / "run-manifest.json").read_text())
    scope = summary["scope"]
    overall = summary["overall"]
    if scope["evaluated_cases"] != EXPECTED_CASES:
        raise SystemExit(f"{model.name}: expected {EXPECTED_CASES} cases")
    if overall["planned_attempts"] != EXPECTED_ATTEMPTS:
        raise SystemExit(f"{model.name}: expected {EXPECTED_ATTEMPTS} attempts")
    if overall["backend_failures"]:
        raise SystemExit(f"{model.name}: backend failures present")
    return summary, manifest


def pct(value: int | float, total: int | float) -> str:
    return f"{100 * value / total:.2f}%"


def rate(overall: dict, key: str) -> str:
    return pct(overall[key], EXPECTED_ATTEMPTS)


def delta(a: dict, b: dict, key: str) -> str:
    return f"{100 * (a[key] - b[key]) / EXPECTED_ATTEMPTS:+.2f} pp"


def main() -> None:
    loaded = [(model, *load(model)) for model in MODELS]
    qwen = {model.name: summary for model, summary, _ in loaded if model.family == "Qwen3"}
    lines = [
        "# RouteBench v13 Current Formal Analysis",
        "",
        "## Scope and Integrity",
        "",
        "- All rows below are complete 776-case runs with 5 seeds (3,880 attempts).",
        "- Primary endpoint: `OptimalPathSuccess`; a capable case has at least "
        "3/5 successful seeds.",
        "- Backend failures leave affected cases unassessed; all rows here have zero failures.",
        "- Attack-path selection is an unsafe simulator branch, not a real destructive action.",
        "- The first 8B run with 904 backend failures is preserved separately and not pooled.",
        "",
        "## Current Formal Results",
        "",
        "| Model | Family | Scale | Optimal | Capable cases | Functional | Policy compliant | "
        "Attack path | Invalid | Runtime | Git |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for model, summary, manifest in loaded:
        o = summary["overall"]
        m = manifest["metadata"]
        lines.append(
            f"| `{model.name}` | {model.family} | {model.scale} | "
            f"{rate(o, 'optimal_path_successes')} | "
            f"{pct(o['capable_cases'], EXPECTED_CASES)} | {rate(o, 'functional_successes')} | "
            f"{rate(o, 'policy_compliant_selections')} | {rate(o, 'attack_path_selections')} | "
            f"{o['invalid_outputs']} | {m['inference_runtime']['implementation']} "
            f"{m['inference_runtime']['version']} | "
            f"`{m['git']['commit'][:12]}` |"
        )

    a = qwen["Qwen3-14B"]["overall"]
    b = qwen["Qwen3-8B"]["overall"]
    c = qwen["Qwen3-32B-AWQ"]["overall"]
    lines.extend(
        [
            "",
            "## Qwen3 Scale Comparison",
            "",
            "8B recovery differs from archived v13 by less than 0.2 pp on optimal attempts, "
            "but by approximately 0.64 pp on capable cases. 8B/14B share commit `558bd16`; "
            "32B-AWQ uses `7c95822` and vLLM 0.28.0.",
            "",
            "| Comparison | Optimal | Capable cases | Functional | Policy | Attack path |",
            "|---|---:|---:|---:|---:|---:|",
            f"| 14B - 8B | {delta(a, b, 'optimal_path_successes')} | "
            f"{100 * (a['capable_cases'] - b['capable_cases']) / EXPECTED_CASES:+.2f} pp | "
            f"{delta(a, b, 'functional_successes')} | "
            f"{delta(a, b, 'policy_compliant_selections')} | "
            f"{delta(a, b, 'attack_path_selections')} |",
            f"| 32B-AWQ - 8B | {delta(c, b, 'optimal_path_successes')} | "
            f"{100 * (c['capable_cases'] - b['capable_cases']) / EXPECTED_CASES:+.2f} pp | "
            f"{delta(c, b, 'functional_successes')} | "
            f"{delta(c, b, 'policy_compliant_selections')} | "
            f"{delta(c, b, 'attack_path_selections')} |",
            f"| 14B - 32B-AWQ | {delta(a, c, 'optimal_path_successes')} | "
            f"{100 * (a['capable_cases'] - c['capable_cases']) / EXPECTED_CASES:+.2f} pp | "
            f"{delta(a, c, 'functional_successes')} | "
            f"{delta(a, c, 'policy_compliant_selections')} | "
            f"{delta(a, c, 'attack_path_selections')} |",
            "",
            "14B is strongest on the primary endpoint. This is descriptive, not a causal "
            "parameter-count law: quantization and serving configurations differ.",
        ]
    )

    lines.extend(
        [
            "",
            "## Qwen3 Effect-Family Breakdown",
            "",
            "| Family | 8B optimal | 14B optimal | 32B optimal | "
            "8B attack | 14B attack | 32B attack |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for family in qwen["Qwen3-8B"]["by_primary_effect_family"]:
        cells = []
        for name in ("Qwen3-8B", "Qwen3-14B", "Qwen3-32B-AWQ"):
            row = qwen[name]["by_primary_effect_family"][family]
            cells.append(pct(row["optimal_path_successes"], 97 * 5))
        for name in ("Qwen3-8B", "Qwen3-14B", "Qwen3-32B-AWQ"):
            row = qwen[name]["by_primary_effect_family"][family]
            cells.append(pct(row["attack_path_selections"], 97 * 5))
        lines.append(f"| `{family}` | " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## Qwen3 Route-Length Breakdown",
            "",
            "| Stratum | 8B optimal | 14B optimal | 32B optimal | "
            "8B capable | 14B capable | 32B capable |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for length in qwen["Qwen3-8B"]["by_route_length"]:
        cases = 258 if length.startswith("l3") else 259
        cells = []
        for name in ("Qwen3-8B", "Qwen3-14B", "Qwen3-32B-AWQ"):
            row = qwen[name]["by_route_length"][length]
            cells.append(pct(row["optimal_path_successes"], cases * 5))
        for name in ("Qwen3-8B", "Qwen3-14B", "Qwen3-32B-AWQ"):
            row = qwen[name]["by_route_length"][length]
            cells.append(pct(row["capable_cases"], cases))
        lines.append(f"| `{length}` | " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## Statistical Boundary",
            "",
            "- Current 8B/14B runs each retain 3,880 private attempt manifests for 776 cases. "
            "No inference rerun is needed for paired intervals.",
            "- Use `scripts/report_v13_evidence.py` to validate manifests and compute current "
            "case-clustered intervals; do not substitute historical intervals.",
            "- Shared scenario digests alone do not establish code or serving equivalence.",
            "",
            "## Next Experiments",
            "",
            "1. Validate current outcomes and compute paired intervals without new inference.",
            "2. Audit cross-family 776-case runs; separate pilots and infrastructure failures.",
            "3. Audit existing ablations for effective manipulations before running new ones.",
            "4. Review f3/f4/f6 and long-route failures; distinguish outcome flags from causes.",
            "5. Freeze protocol and serving provenance before any missing-model run.",
            "",
            "## Provenance",
            "",
            "- Scenario count: 776; attempts per model: 3,880; seeds: 1701-1705.",
            "- Scenario-set digest: `299d3938c4b5bc582e6d1e2ef"
            "778bd2756f44774425a57785313049c436be0ba`.",
            "- Raw prompts, responses, graphs, fixtures, and hidden certificates are not included.",
        ]
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
