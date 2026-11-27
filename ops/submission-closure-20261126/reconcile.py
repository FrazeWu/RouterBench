"""Analysis-only reconciliation of sealed graph records; never retries model calls."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import yaml


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_inventory(source: Path, protocol: dict, paths: list[str]) -> dict[str, str]:
    mapping = {}
    for relative in paths:
        name = relative + "/scenario.yaml"
        path = source / name
        if digest(path) != protocol["source_files"][name]:
            raise ValueError("canonical scenario source changed")
        canonical = yaml.safe_load(path.read_text())["scenario_id"]
        if canonical in mapping.values():
            raise ValueError("duplicate canonical scenario ID")
        mapping[relative] = canonical
    return mapping


def validate_records(
    records: list[dict],
    ids: set[str],
    seeds: list[int],
    variant: str,
    protocol: dict,
    model: str,
    audits: dict,
) -> None:
    expected = {(case, seed) for case in ids for seed in seeds}
    actual = [(r["scenario_id"], r["seed"]) for r in records]
    if len(set(actual)) != len(actual) or set(actual) != expected:
        raise ValueError("raw records do not cover the exact canonical case/seed inventory")
    for row in records:
        metadata = row["metadata"]
        if (
            metadata["protocol_id"] != protocol["protocol_id"]
            or metadata["source_revision"] != protocol["source_revision"]
            or metadata["model_fingerprint"] != protocol["models"][model]["fingerprint"]
            or metadata["variant"] != variant
            or row["scenario_digest"] != audits[row["scenario_id"]]["scenario_digest"]
        ):
            raise ValueError("sealed graph record source/model/protocol identity mismatch")
        if row["status"] not in {"valid", "invalid_output", "backend_failure"}:
            raise ValueError("unknown graph measurement status")


def reconcile(base: Path) -> dict:
    protocol = json.loads((base / "frozen-protocol.json").read_text())
    source = base / "source"
    if subprocess.check_output(["git", "status", "--short"], cwd=source):
        raise ValueError("frozen execution source changed")
    if (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
        != protocol["source_revision"]
    ):
        raise ValueError("frozen execution revision changed")
    sys.path.insert(0, str(source / "src"))
    from routebench.submission.analysis import graph_report
    from routebench.submission.common import durable_json

    inventory = canonical_inventory(source, protocol, protocol["graph_cases"])
    subset = canonical_inventory(source, protocol, protocol["next_hop_cases"])
    audit_root = base / "runs/E9/attempt-0/phase"
    audit_result = json.loads((audit_root / "phase-result.json").read_text())
    audits = {}
    for path in (audit_root / "cases").glob("*.json"):
        if digest(path) != audit_result["artifact_files"][str(path.relative_to(audit_root))]:
            raise ValueError("independent optimum audit identity changed")
        row = json.loads(path.read_text())
        audits[row["scenario_id"]] = row
    index = json.loads((base / "runs/execution-index.json").read_text())
    receipts = {}
    for job in index["jobs"]:
        if job["status"] not in {"complete", "unavailable"} or not job["attempts"]:
            continue
        if not (job["key"].startswith("E1-") or job["key"] == "next-hop"):
            continue
        attempt = job["attempts"][-1]
        work = Path(attempt["output"]) / "phase"
        result_path = work / "phase-result.json"
        result = json.loads(result_path.read_text())
        if result["status"] == "aborted" and result["error_kind"] != "ValueError":
            continue
        if (
            result["protocol_id"] != protocol["protocol_id"]
            or result["source_revision"] != protocol["source_revision"]
        ):
            raise ValueError("reconciliation parent identity mismatch")
        destination = (
            base / "analysis-reconciliation" / f"{job['key']}-attempt-{attempt['index']}.json"
        )
        if destination.exists():
            saved = json.loads(destination.read_text())
            if saved["original_phase_result_sha256"] != digest(result_path):
                raise ValueError("reconciled phase changed")
            receipts[job["key"]] = str(destination)
            continue
        variants = ("B", "C", "D", "E") if job["key"] == "next-hop" else ("A",)
        selected = subset if job["key"] == "next-hop" else inventory
        files = sorted(work.glob("*/attempts/*/complete.json"))
        if len(files) != len(selected) * len(protocol["configuration"]["seeds"]) * len(variants):
            continue  # Incomplete phases are never completed through analysis.
        for name, expected in result["artifact_files"].items():
            if digest(work / name) != expected:
                raise ValueError("sealed phase artifact changed")
        records = [json.loads(path.read_text()) for path in files]
        for path, row in zip(files, records, strict=True):
            if json.loads(path.with_name("manifest.json").read_text()) != row:
                raise ValueError("completion marker differs from its native record")
        model = "qwen3-14b" if job["key"] == "next-hop" else job["key"].removeprefix("E1-")
        summaries = {}
        for variant in variants:
            group = [row for row in records if row["metadata"]["variant"] == variant]
            validate_records(
                group,
                set(selected.values()),
                protocol["configuration"]["seeds"],
                variant,
                protocol,
                model,
                audits,
            )
            summary = graph_report(group)
            summary["original_phase_status"] = result["status"]
            summary["formal_phase_valid"] = (
                result["status"] == "complete" and summary["formal_phase_valid"]
            )
            summary["analysis_status"] = "descriptive_reconciliation_of_sealed_records"
            summaries[variant] = summary
        receipt = {
            "status": "complete_inventory_reconciled_for_descriptive_analysis",
            "job": job["key"],
            "protocol_id": protocol["protocol_id"],
            "execution_source_revision": protocol["source_revision"],
            "analysis_controller_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, text=True
            ).strip(),
            "original_phase_status": result["status"],
            "original_error_kind": result["error_kind"],
            "original_phase_result_sha256": digest(result_path),
            "original_phase_result": str(result_path),
            "directory_to_registered_id": selected,
            "all_expected_case_seed_records_present": True,
            "records": len(records),
            "record_statuses": dict(Counter(r["status"] for r in records)),
            "summaries": summaries,
            "new_model_calls": 0,
            "original_phase_or_queue_status_changed": False,
            "interpretation": (
                "Directory aliases differ from registered IDs. "
                "Analysis reads canonical source IDs; the original aborted phase remains aborted "
                "and backend failures stay in the denominator."
            ),
            "recorded_unix": time.time(),
        }
        durable_json(destination, receipt)
        receipts[job["key"]] = str(destination)
    return receipts


if __name__ == "__main__":
    print(json.dumps(reconcile(Path(__file__).resolve().parent.parent)))
