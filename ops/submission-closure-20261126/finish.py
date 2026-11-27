"""Keep the fixed queue running and package its completed, validated reports."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from reconcile import reconcile

BASE = Path(__file__).resolve().parent.parent
SOURCE = BASE / "source"
RUNS = BASE / "runs"
RUNTIME = BASE.parent / "ecpa-final-230a11174cef/runtime-env/bin/python"


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def queue_running() -> bool:
    with (RUNS / "supervisor.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


def package(report_path: Path) -> None:
    report = read(report_path)
    target = BASE / "delivery"
    target.mkdir(exist_ok=True)
    reconciled = reconcile(BASE)
    reconciliation_index = {}
    for job, name in reconciled.items():
        receipt = read(Path(name))
        reconciliation_index[job] = {
            "path": name,
            "sha256": hashlib.sha256(Path(name).read_bytes()).hexdigest(),
        }
        if job.startswith("E1-") and job not in report["E1"]:
            report["E1"][job] = receipt["summaries"]["A"]
    reconciliation_path = target / "analysis-reconciliation-index.json"
    reconciliation_path.write_text(json.dumps(reconciliation_index, indent=2) + "\n")
    with (target / "planning.csv").open("w") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "model",
                "attempts",
                "cases",
                "optimal_attempt_rate",
                "ci95_lower",
                "ci95_upper",
                "case_successes_3_of_5",
                "formal_phase_valid",
                "original_phase_status",
                "analysis_status",
            ]
        )
        for model, data in sorted(report["E1"].items()):
            estimate = data["rates"]["optimal"]
            writer.writerow(
                [
                    model,
                    data["attempts"],
                    data["cases"],
                    estimate["estimate"],
                    *estimate["ci95"],
                    data["case_success_at_least_3_of_5"],
                    data["formal_phase_valid"],
                    data.get("original_phase_status", "complete"),
                    data.get("analysis_status", "native_complete_phase"),
                ]
            )
    with (target / "composition.csv").open("w") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["job", "metric", "estimate", "denominator", "ci95_lower", "ci95_upper", "clusters"]
        )
        for key, data in sorted(report["E2"].items()):
            overall = data["overall"]
            for metric, estimate in {
                **overall["rates"],
                "D_rec": overall["D_rec"],
                "D_plan": overall["D_plan"],
            }.items():
                writer.writerow(
                    [
                        key,
                        metric,
                        estimate["estimate"],
                        estimate["denominator"],
                        *(estimate["ci95"] or [None, None]),
                        estimate["clusters"],
                    ]
                )
    with (target / "supplements.csv").open("w") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "job",
                "arm",
                "episodes",
                "safe_completions",
                "violations",
                "search_expansions",
                "selector_cpu_seconds",
            ]
        )
        for key, data in sorted(report["supplements"].items()):
            for arm, row in sorted(data["by_arm"].items()):
                writer.writerow(
                    [
                        key,
                        arm,
                        *(
                            row[name]
                            for name in (
                                "episodes",
                                "safe_completions",
                                "violations",
                                "search_expansions",
                                "selector_cpu_seconds",
                            )
                        ),
                    ]
                )
    accounting_notes = {}
    cost_rows = {key: dict(value) for key, value in report["costs_all_attempts"].items()}
    for key, row in cost_rows.items():
        job, attempt_index = key.rsplit("/", 1)
        work = RUNS / job / f"attempt-{attempt_index}" / "phase"
        journal = work / "telemetry.jsonl"
        if journal.exists() and not (work / "telemetry.json").exists():
            # An interrupted warmup can leave a durable journal without final telemetry.
            # Zero in the native aggregation is missing occupancy, never a free GPU run.
            samples = [json.loads(line) for line in journal.read_text().splitlines() if line]
            row["reserved_gpu_device_hours"] = None
            row["reserved_gpu_device_hours_upper_bound"] = row["wall_seconds"] * 2 / 3600
            row["peak_celsius"] = {
                str(gpu): max((s["celsius"] for s in samples if s["gpu"] == gpu), default=None)
                for gpu in (0, 1)
            }
            accounting_notes[key] = {
                "interpretation": (
                    "interrupted startup; GPU occupancy unknown, elapsed-time upper bound reported"
                ),
                "native_occupancy_zero_is_missing": True,
                "journal_sha256": hashlib.sha256(journal.read_bytes()).hexdigest(),
                "reserved_gpu_device_hours_upper_bound": row[
                    "reserved_gpu_device_hours_upper_bound"
                ],
            }
    accounting_path = target / "cost-accounting-notes.json"
    accounting_path.write_text(json.dumps(accounting_notes, indent=2) + "\n")
    with (target / "costs.csv").open("w") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "attempt",
                "wall_seconds",
                "reserved_gpu_device_hours",
                "reserved_gpu_device_hours_upper_bound_if_unknown",
                "calls",
                "charged_tokens",
                "gpu0_peak_celsius",
                "gpu1_peak_celsius",
            ]
        )
        for key, row in sorted(cost_rows.items()):
            writer.writerow(
                [
                    key,
                    row["wall_seconds"],
                    row["reserved_gpu_device_hours"],
                    row.get("reserved_gpu_device_hours_upper_bound"),
                    row["persisted_calls"],
                    row["charged_tokens"],
                    row["peak_celsius"]["0"],
                    row["peak_celsius"]["1"],
                ]
            )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip()
    if revision != report["source_revision"] or subprocess.check_output(
        ["git", "status", "--short"], cwd=SOURCE
    ):
        raise ValueError("source snapshot no longer matches the frozen experiment")
    subprocess.run(
        ["git", "archive", "--format=tar.gz", f"--output={target / 'source.tar.gz'}", revision],
        cwd=SOURCE,
        check=True,
    )
    files = [
        BASE / "frozen-protocol.json",
        BASE / "historical-evidence-index.json",
        report_path,
        report_path.parent / "reproduction-index.json",
        *sorted(target.glob("*.csv")),
        target / "source.tar.gz",
        accounting_path,
        reconciliation_path,
    ]
    result = {
        "status": report["status"],
        "report": str(report_path),
        "source_revision": revision,
        "delivery_controller_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, text=True
        ).strip(),
        "files": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        "completed_unix": time.time(),
    }
    (target / "delivery-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "delivery": str(target)}), flush=True)


def main() -> None:
    binding = read(Path(__file__).parent / "identity.json")
    if (
        hashlib.sha256((BASE / "frozen-protocol.json").read_bytes()).hexdigest()
        != binding["manifest_sha256"]
    ):
        raise ValueError("delivery controller's frozen protocol changed")
    if subprocess.check_output(["git", "status", "--short"], cwd=Path(__file__).parent):
        raise ValueError("delivery controller must remain committed and clean")
    env = {
        key: value
        for key, value in os.environ.items()
        if key.lower() not in {"all_proxy", "http_proxy", "https_proxy"}
    }
    env.update(PYTHONPATH="src", CUDA_DEVICE_ORDER="PCI_BUS_ID")
    last_reconciliation = None
    while True:
        execution_index = read(RUNS / "execution-index.json")
        signature = [
            (job["key"], job["status"])
            for job in execution_index["jobs"]
            if job["status"] in {"complete", "unavailable"}
        ]
        if signature != last_reconciliation:
            print(json.dumps({"analysis_reconciliation": reconcile(BASE)}), flush=True)
            last_reconciliation = signature
        report = RUNS / "analysis/report.json"
        if report.exists() and (report.parent / "reproduction-index.json").exists():
            package(report)
            return
        if not queue_running():
            index = read(RUNS / "execution-index.json")
            if all(job["status"] in {"complete", "unavailable"} for job in index["jobs"]):
                recovered = RUNS / "analysis-recovery-1"
                if recovered.exists():
                    raise RuntimeError(
                        "sealed analysis failed; preserve all phases for independent review"
                    )
                with (RUNS / "analysis-recovery-1.log").open("x") as log:
                    subprocess.run(
                        [
                            str(RUNTIME),
                            "-m",
                            "scripts.analyze_submission",
                            "--manifest",
                            str(BASE / "frozen-protocol.json"),
                            "--runs",
                            str(RUNS),
                            "--output",
                            str(recovered),
                        ],
                        cwd=SOURCE,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                    )
                package(recovered / "report.json")
                return
            with (BASE / "supervisor-continuation.log").open("a") as log:
                process = subprocess.Popen(
                    [
                        str(RUNTIME),
                        "-m",
                        "scripts.run_submission_queue",
                        "--manifest",
                        str(BASE / "frozen-protocol.json"),
                        "--output",
                        str(RUNS),
                    ],
                    cwd=SOURCE,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                print(f"Resumed the unchanged frozen queue as PID {process.pid}", flush=True)
                process.wait()
        time.sleep(30)


if __name__ == "__main__":
    main()
