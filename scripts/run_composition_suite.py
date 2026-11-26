"""Measure the fixed isolated capability, local-policy, recognition and planning units."""

from __future__ import annotations

import argparse
import asyncio
import signal
import time
from pathlib import Path
from typing import Any

import httpx

from routebench.defense.lora import file_digest
from routebench.defense.pilot import ThermalPacer
from routebench.planners.config import PlannerConfig
from routebench.planners.local_json import PlannerResponseError
from routebench.submission.common import (
    JournalTelemetry,
    MeasuredGateway,
    ModelServer,
    durable_json,
)
from routebench.submission.composition import load_pair
from routebench.submission.composition_inference import UNITS, measure_unit
from routebench.submission.protocol import load_protocol


async def measure(args: argparse.Namespace, protocol: dict[str, Any], work: Path) -> None:
    root = Path(protocol["source_root"])
    model = protocol["models"][args.model]
    paths = protocol["composition_cases"][args.split]
    presentations = 1 if args.split == "development" else 2
    total = len(paths) * presentations * len(UNITS)
    configuration = protocol["configuration"]
    config = PlannerConfig.model_validate(
        {
            "schema_version": 2,
            "backend": "vllm",
            "model": model["served_name"],
            "endpoint": "http://127.0.0.1:8011/v1",
            "generation": {
                k: v
                for k, v in configuration["graph_generation"].items()
                if k != "disable_thinking"
            },
            "formal_run": True,
            "disable_thinking": True,
        }
    )
    resources = configuration["resources"]
    state = {
        "status": "starting",
        "completed": 0,
        "total": total,
        "phase": "E2",
        "split": args.split,
        "model": args.model,
        "protocol_id": protocol["protocol_id"],
    }
    with JournalTelemetry(
        work / "telemetry.json", gpu_ids=(0, 1), maximum_celsius=resources["maximum_celsius"]
    ) as telemetry:
        pacer = ThermalPacer(
            telemetry,
            minimum_gap_seconds=resources["graph_gap_seconds"],
            pause_celsius=resources["graph_cooling_pause_celsius"],
            resume_celsius=resources["graph_cooling_resume_celsius"],
            maximum_wait_seconds=300,
        )
        gateway = MeasuredGateway(config, work, pacer, call_limit=total * 13)
        try:
            with ModelServer(
                Path(model["path"]),
                model["served_name"],
                work,
                telemetry,
                context_tokens=32768,
                gpu=1,
            ) as server:
                for path in paths:
                    pair = load_pair(root / path)
                    for presentation in range(presentations):
                        for unit in UNITS:
                            server.check()
                            before = len(gateway.calls)
                            began = time.perf_counter()
                            result: dict[str, Any] = {"correct": False}
                            status = "complete"
                            error = None
                            try:
                                result = await measure_unit(pair, presentation, unit, gateway)
                            except (
                                ValueError,
                                KeyError,
                                TypeError,
                                PlannerResponseError,
                            ) as failure:
                                status = "invalid_output"
                                error = type(failure).__name__
                            except httpx.HTTPError as failure:
                                status = "backend_failure"
                                error = type(failure).__name__
                            record = {
                                "pair_id": pair.pair_id,
                                "family": pair.metadata["semantic_family"],
                                "kind": pair.metadata["kind"],
                                "split": args.split,
                                "model": args.model,
                                "presentation": presentation,
                                "unit": unit,
                                "status": status,
                                "error_kind": error,
                                "elapsed_seconds": time.perf_counter() - began,
                                "calls": gateway.calls[before:],
                                "protocol_id": protocol["protocol_id"],
                                **result,
                            }
                            durable_json(
                                work / "units" / f"{pair.pair_id}_{presentation}_{unit}.json",
                                record,
                            )
                            state.update(
                                status="running",
                                completed=state["completed"] + 1,
                                updated_unix=time.time(),
                            )
                            durable_json(args.output / "status.json", state, exclusive=False)
        finally:
            await gateway.aclose()
    durable_json(
        work / "summary.json",
        {
            "status": "complete",
            "units": total,
            "model": args.model,
            "split": args.split,
            "acquisition_calls": gateway.ledger.calls,
            "acquisition_charged_tokens": gateway.ledger.tokens,
            "pacing_wait_seconds": pacer.wait_seconds,
        },
    )


def stopped(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt("stopped composition stage")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--split", choices=["development", "test"], required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, stopped)
    protocol = load_protocol(args.manifest, model_key=args.model)
    args.output.mkdir(parents=True, exist_ok=False)
    work = args.output / "phase"
    work.mkdir()
    began = time.time()
    durable_json(
        work / "phase-manifest.json",
        {
            "phase": "E2",
            "split": args.split,
            "model": args.model,
            "protocol_id": protocol["protocol_id"],
            "source_revision": protocol["source_revision"],
            "started_unix": began,
        },
    )
    status, error = "aborted", None
    try:
        asyncio.run(measure(args, protocol, work))
        status = "complete"
    except BaseException as failure:
        error = type(failure).__name__
        raise
    finally:
        durable_json(
            work / "phase-result.json",
            {
                "status": status,
                "error_kind": error,
                "phase": "E2",
                "model": args.model,
                "split": args.split,
                "protocol_id": protocol["protocol_id"],
                "source_revision": protocol["source_revision"],
                "started_unix": began,
                "ended_unix": time.time(),
                "artifact_files": {
                    str(p.relative_to(work)): file_digest(p)
                    for p in sorted(work.rglob("*"))
                    if p.is_file() and p.name != "phase-result.json"
                },
            },
        )
        durable_json(
            args.output / "status.json",
            {
                "status": status,
                "phase": "E2",
                "model": args.model,
                "split": args.split,
                "completed": len(list((work / "units").glob("*.json"))),
            },
            exclusive=False,
        )


if __name__ == "__main__":
    main()
