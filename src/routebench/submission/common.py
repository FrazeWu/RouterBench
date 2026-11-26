"""Durable records, measured local inference, and owned model-server lifetime."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from routebench.defense.pilot import GpuTelemetry, ThermalPacer
from routebench.defense.protocol import AcquisitionLedger
from routebench.planners.config import PlannerConfig
from routebench.planners.local_json import LocalJsonPlanner


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def durable_json(path: Path, value: Any, *, exclusive: bool = True) -> None:
    """Publish a complete fsynced record, preserving any existing final artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x") as handle:
            json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            os.link(temporary, path)
            temporary.unlink()
        else:
            os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


class JournalTelemetry(GpuTelemetry):
    """Keep each sampled interval durable even across a host reboot."""

    def sample(self) -> None:
        before = len(self.rows)
        super().sample()
        path = self.output.with_suffix(".jsonl")
        with path.open("a") as handle:
            for row in self.rows[before:]:
                handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


class ModelServer:
    def __init__(
        self,
        model: Path,
        name: str,
        directory: Path,
        telemetry: GpuTelemetry,
        *,
        context_tokens: int,
        gpu: int = 1,
        port: int = 8011,
    ) -> None:
        self.model, self.name, self.directory = model, name, directory
        self.telemetry, self.context_tokens, self.gpu, self.port = (
            telemetry,
            context_tokens,
            gpu,
            port,
        )
        self.process: subprocess.Popen[Any] | None = None
        self.log: Any = None

    def check(self) -> None:
        self.telemetry.check()
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("owned inference server exited")

    def __enter__(self) -> ModelServer:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", self.port))
        self.directory.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--model",
            str(self.model),
            "--served-model-name",
            self.name,
            "--dtype",
            "bfloat16",
            "--max-model-len",
            str(self.context_tokens),
            "--max-num-seqs",
            "1",
            "--gpu-memory-utilization",
            "0.90",
            "--generation-config",
            "vllm",
            "--enforce-eager",
        ]
        self.log = (self.directory / "server.private.log").open("x")
        try:
            self.process = subprocess.Popen(
                command,
                stdout=self.log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=dict(
                    os.environ, CUDA_DEVICE_ORDER="PCI_BUS_ID", CUDA_VISIBLE_DEVICES=str(self.gpu)
                ),
            )
            durable_json(
                self.directory / "server.json",
                {
                    "command": command,
                    "pid": self.process.pid,
                    "gpu": self.gpu,
                    "started_unix": time.time(),
                },
            )
            deadline = time.monotonic() + 600
            with httpx.Client(trust_env=False, timeout=1) as client:
                while time.monotonic() < deadline:
                    self.check()
                    try:
                        response = client.get(f"http://127.0.0.1:{self.port}/v1/models")
                        response.raise_for_status()
                        if self.name in {m["id"] for m in response.json()["data"]}:
                            return self
                    except (httpx.HTTPError, ValueError, KeyError):
                        pass
                    time.sleep(1)
            raise TimeoutError("owned inference server startup exceeded 600 seconds")
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *args: Any) -> None:
        if self.process is not None and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
        if self.log is not None:
            self.log.close()


class MeasuredGateway:
    """Use the existing planner wire format, metering each request durably."""

    def __init__(
        self,
        config: PlannerConfig,
        directory: Path,
        pacer: ThermalPacer,
        *,
        call_limit: int,
        gpu: int = 1,
    ) -> None:
        self.config, self.directory, self.pacer, self.gpu = config, directory, pacer, gpu
        context = config.generation.context_window
        if context is None:
            raise ValueError("a finite inference context is required")
        self.context = context
        self.ledger = AcquisitionLedger(call_limit, call_limit * context)
        self.pending_record: dict[str, Any] | None = None
        self.client = httpx.AsyncClient(
            timeout=120, trust_env=False, event_hooks={"response": [self.capture_usage]}
        )
        self.planner = LocalJsonPlanner(config, self.client)
        self.calls: list[dict[str, Any]] = []

    async def capture_usage(self, response: httpx.Response) -> None:
        await response.aread()
        if self.pending_record is None:
            return
        self.pending_record["http_status"] = response.status_code
        if response.is_success:
            body = response.json()
            usage = body.get("usage")
            if isinstance(usage, dict):
                self.pending_record["usage"] = usage

    async def complete(
        self, instruction: str, payload: dict[str, Any], schema: dict[str, Any], seed: int
    ) -> str:
        self.pacer.before(self.gpu)
        identifier = self.ledger.reserve("rollout", self.context)
        record: dict[str, Any] = {
            "reservation_id": identifier,
            "seed": seed,
            "maximum_reserved_tokens": self.context,
            "status": "error",
            "started_unix": time.time(),
        }
        self.pending_record = record
        began = time.perf_counter()
        try:
            content: str = await self.planner._complete(
                instruction, payload, seed, schema, sort_payload_keys=False
            )
            record["status"] = "complete"
            return content
        finally:
            actual = None
            usage = record.get("usage", {})
            if all(
                type(usage.get(k)) is int and usage[k] >= 0
                for k in ("prompt_tokens", "completion_tokens")
            ):
                actual = usage["prompt_tokens"] + usage["completion_tokens"]
            invalid_usage = actual is not None and actual > self.context
            self.ledger.reconcile(identifier, None if invalid_usage else actual)
            if invalid_usage:
                record["status"] = "invalid_reported_usage"
            record.update(
                charged_tokens=self.context if actual is None or invalid_usage else actual,
                elapsed_seconds=time.perf_counter() - began,
            )
            durable_json(self.directory / "calls" / f"call-{identifier:08d}.json", record)
            self.calls.append(record)
            self.pending_record = None
            self.pacer.after()
            if invalid_usage:
                raise ValueError("reported token usage exceeds the frozen context")

    async def aclose(self) -> None:
        await self.planner.aclose()
