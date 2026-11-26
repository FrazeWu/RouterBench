"""Engineering-only model startup/JSON probes, with no benchmark cases or scores."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import yaml

from routebench.defense.pilot import ThermalPacer
from routebench.planners.config import PlannerConfig
from routebench.submission.common import (
    JournalTelemetry,
    MeasuredGateway,
    ModelServer,
    durable_json,
)


async def probe(output: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    specification = yaml.safe_load((root / "configs/submission/closure-20261126.yaml").read_text())
    for key, model in specification["models"].items():
        work = output / key
        work.mkdir(parents=True, exist_ok=False)
        with JournalTelemetry(
            work / "telemetry.json", gpu_ids=(0, 1), maximum_celsius=85
        ) as telemetry:
            pacer = ThermalPacer(
                telemetry, minimum_gap_seconds=2, pause_celsius=70, resume_celsius=60
            )
            configuration = PlannerConfig.model_validate(
                {
                    "schema_version": 2,
                    "backend": "vllm",
                    "model": model["served_name"],
                    "endpoint": "http://127.0.0.1:8011/v1",
                    "disable_thinking": True,
                    "formal_run": False,
                    "generation": {
                        "temperature": 0,
                        "top_p": 1.0,
                        "max_tokens": 64,
                        "context_window": 32768,
                    },
                }
            )
            gateway = MeasuredGateway(configuration, work, pacer, call_limit=1)
            try:
                with ModelServer(
                    Path(model["path"]), model["served_name"], work, telemetry, context_tokens=32768
                ):
                    response = await gateway.complete(
                        'Return a JSON object with status equal to "ok".',
                        {},
                        {
                            "type": "object",
                            "properties": {"status": {"type": "string", "enum": ["ok"]}},
                            "required": ["status"],
                            "additionalProperties": False,
                        },
                        29,
                    )
                    if json.loads(response) != {"status": "ok"}:
                        raise ValueError("engineering JSON schema probe failed")
                durable_json(
                    work / "engineering-result.json",
                    {
                        "status": "complete",
                        "purpose": "startup_and_wire_format_only",
                        "benchmark_episodes": 0,
                        "calls": gateway.calls,
                    },
                )
            finally:
                await gateway.aclose()
        print(key, "engineering probe complete", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(probe(parser.parse_args().output))
