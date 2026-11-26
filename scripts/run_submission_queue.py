"""Durably execute the fixed matrix with at most one infrastructure recovery per phase."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from routebench.defense.lora import file_digest
from routebench.submission.common import durable_json, read_json
from routebench.submission.protocol import load_protocol


def jobs() -> list[dict[str, Any]]:
    result = [
        {"key": "E9", "module": "scripts.run_submission_graph", "arguments": ["--phase", "E9"]}
    ]
    for model in ("qwen3-14b", "qwen3-1.7b", "qwen2.5-7b"):
        result.append(
            {
                "key": f"E1-{model}",
                "module": "scripts.run_submission_graph",
                "arguments": ["--phase", "E1", "--model", model],
            }
        )
    for split in ("development", "test"):
        for model in ("qwen3-14b", "qwen3-1.7b", "qwen2.5-7b"):
            result.append(
                {
                    "key": f"E2-{split}-{model}",
                    "module": "scripts.run_composition_suite",
                    "arguments": ["--split", split, "--model", model],
                }
            )
    result.append(
        {
            "key": "next-hop",
            "module": "scripts.run_submission_graph",
            "arguments": ["--phase", "next-hop", "--model", "qwen3-14b"],
        }
    )
    for split in ("tune", "calibration", "test"):
        result.append(
            {
                "key": f"E4-{split}",
                "module": "scripts.run_submission_supplement",
                "arguments": ["--phase", "E4", "--split", split],
            }
        )
    result.append(
        {"key": "E5", "module": "scripts.run_submission_supplement", "arguments": ["--phase", "E5"]}
    )
    for condition in ("menu_permutation", "wording_paraphrase"):
        result.append(
            {
                "key": f"E6-{condition}",
                "module": "scripts.run_submission_supplement",
                "arguments": ["--phase", "E6", "--condition", condition],
            }
        )
    return result


def interrupted_result(output: Path, protocol: dict[str, Any]) -> dict[str, Any]:
    work = output / "phase"
    work.mkdir(parents=True, exist_ok=True)
    manifest = work / "phase-manifest.json"
    parent = read_json(manifest) if manifest.exists() else {}
    result = {
        "status": "aborted",
        "error_kind": "InfrastructureInterruption",
        "protocol_id": protocol["protocol_id"],
        "source_revision": protocol["source_revision"],
        "started_unix": parent.get("started_unix", output.stat().st_mtime),
        "ended_unix": time.time(),
        "conservative_inflight_tokens": 8192
        if parent.get("phase") in {"E4", "E5", "E6"}
        else 32768,
        "artifact_files": {
            str(p.relative_to(work)): file_digest(p) for p in sorted(work.rglob("*")) if p.is_file()
        },
        "interpretation": (
            "incomplete infrastructure attempt preserved; excluded from formal results"
        ),
    }
    durable_json(work / "phase-result.json", result)
    return result


def stop_owned_server(output: Path) -> None:
    path = output / "phase/server.json"
    if not path.exists():
        return
    server = read_json(path)
    pid = server["pid"]
    proc = Path(f"/proc/{pid}")
    if not proc.exists():
        return
    current_boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    if server.get("host_boot_id") != current_boot:
        return
    if server.get("process_start_ticks") != (proc / "stat").read_text().split()[21]:
        return
    command = (proc / "cmdline").read_bytes().split(b"\0")
    if b"vllm.entrypoints.openai.api_server" in command and os.getpgid(pid) == pid:
        os.killpg(pid, signal.SIGTERM)
        # The next phase will independently check the port and GPU state.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = load_protocol(args.manifest)
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output / "supervisor.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    index_path = args.output / "execution-index.json"
    if index_path.exists():
        index = read_json(index_path)
        if index["protocol_id"] != protocol["protocol_id"]:
            raise ValueError("queue resume changed protocol")
    else:
        index = {
            "protocol_id": protocol["protocol_id"],
            "source_revision": protocol["source_revision"],
            "jobs": [{**job, "status": "pending", "attempts": []} for job in jobs()],
            "started_unix": time.time(),
        }
        durable_json(index_path, index)
    for job in index["jobs"]:
        if job["status"] in {"complete", "unavailable"}:
            continue
        while len(job["attempts"]) <= 2:
            if job["attempts"]:
                last = job["attempts"][-1]
                previous = Path(last["output"])
                result_path = previous / "phase/phase-result.json"
                stop_owned_server(previous)
                result = (
                    read_json(result_path)
                    if result_path.exists()
                    else interrupted_result(previous, protocol)
                )
                last["result_sha256"] = file_digest(result_path)
                last["status"] = result["status"]
                if result["status"] == "complete":
                    job["status"] = "complete"
                    break
                infrastructure = result["error_kind"] in {
                    "ThermalLimit",
                    "TimeoutError",
                    "KeyboardInterrupt",
                    "InfrastructureInterruption",
                    "RuntimeError",
                    "ConnectError",
                    "ReadTimeout",
                }
                if not infrastructure or len(job["attempts"]) >= 2:
                    job["status"] = "unavailable"
                    job["unavailable_reason"] = result["error_kind"]
                    break
                if not (previous.parent / "recovery-decision.json").exists():
                    durable_json(
                        previous.parent / "recovery-decision.json",
                        {
                            "reason": result["error_kind"],
                            "failed_result_sha256": last["result_sha256"],
                            "configuration_changed": False,
                            "model_failures_retried": False,
                            "recovery_index": 1,
                            "recorded_unix": time.time(),
                        },
                    )
            attempt_index = len(job["attempts"])
            output = args.output / job["key"] / f"attempt-{attempt_index}"
            output.parent.mkdir(parents=True, exist_ok=True)
            command = [
                sys.executable,
                "-m",
                job["module"],
                "--manifest",
                str(args.manifest),
                "--output",
                str(output),
                *job["arguments"],
            ]
            entry = {
                "index": attempt_index,
                "output": str(output),
                "command": command,
                "status": "running",
                "started_unix": time.time(),
            }
            job["attempts"].append(entry)
            job["status"] = "running"
            durable_json(index_path, index, exclusive=False)
            print(
                json.dumps({"job": job["key"], "attempt": attempt_index, "status": "starting"}),
                flush=True,
            )
            with (output.parent / f"attempt-{attempt_index}.log").open("x") as log:
                process = subprocess.Popen(
                    command,
                    cwd=protocol["source_root"],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=dict(os.environ, PYTHONPATH="src"),
                )
                entry["pid"] = process.pid
                while process.poll() is None:
                    durable_json(
                        args.output / "status.json",
                        {
                            "status": "running",
                            "current_job": job["key"],
                            "attempt": attempt_index,
                            "updated_unix": time.time(),
                            "finished_jobs": sum(
                                j["status"] in {"complete", "unavailable"} for j in index["jobs"]
                            ),
                            "total_jobs": len(index["jobs"]),
                            "phase_status": read_json(output / "status.json")
                            if (output / "status.json").exists()
                            else {},
                        },
                        exclusive=False,
                    )
                    time.sleep(10)
                entry["exit_code"] = process.returncode
        durable_json(index_path, index, exclusive=False)
        print(json.dumps({"job": job["key"], "status": job["status"]}), flush=True)
    report_root = args.output / "analysis"
    if not report_root.exists():
        command = [
            sys.executable,
            "-m",
            "scripts.analyze_submission",
            "--manifest",
            str(args.manifest),
            "--runs",
            str(args.output),
            "--output",
            str(report_root),
        ]
        with (args.output / "analysis.log").open("x") as log:
            subprocess.run(
                command,
                cwd=protocol["source_root"],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                env=dict(os.environ, PYTHONPATH="src"),
            )
    durable_json(
        args.output / "status.json",
        {
            "status": "complete",
            "updated_unix": time.time(),
            "total_jobs": len(index["jobs"]),
            "completed_jobs": sum(j["status"] == "complete" for j in index["jobs"]),
            "unavailable_jobs": sum(j["status"] == "unavailable" for j in index["jobs"]),
            "report": str(report_root / "report.json"),
        },
        exclusive=False,
    )


if __name__ == "__main__":
    main()
