"""Collect, fit, tune, audit and test one frozen, reviewed defense study.

This entry point cannot freeze a protocol or accept a source review. Fresh test
collection requires completed fitting, tuning and fixed-policy calibration from
the same identity. A completed run can still fail the unchanged efficacy rule.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import gc
import importlib.metadata
import json
import os
import random
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from routebench.defense.collect import PolicyChoice
from routebench.defense.compact import CompactPolicy, LocalCandidateModel
from routebench.defense.comparison import (
    EvaluationSplit,
    PolicySession,
    comparison_analysis,
    load_comparison,
    load_fit_phase,
    phase_files,
    run_comparison,
    select_comparator,
)
from routebench.defense.contracts import content_hash
from routebench.defense.ecpa import DefenseObservation
from routebench.defense.freeze import StudySpec
from routebench.defense.lora import file_digest, train_lora
from routebench.defense.pilot import GpuTelemetry, ThermalPacer, clean_revision
from routebench.defense.policies import PerActionAuthorizationPolicy, PublicRulePolicy
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


class PacedStudySelector(CompactPolicy):
    """Measure every local selector invocation, including frozen fallbacks."""

    def __init__(
        self,
        model: LocalCandidateModel,
        *,
        use_adapter: bool,
        telemetry: GpuTelemetry,
        pacer: ThermalPacer,
        ledger: AcquisitionLedger,
        record: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__(model, use_adapter=use_adapter)
        self.telemetry, self.pacer, self.ledger, self.record = telemetry, pacer, ledger, record

    def choose(self, observation: DefenseObservation, *, rng: random.Random) -> PolicyChoice:
        # A forced menu is not an inference/fallback. Both compact arms take
        # the identical runtime choice, without reserving calls or model tokens.
        if len(observation.menu) == 1:
            return super().choose(observation, rng=rng)
        self.telemetry.check()
        self.pacer.before(int(self.model.config.device.split(":", 1)[1]))
        identifier = self.ledger.reserve("rollout", self.model.config.context_tokens)
        previous = len(self.model.calls)
        try:
            return super().choose(observation, rng=rng)
        finally:
            call = self.model.calls[-1] if len(self.model.calls) > previous else None
            tokens = (
                int(str(call["prompt_tokens"])) + int(str(call["completion_tokens"]))
                if call and call["status"] in {"ok", "invalid_output_fallback"}
                else None
            )
            self.ledger.reconcile(identifier, tokens)
            self.record(
                {
                    "reservation_id": identifier,
                    "model_role": "compact_selector",
                    "acquisition_purpose": "rollout",
                    "maximum_reserved_tokens": self.model.config.context_tokens,
                    "charged_tokens": tokens
                    if tokens is not None
                    else self.model.config.context_tokens,
                    "call": call,
                }
            )
            self.pacer.after()


def evaluation_inputs(study: FrozenStudy, args: argparse.Namespace, root: Path) -> dict[str, Any]:
    """Validate the full prerequisite chain before allocating models."""
    if args.fit is None:
        raise ValueError("held-out comparisons require the completed three-seed --fit phase")
    fit_path = private_output(root, root / args.fit)
    adapters = load_fit_phase(fit_path, study)
    identity: dict[str, Any] = {
        "fit": str(fit_path),
        "fit_result_sha256": file_digest(fit_path / "phase-result.json"),
    }
    selection = None
    if args.phase in {"calibration", "test"}:
        if args.tune is None:
            raise ValueError("calibration/test require the completed --tune phase")
        tune_path = private_output(root, root / args.tune)
        rows = load_comparison(tune_path / "comparison", study, "tune")
        selection = select_comparator(rows, study)
        saved = json.loads((tune_path / "decision.json").read_text())
        if content_hash(saved) != content_hash(selection):
            raise ValueError("tuning decision differs from its complete matched outcomes")
        manifest = json.loads((tune_path / "phase-manifest.json").read_text())
        if manifest.get("prerequisites") != identity:
            raise ValueError("tuning must use these exact three fitted adapters")
        identity.update(
            {
                "tune": str(tune_path),
                "tune_result_sha256": file_digest(tune_path / "phase-result.json"),
                "selection_sha256": file_digest(tune_path / "decision.json"),
            }
        )
    if args.phase == "test":
        if args.calibration is None:
            raise ValueError("test requires a completed fixed-policy --calibration phase")
        calibration_path = private_output(root, root / args.calibration)
        load_comparison(calibration_path / "comparison", study, "calibration")
        manifest = json.loads((calibration_path / "phase-manifest.json").read_text())
        if manifest.get("prerequisites") != identity:
            raise ValueError("calibration must use the same fit and tuning decision")
        if content_hash(
            json.loads((calibration_path / "decision.json").read_text())
        ) != content_hash(selection):
            raise ValueError("calibration cannot alter the selected policy")
        identity.update(
            {
                "calibration": str(calibration_path),
                "calibration_result_sha256": file_digest(calibration_path / "phase-result.json"),
            }
        )
    return {"adapters": adapters, "selection": selection, "prerequisites": identity}


async def compare(
    study: FrozenStudy,
    split: EvaluationSplit,
    output: Path,
    inputs: dict[str, Any],
    ledger: AcquisitionLedger,
    telemetry: GpuTelemetry,
    pacer: ThermalPacer,
) -> None:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(study.spec.task_model_path, local_files_only=True)

    def record(row: dict[str, Any]) -> None:
        write_exclusive(output / "calls" / f"call-{row['reservation_id']:08d}.private.json", row)

    @contextlib.contextmanager
    def session(arm: str) -> Iterator[PolicySession]:
        telemetry.check()
        if arm in {"unguarded", "per_action"}:
            yield PolicySession(PerActionAuthorizationPolicy())
        elif arm == "path_rule":
            yield PolicySession(PublicRulePolicy())
        else:
            pacer.before(int(study.spec.compact.device.split(":", 1)[1]))
            adapter = (
                None
                if arm == "compact_base"
                else inputs["adapters"][int(arm.removeprefix("compact_lora_seed_"))]
            )
            model = LocalCandidateModel(
                study.spec.compact, adapter=adapter, expected_protocol_id=study.protocol_id
            )
            policy = PacedStudySelector(
                model,
                use_adapter=adapter is not None,
                telemetry=telemetry,
                pacer=pacer,
                ledger=ledger,
                record=record,
            )
            active = PolicySession(policy, model.calls)
            try:
                yield active
            finally:
                active.policy = PublicRulePolicy()
                del policy, model
                import torch

                gc.collect()
                torch.cuda.empty_cache()

    with OwnedTaskServer(study, output, telemetry) as server:

        def before() -> None:
            server.check()
            pacer.before(study.spec.resources.task_agent_gpu)

        def factory(relay: StagedResponseRelay) -> MeteredStudyAgent:
            return MeteredStudyAgent(
                study.spec.agent,
                tokenizer=tokenizer,
                ledger=ledger,
                acquisition_purpose="rollout",
                before_call=before,
                after_call=pacer.after,
                record_call=record,
                relay=relay,
                text_receiver=relay.mode == "text",
            )

        report = await run_comparison(
            study, split, output / "comparison", factory, session, check=server.check
        )
    from routebench.defense.comparison import ComparisonRow

    rows = [ComparisonRow.model_validate(row) for row in report["rows"]]
    selection = select_comparator(rows, study) if split == "tune" else inputs["selection"]
    write_exclusive(output / "decision.json", selection)
    if split != "tune":
        analysis = comparison_analysis(rows, study, selection["selected_comparator"])
        analysis.update(
            {
                "split": split,
                "calibration_policy": study.spec.calibration_policy,
                "efficacy_evidence": split == "test",
                "formal_claim_requires_complete_measured_phase": True,
            }
        )
        write_exclusive(output / "analysis.json", analysis)


def run(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    if os.environ.get("CUDA_VISIBLE_DEVICES"):
        raise ValueError("unset CUDA_VISIBLE_DEVICES so frozen GPU IDs remain physical indices")
    if os.environ.get("CUDA_DEVICE_ORDER", "PCI_BUS_ID") != "PCI_BUS_ID":
        raise ValueError("formal GPU accounting requires CUDA_DEVICE_ORDER=PCI_BUS_ID")
    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    study = load_frozen_study(root, root / args.manifest)
    output = private_output(root, root / args.output)
    inputs: dict[str, Any] = {}
    collection: Path | None = None
    if args.phase == "fit":
        if args.collection is None:
            raise ValueError("fit requires the completed training --collection directory")
        collection = private_output(root, root / args.collection)
        load_training_phase(collection, study)
    elif args.phase == "collect":
        server_address(study.spec)
    else:
        server_address(study.spec)
        if not study.spec.compact.device.startswith("cuda:"):
            raise ValueError("formal comparison requires a reserved CUDA selector device")
        if int(study.spec.compact.device.split(":", 1)[1]) == study.spec.resources.task_agent_gpu:
            raise ValueError("concurrent task/selector inference requires distinct reserved GPUs")
        inputs = evaluation_inputs(study, args, root)
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
            "collection": str(collection) if collection else None,
            "collection_phase_sha256": file_digest(collection.parent / "phase-result.json")
            if collection
            else None,
            "prerequisites": inputs.get("prerequisites", {}),
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
            elif args.phase == "fit":
                assert args.collection is not None
                fit(study, root / args.collection, output, telemetry, pacer)
            else:
                asyncio.run(compare(study, args.phase, output, inputs, ledger, telemetry, pacer))
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
                "frozen_manifest_digest": study.manifest_digest,
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
                "comparison_files": {
                    str(path.relative_to(output / "comparison")): file_digest(path)
                    for path in sorted((output / "comparison").rglob("*"))
                    if path.is_file()
                }
                if args.phase in {"tune", "calibration", "test"}
                else {},
                "artifact_files": phase_files(output),
                "efficacy_evidence": False,
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--phase", choices=("collect", "fit", "tune", "calibration", "test"), required=True
    )
    parser.add_argument("--collection", type=Path)
    parser.add_argument("--fit", type=Path)
    parser.add_argument("--tune", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
