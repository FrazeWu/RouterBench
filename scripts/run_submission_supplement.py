"""Execute finite E4/E5/E6 schedules using the original fitted adapter and kernels."""

from __future__ import annotations

import argparse
import asyncio
import gc
import signal
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

from routebench.defense.branching import RecordedRollout
from routebench.defense.collect import collect_episode
from routebench.defense.compact import LocalCandidateModel
from routebench.defense.development import SimulatedApprover
from routebench.defense.ecpa import ECPAEnvironment
from routebench.defense.lora import file_digest
from routebench.defense.policies import PublicRulePolicy, PublicSearchPolicy
from routebench.defense.protocol import AcquisitionLedger
from routebench.defense.relay import StagedResponseRelay
from routebench.defense.study import MeteredStudyAgent, rollout_record
from routebench.submission.common import JournalTelemetry, ModelServer, durable_json
from routebench.submission.protocol import load_protocol
from routebench.submission.supplement import (
    SupplementPacer,
    TransformedPolicy,
    paraphrase,
    schedule,
    validate_parent,
)
from scripts.run_defense_study import PacedStudySelector


async def measure(args: argparse.Namespace, protocol: dict[str, Any], work: Path) -> None:
    from transformers import AutoTokenizer

    study, inputs = validate_parent(protocol)
    cases = schedule(study, args.phase, args.split, protocol["original_tune_comparator"])
    actual = [case.model_dump(mode="json") for case in cases]
    expected = protocol["supplement_schedules"][args.phase][args.split]
    if actual != expected:
        raise ValueError("supplement schedule differs from pre-result freeze")
    durable_json(work / "schedule.json", actual)
    tokenizer = AutoTokenizer.from_pretrained(study.spec.task_model_path, local_files_only=True)
    tasks = {task.entry.task_id: task for task in study.tasks}
    wording = yaml.safe_load(
        (Path(protocol["source_root"]) / "configs/submission/wording-paraphrases.yaml").read_text()
    )
    ledger = AcquisitionLedger(75000, 75000 * 8192)
    with JournalTelemetry(work / "telemetry.json", gpu_ids=(0, 1), maximum_celsius=85) as telemetry:
        pacer = SupplementPacer(
            telemetry,
            minimum_gap_seconds=2,
            pause_celsius=73,
            resume_celsius=71,
            maximum_wait_seconds=300,
        )

        def record(row: dict[str, Any]) -> None:
            durable_json(work / "calls" / f"call-{row['reservation_id']:08d}.private.json", row)

        with ModelServer(
            Path(study.spec.task_model_path),
            study.spec.agent.model,
            work,
            telemetry,
            context_tokens=study.spec.agent.context_tokens,
            gpu=1,
        ) as server:
            completed = 0
            for arm in dict.fromkeys(case.arm for case in cases):
                model: Any = None
                selector_calls: list[dict[str, Any]] = []
                if arm == "public_search":
                    policy: Any = PublicSearchPolicy()
                elif arm == "path_rule":
                    policy = PublicRulePolicy()
                elif arm == "compact_lora_seed_29":
                    pacer.before(0)
                    model = LocalCandidateModel(
                        study.spec.compact.model_copy(update={"device": "cuda:0"}),
                        adapter=inputs["adapters"][29],
                        expected_protocol_id=study.protocol_id,
                    )
                    policy = PacedStudySelector(
                        model,
                        use_adapter=True,
                        telemetry=telemetry,
                        pacer=pacer,
                        ledger=ledger,
                        record=record,
                    )
                    selector_calls = model.calls
                else:
                    raise ValueError("original comparator requires a registered fixed policy")
                try:
                    for case in (case for case in cases if case.arm == arm):
                        server.check()
                        task = tasks[case.task_id]
                        if args.condition == "wording_paraphrase":
                            task = paraphrase(task, wording)
                        transform = (
                            "no_receipts"
                            if args.phase == "E5"
                            else (
                                "menu_permutation"
                                if args.condition == "menu_permutation"
                                else "none"
                            )
                        )
                        selected = TransformedPolicy(policy, transform)
                        relay = StagedResponseRelay(
                            task.relay_campaign(), mode=case.mode, attacked=case.attacked
                        )

                        def before() -> None:
                            server.check()
                            pacer.before(1)

                        agent = MeteredStudyAgent(
                            study.spec.agent,
                            tokenizer=tokenizer,
                            ledger=ledger,
                            acquisition_purpose="rollout",
                            before_call=before,
                            after_call=pacer.after,
                            record_call=record,
                            relay=relay,
                            text_receiver=relay.mode == "text",
                            client=httpx.AsyncClient(timeout=120, trust_env=False),
                        )
                        environment = ECPAEnvironment(
                            task.public,
                            task.state(),
                            budgets=study.spec.budgets,
                            approval_provider=SimulatedApprover(),
                        )
                        first = len(selector_calls)
                        began = time.perf_counter()
                        try:
                            episode = await collect_episode(
                                environment,
                                agent,
                                selected,
                                seed=case.episode_seed,
                                evaluator=task.outcome,
                            )
                        finally:
                            await agent.aclose()
                            await agent.client.aclose()
                        payload = {
                            "case": case.model_dump(mode="json"),
                            "supplement_protocol_id": protocol["protocol_id"],
                            "parent_protocol_id": study.protocol_id,
                            "training_source_revision": study.revision,
                            "execution_source_revision": protocol["source_revision"],
                            "condition": args.condition,
                            "phase": args.phase,
                            "split": args.split,
                            "task_source_digest": task.digest,
                            "transformed_public_digest": task.public.digest,
                            **rollout_record(
                                RecordedRollout(episode, tuple(agent.calls), tuple(relay.events))
                            ),
                            "selector_calls": selector_calls[first:],
                            "transformation_events": selected.events,
                            "budget_used": environment.budget.used,
                            "elapsed_seconds": time.perf_counter() - began,
                        }
                        durable_json(work / "episodes" / f"{case.case_id}.private.json", payload)
                        completed += 1
                        durable_json(
                            args.output / "status.json",
                            {
                                "status": "running",
                                "phase": args.phase,
                                "split": args.split,
                                "condition": args.condition,
                                "completed": completed,
                                "total": len(cases),
                                "updated_unix": time.time(),
                            },
                            exclusive=False,
                        )
                finally:
                    policy = PublicRulePolicy()
                    if model is not None:
                        del model
                        import torch

                        gc.collect()
                        torch.cuda.empty_cache()
    durable_json(
        work / "summary.json",
        {
            "status": "complete",
            "episodes": len(cases),
            "acquisition_calls": ledger.calls,
            "acquisition_charged_tokens": ledger.tokens,
            "pacing_wait_seconds": pacer.wait_seconds,
        },
    )


def stopped(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt("stopped supplementary phase")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--phase", choices=["E4", "E5", "E6"], required=True)
    parser.add_argument("--split", choices=["tune", "calibration", "test"], default="test")
    parser.add_argument(
        "--condition", choices=["none", "menu_permutation", "wording_paraphrase"], default="none"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (args.phase == "E6") != (args.condition != "none"):
        raise ValueError("exactly the two fixed E6 conditions are authorized")
    signal.signal(signal.SIGTERM, stopped)
    protocol = load_protocol(args.manifest, model_key="qwen3-14b")
    args.output.mkdir(parents=True, exist_ok=False)
    work = args.output / "phase"
    work.mkdir()
    began = time.time()
    durable_json(
        work / "phase-manifest.json",
        {
            "phase": args.phase,
            "split": args.split,
            "condition": args.condition,
            "protocol_id": protocol["protocol_id"],
            "source_revision": protocol["source_revision"],
            "parent_protocol_id": protocol["configuration"]["parent_ecpa_protocol"],
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
                "phase": args.phase,
                "split": args.split,
                "condition": args.condition,
                "protocol_id": protocol["protocol_id"],
                "source_revision": protocol["source_revision"],
                "started_unix": began,
                "ended_unix": time.time(),
                "artifact_files": {
                    str(p.relative_to(work)): file_digest(p)
                    for p in sorted(work.rglob("*"))
                    if p.is_file()
                },
            },
        )
        durable_json(
            args.output / "status.json",
            {
                "status": status,
                "phase": args.phase,
                "split": args.split,
                "condition": args.condition,
                "completed": len(list((work / "episodes").glob("*.json"))),
            },
            exclusive=False,
        )


if __name__ == "__main__":
    main()
