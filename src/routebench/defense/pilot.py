"""Development-only simulator reference, provenance, and GPU cost telemetry."""

from __future__ import annotations

import csv
import subprocess
import threading
import time
from pathlib import Path

from routebench.contracts import ActionRequest
from routebench.defense.compact import write_json
from routebench.defense.ecpa import ECPAEnvironment
from routebench.runtime.reference import InvalidRouteActionError, Preview
from routebench.scenarios.schema import AuthorityGrant, GraphEdgeSpec


class UnguardedSimulatorReference(ECPAEnvironment):
    """A distinct development-only arm; never install into a live executor.

    Keep graph reachability, typed actions, budgets, and simulator preconditions;
    bypass operational grants/policy so modeled harm can be measured. No fallback
    or menu replacement is selected in this arm. The ordinary ECPA class and its
    final checks are unchanged.
    """

    async def _check(
        self, edge: GraphEdgeSpec, extra_grants: tuple[AuthorityGrant, ...] = ()
    ) -> tuple[ActionRequest, Preview] | None:
        del extra_grants
        self.budget.charge("previews")
        try:
            return self._request(edge)
        except (InvalidRouteActionError, KeyError, ValueError, TypeError):
            return None


def clean_revision(root: Path) -> str:
    if subprocess.check_output(["git", "status", "--short"], cwd=root, text=True):
        raise ValueError("commit the source before measured development or formal runs")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


class ThermalLimit(RuntimeError):
    pass


class GpuTelemetry:
    """Sample actual device telemetry; phase occupancy is separately declared.

    Temperature limits stop further work at a phase/call boundary. They do not
    falsify a completed/censored episode. Unexpected telemetry failures are fatal.
    """

    def __init__(self, output: Path, *, gpu_ids: tuple[int, ...], maximum_celsius: int = 85):
        if not gpu_ids or not 40 <= maximum_celsius <= 90:
            raise ValueError("explicit GPU IDs and a valid thermal limit are required")
        self.output, self.gpu_ids, self.maximum_celsius = output, gpu_ids, maximum_celsius
        self.rows: list[dict[str, object]] = []
        self.stop = threading.Event()
        self.error: str | None = None
        self.thread = threading.Thread(target=self._sample_loop, daemon=True)

    def sample(self) -> None:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,temperature.gpu,memory.used,utilization.gpu,"
                "clocks_event_reasons.sw_thermal_slowdown,clocks_event_reasons.hw_thermal_slowdown",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        for values in csv.reader(result.stdout.splitlines(), skipinitialspace=True):
            index, name, temp, memory, utilization, sw, hw = [value.strip() for value in values]
            if int(index) not in self.gpu_ids:
                continue
            self.rows.append(
                {
                    "time_unix": time.time(),
                    "gpu": int(index),
                    "name": name,
                    "celsius": int(temp),
                    "memory_mib": int(memory),
                    "utilization_percent": int(utilization),
                    "software_thermal": sw,
                    "hardware_thermal": hw,
                }
            )
            if int(temp) >= self.maximum_celsius or sw == "Active" or hw == "Active":
                self.error = f"GPU {index} thermal limit/throttling observed at {temp} C"

    def _sample_loop(self) -> None:
        while not self.stop.wait(2):
            try:
                self.sample()
            except Exception as error:
                self.error = f"telemetry failed: {type(error).__name__}"
                break

    def check(self) -> None:
        if self.error:
            raise ThermalLimit(self.error)

    def __enter__(self) -> GpuTelemetry:
        self.sample()
        if {row["gpu"] for row in self.rows} != set(self.gpu_ids):
            raise ValueError("a requested GPU is not visible in telemetry")
        self.check()
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop.set()
        self.thread.join(timeout=12)
        write_json(self.output, {"samples": self.rows, "error": self.error})
