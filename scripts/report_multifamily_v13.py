#!/usr/bin/env python3
"""Report the frozen v13 multi-family pilot and full-run inventory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/private/formal-v13-multifamily-pilot-20261004.md"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    family: str
    scale: str
    formal_root: Path | None = None
    pilot_root: Path | None = None
    formal_eligible: bool = True


MODELS = (
    ModelSpec(
        "Qwen3-8B", "Qwen3", "8B",
        formal_root=ROOT / "artifacts/private/formal-v3-776-20260929/qwen3-8b-v13",
    ),
    ModelSpec(
        "Qwen3-14B", "Qwen3", "14B",
        formal_root=ROOT / "artifacts/private/formal-v3-776-20260929/qwen3-14b-v13",
    ),
    ModelSpec(
        "Qwen3-32B-AWQ",
        "Qwen3",
        "32B",
        formal_root=ROOT / "artifacts/private/formal-v3-776-20260929/qwen3-32b-awq-v13",
    ),
    ModelSpec(
        "DeepSeek-R1-Distill-Qwen-7B",
        "DeepSeek-Qwen",
        "7B",
        pilot_root=ROOT / "artifacts/private/local-v13-deepseek7-pilot-20261005",
        formal_root=ROOT / "artifacts/private/formal-v13-deepseek7-776-20261005",
    ),
    ModelSpec(
        "Qwen2.5-7B",
        "Qwen2.5",
        "7B",
        formal_root=ROOT / "artifacts/private/formal-v13-qwen25-7b-20261004",
        pilot_root=ROOT / "artifacts/private/cross-family-qwen25-7b-v13-20261004-retry1",
    ),
    ModelSpec(
        "Qwen2.5-14B",
        "Qwen2.5",
        "14B",
        formal_root=ROOT / "artifacts/private/formal-v13-qwen25-14b-20261004",
        pilot_root=ROOT / "artifacts/private/cross-family-qwen25-14b-v13-retry2-20261004/result",
        formal_eligible=False,
    ),
    ModelSpec(
        "Llama3.1-8B",
        "Llama",
        "8B",
        formal_root=ROOT / "artifacts/private/formal-v13-llama31-8b-20261004",
        pilot_root=ROOT / "artifacts/private/cross-family-llama31-8b-v13-20261003",
    ),
    ModelSpec(
        "Gemma3-12B",
        "Gemma",
        "12B",
        formal_root=ROOT / "artifacts/private/formal-v13-gemma3-12b-20261004",
        pilot_root=ROOT / "artifacts/private/cross-family-gemma3-12b-v13-20261004/result",
        formal_eligible=False,
    ),
    ModelSpec(
        "Gemma3-1B",
        "Gemma3",
        "1B",
        formal_root=ROOT / "artifacts/private/formal-v13-gemma3-1b-776-20261005",
        pilot_root=ROOT / "artifacts/private/local-v13-gemma3-1b-pilot-20261005-rerun",
    ),
    ModelSpec(
        "Mistral-7B",
        "Mistral",
        "7B",
        formal_root=ROOT / "artifacts/private/formal-v13-mistral-7b-20261004",
        pilot_root=ROOT / "artifacts/private/cross-family-mistral-7b-v13-20261004/result",
        formal_eligible=False,
    ),
)


def percent(value: int, total: int) -> str:
    return f"{100 * value / total:.2f}%"


def load(spec: ModelSpec) -> tuple[dict, dict, str] | None:
    roots = (
        ("complete_formal_benchmark", spec.formal_root),
        ("formal_prefix", spec.pilot_root),
    )
    for scope, root in roots:
        if root is None:
            continue
        summary_path = root / "formal-graph-summary.json"
        manifest_path = root / "run-manifest.json"
        if summary_path.is_file() and manifest_path.is_file():
            return (
                json.loads(summary_path.read_text(encoding="utf-8")),
                json.loads(manifest_path.read_text(encoding="utf-8")),
                scope,
            )
    return None


def main() -> None:
    rows: list[tuple[ModelSpec, dict, dict, str]] = []
    pending: list[str] = []
    pending_formal: list[str] = []
    for spec in MODELS:
        loaded = load(spec)
        if loaded is None:
            pending.append(spec.name)
            continue
        if (
            spec.formal_eligible
            and spec.formal_root is not None
            and not (spec.formal_root / "formal-graph-summary.json").is_file()
            and spec.pilot_root is not None
            and (spec.pilot_root / "formal-graph-summary.json").is_file()
        ):
            pending_formal.append(spec.name)
        rows.append((spec, loaded[0], loaded[1], loaded[2]))

    lines = [
        "# RouteBench v13 Multi-Family Model Comparison",
        "",
        "## Protocol",
        "",
        "- Same v13 permutation-balanced incremental-edge interface, evaluator, graph inventory, "
        "temperature 0, top-p 1, max tokens 2048, and 5 seeds (1701-1705).",
        "- The independent unit is the scenario case; a capable case has at least 3/5 optimal "
        "selections.",
        "- 776-case rows are formal benchmark results. 100-case rows are prefix pilots and are "
        "not pooled into a formal ranking.",
        "",
        "## Results",
        "",
        "| Model | Family | Scale | Scope | Cases | Valid | Optimal | Capable | Policy | "
        "Attack | Runtime | Commit |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for spec, summary, manifest, _source in rows:
        overall = summary["overall"]
        scope = summary["scope"]
        metadata = manifest["metadata"]
        cases = int(scope["evaluated_cases"])
        attempts = int(overall["planned_attempts"])
        runtime = metadata["inference_runtime"]
        lines.append(
            f"| `{spec.name}` | {spec.family} | {spec.scale} | `{scope['kind']}` | {cases} | "
            f"{overall['valid_attempts']}/{attempts} | "
            f"{percent(overall['optimal_path_successes'], attempts)} | "
            f"{percent(overall['capable_cases'], cases)} | "
            f"{percent(overall['policy_compliant_selections'], attempts)} | "
            f"{percent(overall['attack_path_selections'], attempts)} | "
            f"{runtime['implementation']} {runtime['version']} | "
            f"`{metadata['git']['commit'][:12]}` |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Compare rows within the same scope first. The pilot rows establish family/scale "
            "coverage and infrastructure validity; they do not replace the 776-case estimate.",
            "- Attack-path selection is a simulator outcome for an unsafe branch, not execution "
            "against real private data or production systems.",
            "- A backend or context incompatibility is reported as infrastructure exclusion, not "
            "as a capability score.",
            "",
            "## Pending Or Excluded",
            "",
        ]
    )
    if pending:
        lines.extend(f"- `{name}`: artifact not complete yet." for name in pending)
    if pending_formal:
        lines.extend(
            f"- `{name}`: 776-case formal run pending; "
            "the displayed row is still the 100-case pilot."
            for name in pending_formal
        )
    lines.extend(
        [
            "- Gemma2-9B/27B: native context configuration is incompatible with the frozen 32K "
            "protocol.",
            "- Llama3.3-70B-AWQ: single-node launch exceeded available KV/profile memory; no "
            "capability score is assigned.",
            "- Qwen2.5-14B: the available single-GPU vLLM 0.7.3 runtime cannot satisfy the "
            "frozen 32K context contract; its 100-case pilot remains diagnostic only.",
            "- Mistral-7B: vLLM 0.7.3 fails while reading the model rotary configuration "
            "(`partial_rotary_factor=None`); its 100-case pilot remains diagnostic only.",
            "- Gemma3-12B: vLLM 0.7.3 fails because `Gemma3Config` lacks `vocab_size`; "
            "its 100-case pilot remains diagnostic only.",
            "- Gemma3-4B: vLLM 0.7.3 fails because `Gemma3Config` lacks `vocab_size`; "
            "no capability score is assigned.",
            "- DeepSeek-R1-Distill-Qwen-14B: single A100 cannot provide the frozen 32K KV "
            "cache (maximum 22,224 tokens at the configured memory limit); no score is assigned.",
            "- InternLM2.5-7B: vLLM tokenizer conversion fails on the local tokenizer.model; "
            "no capability score is assigned.",
            "- Zephyr-7B and Dolphin-2.6-Mixtral-8x7B: current vLLM MistralCommonTokenizer "
            "rejects the tokenizer kwargs; no capability score is assigned.",
            "- Mistral Small 3.2-24B: vLLM 0.7.3 cannot load its Mistral3 config in the current "
            "runtime; the Mistral-7B pilot is the runnable family baseline.",
            "",
            "## Provenance",
            "",
            "All included rows have a run manifest with model-weight hash, scenario digest, "
            "runtime identity, and clean Git revision. Raw prompts and model responses are not "
            "included in this report.",
            "",
        ]
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
