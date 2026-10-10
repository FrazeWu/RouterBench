"""Unified, aggregate-only validation and result analysis for experiments.

The module deliberately does not invoke a planner.  It validates scenario material and
collects already-written aggregate summaries so a small dry run can exercise the complete
experiment bookkeeping path before any model-backed evaluation is launched.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from routebench.runtime.graph import GraphAuditError, audit_candidate_graph
from routebench.scenarios.loader import load_scenario


@dataclass(frozen=True, slots=True)
class ScenarioValidation:
    path: str
    scenario_id: str | None
    schema_version: int | None
    split: str | None
    status: str
    terminal_paths: int | None = None
    error: str | None = None

    def payload(self) -> dict[str, object]:
        return {
            "path": self.path,
            "scenario_id": self.scenario_id,
            "schema_version": self.schema_version,
            "split": self.split,
            "status": self.status,
            "terminal_paths": self.terminal_paths,
            "error": self.error,
        }


def discover_scenarios(root: str | Path) -> tuple[Path, ...]:
    """Return deterministic scenario directories below ``root``."""

    base = Path(root).expanduser().resolve(strict=True)
    if not base.is_dir():
        raise ValueError(f"scenario root is not a directory: {base}")
    return tuple(sorted(path.parent for path in base.rglob("scenario.yaml")))


def _scenario_split(path: Path) -> str | None:
    try:
        bundle = load_scenario(path)
    except (OSError, ValueError):
        return None
    split = bundle.definition.metadata.split
    return split.value if split is not None else None


def validate_scenarios(
    root: str | Path,
    *,
    limit: int | None = None,
    split: str | None = None,
) -> tuple[ScenarioValidation, ...]:
    """Validate a bounded scenario prefix, auditing every v4 candidate graph."""

    if limit is not None and limit < 1:
        raise ValueError("validation limit must be positive")
    paths = discover_scenarios(root)
    if split is not None:
        paths = tuple(
            path
            for path in paths
            if _scenario_split(path) == split
        )
    records: list[ScenarioValidation] = []
    for path in paths[:limit] if limit is not None else paths:
        try:
            bundle = load_scenario(path)
            metadata = bundle.definition.metadata
            split_value = metadata.split.value if metadata.split is not None else None
            graph = bundle.definition.graph
            if graph is None:
                records.append(
                    ScenarioValidation(
                        path=str(path),
                        scenario_id=metadata.scenario_id,
                        schema_version=metadata.schema_version,
                        split=split_value,
                        status="valid_no_graph",
                    )
                )
                continue
            audit = audit_candidate_graph(bundle)
            records.append(
                ScenarioValidation(
                    path=str(path),
                    scenario_id=metadata.scenario_id,
                    schema_version=metadata.schema_version,
                    split=split_value,
                    status="valid_graph",
                    terminal_paths=audit.total_terminal_paths,
                )
            )
        except (ValueError, GraphAuditError) as error:
            records.append(
                ScenarioValidation(
                    path=str(path),
                    scenario_id=None,
                    schema_version=None,
                    split=None,
                    status="invalid",
                    error=str(error),
                )
            )
    return tuple(records)


def _number(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _rate(value: Any, denominator: Any) -> float | None:
    den = _number(denominator)
    return _number(value) / den if den else None


def collect_result_summaries(root: str | Path) -> tuple[dict[str, object], ...]:
    """Collect aggregate formal summaries without reading prompts or responses."""

    base = Path(root).expanduser().resolve(strict=True)
    rows: list[dict[str, object]] = []
    for path in sorted(base.rglob("formal-graph-summary.json")):
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
            overall = summary["overall"]
            scope = summary["scope"]
            metadata = summary.get("metadata", {})
            planner = metadata.get("planner", {}) if isinstance(metadata, dict) else {}
            runtime = metadata.get("inference_runtime", {}) if isinstance(metadata, dict) else {}
            attempts = _number(overall.get("planned_attempts"))
            cases = _number(scope.get("evaluated_cases"))
            rows.append(
                {
                    "source": str(path),
                    "model": planner.get("model", "unknown"),
                    "scope": scope.get("kind", "unknown"),
                    "cases": cases,
                    "planned_attempts": attempts,
                    "valid_attempts": _number(overall.get("valid_attempts")),
                    "backend_failures": _number(overall.get("backend_failures")),
                    "invalid_outputs": _number(overall.get("invalid_outputs")),
                    "optimal_rate": _rate(overall.get("optimal_path_successes"), attempts),
                    "capable_case_rate": _rate(overall.get("capable_cases"), cases),
                    "functional_rate": _rate(overall.get("functional_successes"), attempts),
                    "policy_rate": _rate(overall.get("policy_compliant_selections"), attempts),
                    "attack_rate": _rate(overall.get("attack_path_selections"), attempts),
                    "runtime": runtime.get("implementation", "unknown"),
                    "git_commit": (metadata.get("git", {}) or {}).get("commit"),
                    "status": (
                        "complete"
                        if _number(overall.get("backend_failures")) == 0
                        else "infrastructure_failure"
                    ),
                }
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            rows.append({"source": str(path), "status": "unreadable"})
    return tuple(rows)


def build_unified_report(
    validations: tuple[ScenarioValidation, ...], results: tuple[dict[str, object], ...]
) -> dict[str, object]:
    """Build one JSON-safe report used by both the CLI and Markdown writer."""

    return {
        "validation": {
            "scenarios_checked": len(validations),
            "valid": sum(item.status != "invalid" for item in validations),
            "invalid": sum(item.status == "invalid" for item in validations),
            "graph_scenarios": sum(item.status == "valid_graph" for item in validations),
            "records": [item.payload() for item in validations],
        },
        "results": {
            "summaries_found": len(results),
            "complete_summaries": sum(item.get("status") == "complete" for item in results),
            "records": list(results),
        },
    }


def write_unified_report(report: dict[str, object], output_root: str | Path) -> tuple[Path, Path]:
    """Write machine-readable JSON and aggregate-only Markdown outputs."""

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "unified-experiment-report.json"
    markdown_path = root / "unified-experiment-report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validation = report["validation"]
    results = report["results"]
    assert isinstance(validation, dict) and isinstance(results, dict)
    lines = [
        "# RouteBench Unified Experiment Report",
        "",
        "This report validates scenario material and summarizes existing aggregate results. "
        "It does not invoke a model and stores no prompts or raw responses.",
        "",
        "## Validation",
        "",
        f"- Scenarios checked: `{validation['scenarios_checked']}`",
        f"- Valid: `{validation['valid']}`",
        f"- Invalid: `{validation['invalid']}`",
        f"- Candidate-graph scenarios: `{validation['graph_scenarios']}`",
        "",
        "## Existing result summaries",
        "",
        f"- Summary files found: `{results['summaries_found']}`",
        f"- Complete summaries: `{results['complete_summaries']}`",
        "",
        "| Model | Scope | Cases | Optimal | Capable cases | Functional | "
        "Policy | Attack | Status |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in results["records"]:
        if not isinstance(row, dict) or "model" not in row:
            continue
        def pct(value: object) -> str:
            return "-" if value is None else f"{float(value) * 100:.2f}%"
        lines.append(
            f"| `{row.get('model', 'unknown')}` | `{row.get('scope', 'unknown')}` | "
            f"{row.get('cases', 0)} | {pct(row.get('optimal_rate'))} | "
            f"{pct(row.get('capable_case_rate'))} | {pct(row.get('functional_rate'))} | "
            f"{pct(row.get('policy_rate'))} | {pct(row.get('attack_rate'))} | "
            f"{row.get('status', 'unknown')} |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
