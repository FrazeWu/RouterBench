"""Collect or fit one frozen, independently reviewed defense study.

This entry point cannot freeze a protocol, accept a source review, open test
outcomes or certify efficacy. Collection owns a local task-model server; fitting
uses only the completed, verified training collection from this same protocol.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import gc
import importlib.metadata
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from routebench.defense.freeze import StudySpec
from routebench.defense.lora import file_digest, train_lora
from routebench.defense.pilot import GpuTelemetry, ThermalPacer, clean_revision
from routebench.defense.protocol import AcquisitionLedger
from routebench.defense.relay import StagedResponseRelay
from routebench.defense.study import (
    AcquisitionPurpose,
    FrozenStudy,
    MeteredStudyAgent,
    collect_training,
    load_frozen_study,
    load_training_phase,
    private_output,
    write_exclusive,
)


def server_address(spec: StudySpec) -> tuple[str, int]:
    url = urlsplit(spec.agent.endpoint)
    if (
        url.scheme != "http"
        or url.hostname != "127.0.0.1"
        or url.port is None
        or url.path != "/v1"
        or url.query
        or url.fragment
        or url.username
        or url.password
    ):
        raise ValueError("frozen collection requires an explicit http://127.0.0.1:PORT/v1 endpoint")
    return url.hostname, url.port


def server_command(study: FrozenStudy) -> list[str]:
    host, port = server_address(study.spec)
    return [
        sys.executable,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--host",
        host,
        "--port",
        str(port),
        "--model",
        study.spec.task_model_path,
        "--served-model-name",
        study.spec.agent.model,
        "--dtype",
        "bfloat16",
        "--max-model-len",
        str(study.spec.agent.context_tokens),
        "--max-num-seqs",
        "1",
        "--gpu-memory-utilization",
        "0.90",
        "--generation-config",
        "vllm",
        "--enforce-eager",
    ]


class OwnedTaskServer:
    """Only the subprocess created by this run may serve frozen collection."""

    def __init__(self, study: FrozenStudy, output: Path, telemetry: GpuTelemetry):
        self.study, self.output, self.telemetry = study, output, telemetry
        self.process: subprocess.Popen[bytes] | None = None
        self.log: Any = None

    def __enter__(self) -> OwnedTaskServer:
        host, port = server_address(self.study.spec)
        with socket.socket() as probe:
            probe.bind((host, port))
        command = server_command(self.study)
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(self.study.spec.resources.task_agent_gpu))
        self.log = (self.output / "task-server.private.log").open("xb")
        try:
            self.process = subprocess.Popen(
                command,
                env=env,
                stdout=self.log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            write_exclusive(
                self.output / "task-server.json",
                {
                    "command": command,
                    "pid": self.process.pid,
                    "physical_gpu": self.study.spec.resources.task_agent_gpu,
                    "started_unix": time.time(),
                    "source_revision": self.study.revision,
                    "formal_protocol_id": self.study.protocol_id,
                },
            )
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                self.check()
                try:
                    response = httpx.get(self.study.spec.agent.endpoint + "/models", timeout=1)
                    response.raise_for_status()
                    if self.study.spec.agent.model in {
                        item["id"] for item in response.json()["data"]
                    }:
                        return self
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    pass
                time.sleep(1)
            raise RuntimeError("owned task-model server did not become ready within 600 seconds")
        except BaseException:
            self.__exit__()
            raise

    def check(self) -> None:
        self.telemetry.check()
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("owned task-model server exited")

    def __exit__(self, *args: object) -> None:
        if self.process is not None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
        if self.log is not None:
            self.log.close()


async def collect(
    study: FrozenStudy,
    output: Path,
    ledger: AcquisitionLedger,
    telemetry: GpuTelemetry,
    pacer: ThermalPacer,
) -> None:
    from transformers import AutoTokenizer  # type: ignore[import-not-found]

    tokenizer = AutoTokenizer.from_pretrained(study.spec.task_model_path, local_files_only=True)
    with OwnedTaskServer(study, output, telemetry) as server:
        calls = output / "calls"

        def before() -> None:
            server.check()
            pacer.before(study.spec.resources.task_agent_gpu)

        def record(row: dict[str, object]) -> None:
            write_exclusive(calls / f"call-{row['reservation_id']:08d}.private.json", row)

        def factory(purpose: AcquisitionPurpose, relay: StagedResponseRelay) -> MeteredStudyAgent:
            return MeteredStudyAgent(
                study.spec.agent,
                tokenizer=tokenizer,
                ledger=ledger,
                acquisition_purpose=purpose,
                before_call=before,
                after_call=pacer.after,
                record_call=record,
                relay=relay,
                text_receiver=relay.mode == "text",
            )

        await collect_training(study, output / "collection", factory)


def fit(
    study: FrozenStudy,
    collection: Path,
    output: Path,
    telemetry: GpuTelemetry,
    pacer: ThermalPacer,
) -> None:
    # Load provenance and complete-menu coverage before importing/allocating Torch.
    groups = load_training_phase(collection, study)
    if study.spec.compact.device == "cpu":
        raise ValueError("formal fitting requires an explicitly reserved CUDA device")
    gpu = int(study.spec.compact.device.split(":", 1)[1])

    def before() -> None:
        telemetry.check()
        pacer.before(gpu)

    for seed in study.spec.adapter_seeds:
        train_lora(
            groups,
            study.spec.compact,
            study.spec.lora.model_copy(update={"seed": seed}),
            output / f"adapter-seed-{seed}",
            source_revision=study.revision,
            formal_protocol_id=study.protocol_id,
            check=before,
            after_update=pacer.after,
        )
        import torch  # type: ignore[import-not-found]

        gc.collect()
        torch.cuda.empty_cache()
    write_exclusive(
        output / "fit-complete.json",
        {
            "source_revision": study.revision,
            "formal_protocol_id": study.protocol_id,
            "adapter_seeds": study.spec.adapter_seeds,
            "efficacy_evidence": False,
        },
    )


def run(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    if os.environ.get("CUDA_VISIBLE_DEVICES"):
        raise ValueError("unset CUDA_VISIBLE_DEVICES so frozen GPU IDs remain physical indices")
    if os.environ.get("CUDA_DEVICE_ORDER", "PCI_BUS_ID") != "PCI_BUS_ID":
        raise ValueError("formal GPU accounting requires CUDA_DEVICE_ORDER=PCI_BUS_ID")
    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    study = load_frozen_study(root, root / args.manifest)
    output = private_output(root, root / args.output)
    if args.phase == "fit":
        if args.collection is None:
            raise ValueError("fit requires the completed training --collection directory")
        collection = private_output(root, root / args.collection)
        load_training_phase(collection, study)
    else:
        server_address(study.spec)
    output.mkdir(parents=True, exist_ok=False)
    resources = study.spec.resources
    ledger = AcquisitionLedger(
        study.spec.acquisition_call_limit, study.spec.acquisition_token_limit
    )
    started, status, error_kind = time.time(), "aborted", None
    write_exclusive(
        output / "phase-manifest.json",
        {
            "phase": args.phase,
            "formal_protocol_id": study.protocol_id,
            "source_revision": study.revision,
            "frozen_manifest_digest": study.manifest_digest,
            "resources": resources.model_dump(mode="json"),
            "packages": {name: importlib.metadata.version(name) for name in ("httpx", "pydantic")},
            "started_unix": started,
            "collection": str(args.collection) if args.collection else None,
        },
    )
    pacer: ThermalPacer | None = None
    try:
        with GpuTelemetry(
            output / "telemetry.json",
            gpu_ids=resources.gpu_ids,
            maximum_celsius=resources.maximum_celsius,
        ) as telemetry:
            pacer = ThermalPacer(
                telemetry,
                minimum_gap_seconds=resources.minimum_request_gap_seconds,
                pause_celsius=resources.cooling_pause_celsius,
                resume_celsius=resources.cooling_resume_celsius,
                maximum_wait_seconds=resources.maximum_cooling_wait_seconds,
            )
            if args.phase == "collect":
                asyncio.run(collect(study, output, ledger, telemetry, pacer))
            else:
                assert args.collection is not None
                fit(study, root / args.collection, output, telemetry, pacer)
            telemetry.check()
            if clean_revision(root) != study.revision:
                raise ValueError("source changed during the formal phase")
        telemetry.check()
        status = "complete"
    except BaseException as error:
        error_kind = type(error).__name__
        raise
    finally:
        ended = time.time()
        write_exclusive(
            output / "phase-result.json",
            {
                "phase": args.phase,
                "status": status,
                "error_kind": error_kind,
                "source_revision": study.revision,
                "formal_protocol_id": study.protocol_id,
                "started_unix": started,
                "ended_unix": ended,
                "reserved_gpu_device_hours": (ended - started) * len(resources.gpu_ids) / 3600,
                "acquisition_calls": ledger.calls,
                "acquisition_charged_tokens": ledger.tokens,
                "pacing_wait_seconds": pacer.wait_seconds if pacer else 0,
                "collection_files": {
                    str(path.relative_to(output / "collection")): file_digest(path)
                    for path in sorted((output / "collection").rglob("*"))
                    if path.is_file()
                }
                if args.phase == "collect"
                else {},
                "efficacy_evidence": False,
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--phase", choices=("collect", "fit"), required=True)
    parser.add_argument("--collection", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
