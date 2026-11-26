"""Run fixed E1, independent optimality, and next-hop ablation matrices."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import httpx

from routebench.authorization.controllers import NoAuthorizationController
from routebench.contracts import FeedbackMode
from routebench.defense.lora import file_digest
from routebench.defense.pilot import ThermalPacer
from routebench.evaluation.graph_evaluation import (
    FormalGraphAttempt,
    build_formal_graph_summary,
    formal_graph_case_labels,
    write_private_formal_graph_attempt_manifest,
)
from routebench.evaluation.graph_selection import run_graph_selection
from routebench.planners.config import PlannerConfig
from routebench.planners.local_json import PlannerResponseError, _anonymize_candidate_graph
from routebench.runtime.graph import evaluate_candidate_paths, public_route_optimality
from routebench.runtime.reference import (
    InvalidRouteActionError,
    UnsatisfiedPriorActionRequirementError,
)
from routebench.scenarios.loader import load_scenario
from routebench.submission.common import (
    JournalTelemetry,
    MeasuredGateway,
    ModelServer,
    durable_json,
)
from routebench.submission.graph import (
    RepairGraphPlanner,
    candidate_menu,
)
from routebench.submission.optimality import audit_scenario
from routebench.submission.protocol import load_protocol


def interrupted(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt("operator stopped the submission job")


def retention(bundle: Any, seed: int, variant: str) -> dict[str, Any]:
    graph = bundle.definition.graph
    public, mapping = _anonymize_candidate_graph(graph, seed)
    labels = {original: shown for shown, original in mapping.items()}
    public_edges = {edge.edge_id: edge for edge in public.edges}
    eligible = [
        p.edge_ids
        for p in evaluate_candidate_paths(bundle)
        if p.functional_success and p.policy_compliance and not p.attack_target_ids
    ]
    optimum = public_route_optimality(bundle).exact_optimal_edge_ids

    def kept(route: tuple[str, ...]) -> bool:
        node = public.start_node
        history: tuple[str, ...] = ()
        for original in route:
            menu, _ = candidate_menu(public, node, history, variant, seed)
            shown = labels[original]
            if shown not in menu:
                return False
            history = (*history, shown)
            node = public_edges[shown].target
        return True

    safe_kept = sum(kept(route) for route in eligible)
    optimal_kept = sum(kept(route) for route in optimum)
    return {
        "safe_paths": len(eligible),
        "safe_paths_retained": safe_kept,
        "optimal_paths": len(optimum),
        "optimal_paths_retained": optimal_kept,
        "any_safe_retained": safe_kept > 0,
        "any_optimal_retained": optimal_kept > 0,
    }


async def model_job(
    args: argparse.Namespace, protocol: dict[str, Any], work: Path
) -> dict[str, Any]:
    root = Path(protocol["source_root"])
    config = protocol["configuration"]
    model = protocol["models"][args.model]
    selected = protocol["graph_cases"] if args.phase == "E1" else protocol["next_hop_cases"]
    variants = ["A"] if args.phase == "E1" else ["B", "C", "D", "E"]
    seeds = config["seeds"]
    total = len(selected) * len(seeds) * len(variants)
    planner_config = PlannerConfig.model_validate(
        {
            "schema_version": 2,
            "backend": "vllm",
            "model": model["served_name"],
            "endpoint": "http://127.0.0.1:8011/v1",
            "generation": {
                k: v for k, v in config["graph_generation"].items() if k != "disable_thinking"
            },
            "formal_run": True,
            "disable_thinking": True,
            "anonymize_graph_labels": True,
            "graph_presentation_seeded_permutation": True,
            "graph_selection_interface": "incremental_edge",
            "protocol_version": "v13",
        }
    )
    attempts: dict[str, list[FormalGraphAttempt]] = defaultdict(list)
    retention_rows = []
    state = {
        "status": "starting",
        "phase": args.phase,
        "model": args.model,
        "completed": 0,
        "total": total,
        "protocol_id": protocol["protocol_id"],
        "source_revision": protocol["source_revision"],
    }
    resources = config["resources"]
    status_path = args.output / "status.json"
    with JournalTelemetry(
        work / "telemetry.json", gpu_ids=(0, 1), maximum_celsius=resources["maximum_celsius"]
    ) as telemetry:
        pacer = ThermalPacer(
            telemetry,
            minimum_gap_seconds=resources["graph_gap_seconds"],
            pause_celsius=resources["graph_cooling_pause_celsius"],
            resume_celsius=resources["graph_cooling_resume_celsius"],
            maximum_wait_seconds=resources["maximum_cooling_wait_seconds"],
        )
        gateway = MeasuredGateway(planner_config, work, pacer, call_limit=total * 17)
        try:
            with ModelServer(
                Path(model["path"]),
                model["served_name"],
                work,
                telemetry,
                context_tokens=32768,
                gpu=1,
            ) as server:
                for variant in variants:
                    for relative in selected:
                        bundle = load_scenario(root / relative)
                        family, length = formal_graph_case_labels(bundle)
                        for seed in seeds:
                            server.check()
                            selected_planner = RepairGraphPlanner(
                                gateway, bundle.definition.policy, variant
                            )
                            before = len(gateway.calls)
                            began = time.perf_counter()
                            try:
                                result = await run_graph_selection(
                                    bundle,
                                    selected_planner,
                                    NoAuthorizationController(),
                                    FeedbackMode.MINIMAL,
                                    seed,
                                )
                                attempt = FormalGraphAttempt(
                                    bundle.definition.metadata.scenario_id,
                                    bundle.digest,
                                    seed,
                                    family,
                                    length,
                                    time.perf_counter() - began,
                                    "valid",
                                    result,
                                )
                            except (
                                PlannerResponseError,
                                InvalidRouteActionError,
                                UnsatisfiedPriorActionRequirementError,
                            ) as error:
                                attempt = FormalGraphAttempt(
                                    bundle.definition.metadata.scenario_id,
                                    bundle.digest,
                                    seed,
                                    family,
                                    length,
                                    time.perf_counter() - began,
                                    "invalid_output",
                                    failure_kind=type(error).__name__,
                                )
                            except httpx.HTTPError as error:
                                attempt = FormalGraphAttempt(
                                    bundle.definition.metadata.scenario_id,
                                    bundle.digest,
                                    seed,
                                    family,
                                    length,
                                    time.perf_counter() - began,
                                    "backend_failure",
                                    failure_kind=type(error).__name__,
                                )
                            metadata = {
                                "protocol_id": protocol["protocol_id"],
                                "source_revision": protocol["source_revision"],
                                "interface": "explicit_stop_continue_v1",
                                "variant": variant,
                                "model_fingerprint": model["fingerprint"],
                                "calls": gateway.calls[before:],
                                "candidate_steps": selected_planner.steps,
                            }
                            manifest = write_private_formal_graph_attempt_manifest(
                                attempt, work / variant, metadata
                            )
                            # Flush the native record before publishing its completion marker.
                            record = json.loads(manifest.read_text())
                            durable_json(manifest, record, exclusive=False)
                            durable_json(manifest.with_name("complete.json"), record)
                            attempts[variant].append(attempt)
                            if args.phase != "E1":
                                retention_rows.append(
                                    {
                                        "scenario_id": attempt.scenario_id,
                                        "seed": seed,
                                        "variant": variant,
                                        **retention(bundle, seed, variant),
                                    }
                                )
                            state.update(
                                status="running",
                                completed=state["completed"] + 1,
                                updated_unix=time.time(),
                                last_case=attempt.scenario_id,
                            )
                            durable_json(status_path, state, exclusive=False)
                            server.check()
        finally:
            await gateway.aclose()
    summaries = {}
    identifiers = tuple(Path(relative).name for relative in selected)
    for variant in variants:
        summaries[variant] = build_formal_graph_summary(
            attempts=tuple(attempts[variant]),
            scenario_ids=identifiers,
            seeds=tuple(seeds),
            metadata={
                "protocol_id": protocol["protocol_id"],
                "interface": "explicit_stop_continue_v1",
                "variant": variant,
                "model": args.model,
            },
            benchmark_case_target=776,
        )
    report = {
        "status": "complete",
        "phase": args.phase,
        "model": args.model,
        "attempts": total,
        "summaries": summaries,
        "retention": retention_rows,
        "acquisition_calls": gateway.ledger.calls,
        "acquisition_charged_tokens": gateway.ledger.tokens,
        "pacing_wait_seconds": pacer.wait_seconds,
        "backend_failures": sum(
            a.status == "backend_failure" for values in attempts.values() for a in values
        ),
    }
    durable_json(work / "summary.json", report)
    return report


def run(args: argparse.Namespace) -> None:
    protocol = load_protocol(args.manifest, model_key=args.model)
    args.output.mkdir(parents=True, exist_ok=False)
    work = args.output / "phase"
    work.mkdir()
    began = time.time()
    durable_json(
        work / "phase-manifest.json",
        {
            "protocol_id": protocol["protocol_id"],
            "source_revision": protocol["source_revision"],
            "phase": args.phase,
            "model": args.model,
            "started_unix": began,
        },
    )
    status, error = "aborted", None
    try:
        if args.phase == "E9":
            paths = [Path(protocol["source_root"]) / p for p in protocol["graph_cases"]]
            rows = []
            with ProcessPoolExecutor(max_workers=4, mp_context=get_context("spawn")) as pool:
                for row in pool.map(audit_scenario, paths):
                    durable_json(work / "cases" / f"{row['scenario_id']}.json", row)
                    rows.append(row)
                    durable_json(
                        args.output / "status.json",
                        {
                            "status": "running",
                            "completed": len(rows),
                            "total": len(paths),
                            "phase": "E9",
                        },
                        exclusive=False,
                    )
            durable_json(
                work / "summary.json",
                {
                    "status": "complete",
                    "cases": len(rows),
                    "equal_optima_cases": sum(r["equal_optima"] > 1 for r in rows),
                    "all_paths_selectable": all(r["all_paths_selectable"] for r in rows),
                    "native_solver_agreement": all(
                        r["topology_agrees"] and r["optimum_agrees"] for r in rows
                    ),
                },
            )
        else:
            if args.model is None:
                raise ValueError("a frozen model is required")
            asyncio.run(model_job(args, protocol, work))
        status = "complete"
    except BaseException as exception:
        error = type(exception).__name__
        raise
    finally:
        result = {
            "status": status,
            "error_kind": error,
            "phase": args.phase,
            "model": args.model,
            "protocol_id": protocol["protocol_id"],
            "source_revision": protocol["source_revision"],
            "started_unix": began,
            "ended_unix": time.time(),
            "artifact_files": {
                str(p.relative_to(work)): file_digest(p)
                for p in sorted(work.rglob("*"))
                if p.is_file() and p.name != "phase-result.json"
            },
        }
        durable_json(work / "phase-result.json", result)
        durable_json(
            args.output / "status.json",
            {
                "status": status,
                "phase": args.phase,
                "model": args.model,
                "completed": len(list(work.rglob("complete.json")))
                if args.phase != "E9"
                else len(list((work / "cases").glob("*.json"))),
                "result_sha256": file_digest(work / "phase-result.json"),
            },
            exclusive=False,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--phase", choices=["E9", "E1", "next-hop"], required=True)
    parser.add_argument("--model")
    parser.add_argument("--output", type=Path, required=True)
    signal.signal(signal.SIGTERM, interrupted)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
