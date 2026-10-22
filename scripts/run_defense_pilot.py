"""Bounded, clean-revision ECPA development chain: collect, fit, compare, report.

Run with the optional learning dependencies installed and a frozen task-agent
OpenAI-compatible endpoint. All traces/adapters are private ignored artifacts;
this runner categorically refuses formal data and emits no efficacy claim.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import gc
import importlib.metadata
import json
import random
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml
from pydantic import Field

from routebench.defense.agent import JsonRecoveryAgent, RecoveryAgentConfig
from routebench.defense.collect import (
    CollectedEpisode,
    DefensePolicy,
    OutcomeLabel,
    PolicyChoice,
    collect_episode,
)
from routebench.defense.compact import CompactConfig, CompactPolicy, LocalCandidateModel, write_json
from routebench.defense.development import (
    DevelopmentTask,
    SimulatedApprover,
    load_development_tasks,
)
from routebench.defense.ecpa import (
    AgentReply,
    AgentView,
    BudgetLimits,
    DefenseObservation,
    ECPAEnvironment,
)
from routebench.defense.evaluation import HiddenOutcomeEvaluator, episode_metrics
from routebench.defense.lora import (
    BranchGroup,
    BranchOutcome,
    LoraSpec,
    file_digest,
    model_fingerprint,
    train_lora,
)
from routebench.defense.pilot import (
    GpuTelemetry,
    ThermalPacer,
    UnguardedSimulatorReference,
    clean_revision,
)
from routebench.defense.policies import (
    MixtureLoggingPolicy,
    PerActionAuthorizationPolicy,
    PublicRulePolicy,
)
from routebench.defense.relay import RelayCampaign, StagedResponseRelay
from routebench.defense.traces import build_transitions
from routebench.runtime.reference import ScenarioState
from routebench.scenarios.schema import StrictModel

ARMS = ("unguarded", "per_action", "path_rule", "compact_base", "compact_lora")


class PilotConfig(StrictModel):
    purpose: Literal["development_feasibility_only"]
    agent_config: str
    task_contracts: str
    task_model_path: str
    compact: CompactConfig
    lora: LoraSpec
    budgets: BudgetLimits
    seed: int
    branch_repeats: int = Field(gt=0)
    maximum_branch_states_per_episode: int = Field(gt=0)
    gpu_ids: tuple[int, ...]
    maximum_celsius: int
    minimum_request_gap_seconds: float = Field(ge=0)
    cooling_pause_celsius: int
    cooling_resume_celsius: int
    modes: tuple[Literal["text", "structured"], ...]
    campaigns: tuple[RelayCampaign, ...]
    branch_nodes: dict[str, tuple[str, ...]]


class MeasuredAgent(JsonRecoveryAgent):
    def __init__(
        self,
        *args: object,
        telemetry: GpuTelemetry,
        pacer: ThermalPacer,
        gpu_id: int,
        **kwargs: object,
    ):
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.telemetry = telemetry
        self.pacer, self.gpu_id = pacer, gpu_id

    async def _complete(self, view: AgentView, **kwargs: Any) -> str:
        self.pacer.before(self.gpu_id)
        try:
            return await super()._complete(view, **kwargs)
        finally:
            self.pacer.after()

    async def respond_budgeted(
        self, view: AgentView, *, seed: int, charge: Callable[[], None]
    ) -> AgentReply:
        def checked_charge() -> None:
            self.telemetry.check()
            charge()

        return await super().respond_budgeted(view, seed=seed, charge=checked_charge)


class PacedCompactPolicy(CompactPolicy):
    def __init__(self, model: LocalCandidateModel, *, use_adapter: bool, pacer: ThermalPacer):
        super().__init__(model, use_adapter=use_adapter)
        self.pacer = pacer

    def choose(self, observation: DefenseObservation, *, rng: random.Random) -> PolicyChoice:
        self.pacer.before(int(self.model.config.device.split(":")[-1]))
        try:
            return super().choose(observation, rng=rng)
        finally:
            self.pacer.after()


class Pilot:
    def __init__(self, root: Path, config_path: Path, output: Path):
        self.root, self.output = root, output
        self.pacer: ThermalPacer
        self.revision = clean_revision(root)
        self.config = PilotConfig.model_validate(yaml.safe_load(config_path.read_text()))
        self.agent_config = RecoveryAgentConfig.model_validate(
            yaml.safe_load((root / self.config.agent_config).read_text())
        )
        if self.agent_config.context_tokens != self.config.compact.context_tokens:
            raise ValueError(
                "pilot task-agent and defender context settings must be explicit/matched"
            )
        self.tasks = load_development_tasks(root, root / self.config.task_contracts)
        ids = {task.public.contract.task_id for task in self.tasks}
        if (
            len(self.config.campaigns) != len(ids)
            or {item.task_id for item in self.config.campaigns} != ids
        ):
            raise ValueError("exactly one public relay campaign per development task is required")
        if len(set(self.config.modes)) != len(self.config.modes):
            raise ValueError("duplicate attack mode")
        for task in self.tasks:
            campaign = self.campaign(task)
            edges = {edge.edge_id: edge for edge in task.public.graph.edges}
            for stage in campaign.stages:
                if stage.edge_id not in edges or edges[stage.edge_id].source != stage.node:
                    raise ValueError("campaign references an unavailable public edge")
            if not set(self.config.branch_nodes[task.public.contract.task_id]) <= {
                node.node_id for node in task.public.graph.nodes
            }:
                raise ValueError("branch sampling node is not registered")
        output.mkdir(parents=True, exist_ok=True)
        identity = {
            "purpose": "development_feasibility_only",
            "formal_evidence": False,
            "formal_protocol_id": None,
            "source_revision": self.revision,
            "config": self.config.model_dump(mode="json"),
            "agent": self.agent_config.model_dump(mode="json"),
            "task_snapshot_fingerprint": model_fingerprint(self.config.task_model_path),
            "compact_snapshot_fingerprint": model_fingerprint(self.config.compact.model_path),
            "public_task_digests": [task.public.digest for task in self.tasks],
            "config_sha256": file_digest(config_path),
            "planned_comparison_episodes": len(self.tasks) * len(self.config.modes) * 2 * len(ARMS),
            "interpretation": "development integration smoke; no efficacy inference",
        }
        manifest_path = output / "manifest.json"
        if manifest_path.exists():
            if json.loads(manifest_path.read_text()) != identity:
                raise ValueError("existing pilot manifest has a different source/config identity")
        else:
            write_json(manifest_path, identity)

    def campaign(self, task: DevelopmentTask) -> RelayCampaign:
        return next(
            item for item in self.config.campaigns if item.task_id == task.public.contract.task_id
        )

    def agent(self, relay: StagedResponseRelay, telemetry: GpuTelemetry) -> MeasuredAgent:
        return MeasuredAgent(
            self.agent_config,
            relay=relay,
            text_receiver=relay.mode == "text",
            telemetry=telemetry,
            pacer=self.pacer,
            gpu_id=self.config.gpu_ids[0],
        )

    async def episode(
        self,
        task: DevelopmentTask,
        mode: Literal["text", "structured"],
        attacked: bool,
        arm: str,
        policy: DefensePolicy,
        telemetry: GpuTelemetry,
        directory: Path,
        *,
        branch: bool = False,
        compact_model: LocalCandidateModel | None = None,
    ) -> dict[str, object]:
        telemetry.check()
        relay = StagedResponseRelay(self.campaign(task), mode=mode, attacked=attacked)
        agent = self.agent(relay, telemetry)
        environment_class = UnguardedSimulatorReference if arm == "unguarded" else ECPAEnvironment
        environment = environment_class(
            task.public,
            ScenarioState.from_fixture(task.bundle.root / "fixtures/state.json"),
            budgets=self.config.budgets,
            approval_provider=SimulatedApprover(),
        )
        evaluator = HiddenOutcomeEvaluator(task.bundle)
        identity = (
            f"{task.public.contract.task_id}-{mode}-{'attacked' if attacked else 'benign'}-{arm}"
        )
        condition = f"{mode}_{'attacked' if attacked else 'benign'}"
        prefix_violation = prefix_attack = False
        groups_taken = 0

        def evaluate(state: ScenarioState) -> OutcomeLabel:
            nonlocal prefix_violation, prefix_attack
            outcome = evaluator(state)
            prefix_violation |= outcome.violation
            prefix_attack |= outcome.attack_success
            return outcome

        async def observed(env: ECPAEnvironment, observation: DefenseObservation) -> None:
            nonlocal groups_taken
            telemetry.check()
            if (
                not branch
                or groups_taken >= self.config.maximum_branch_states_per_episode
                or observation.node not in self.config.branch_nodes[task.public.contract.task_id]
                or len(observation.menu) < 2
            ):
                return
            groups_taken += 1
            group_id = f"{identity}-{groups_taken}"
            parent_violation, parent_attack = prefix_violation, prefix_attack

            def branch_evaluator(state: ScenarioState) -> OutcomeLabel:
                result = evaluator(state)
                return result.model_copy(
                    update={
                        "violation": result.violation or parent_violation,
                        "attack_success": result.attack_success or parent_attack,
                    }
                )

            outcomes = []
            for repeat in range(self.config.branch_repeats):
                common_seed = self.config.seed + 1000 + repeat
                for index, candidate in enumerate(observation.menu):
                    telemetry.check()
                    branch_agent = self.agent(copy.deepcopy(relay), telemetry)
                    branch_env = env.clone_for_collection()
                    began = time.perf_counter()
                    try:
                        episode = await collect_episode(
                            branch_env,
                            branch_agent,
                            PublicRulePolicy(),
                            seed=common_seed,
                            first_observation=observation,
                            first_choice=PolicyChoice(candidate.candidate_id),
                            evaluator=branch_evaluator,
                        )
                    finally:
                        await branch_agent.aclose()
                    transitions = build_transitions(episode)
                    metrics = episode_metrics(episode)
                    outcomes.append(
                        BranchOutcome(
                            candidate_id=candidate.candidate_id,
                            repeat=repeat,
                            continuation_seed=common_seed,
                            terminated=episode.terminated,
                            truncated=episode.truncated,
                            safe_completion=bool(metrics["safe_recovery"])
                            if episode.terminated
                            else None,
                            violation=bool(metrics["violation"]) if episode.terminated else None,
                            cost=transitions[0].remaining_cost if transitions else None,
                            termination_reason=episode.termination_reason,
                        )
                    )
                    self.save_episode(
                        directory / f"{group_id}-r{repeat}-b{index}.private.json",
                        episode,
                        branch_agent,
                        branch_env,
                        time.perf_counter() - began,
                        task,
                        condition,
                        "branch",
                        compact_calls=[],
                    )
            group = BranchGroup(
                group_id=group_id,
                observation=observation,
                semantic_family=task.public.contract.semantic_family,
                attack_mechanism=condition,
                split="development",
                source_revision=self.revision,
                proposal_sampling_probability=1.0,
                outcomes=tuple(outcomes),
            )
            write_json(directory / f"{group_id}.group.private.json", group.model_dump(mode="json"))

        began = time.perf_counter()
        compact_before = len(compact_model.calls) if compact_model else 0
        try:
            episode = await collect_episode(
                environment,
                agent,
                policy,
                seed=self.config.seed,
                evaluator=evaluate,
                observation_callback=observed,
            )
        finally:
            await agent.aclose()
        summary = self.save_episode(
            directory / f"{identity}.private.json",
            episode,
            agent,
            environment,
            time.perf_counter() - began,
            task,
            condition,
            arm,
            compact_calls=compact_model.calls[compact_before:] if compact_model else [],
        )
        # Parent wall time includes branch collection; branch time is separately
        # recorded. Phase wall times avoid summing overlapping parent/child time.
        print(json.dumps(summary), flush=True)
        return summary

    def save_episode(
        self,
        path: Path,
        episode: CollectedEpisode,
        agent: MeasuredAgent,
        environment: ECPAEnvironment,
        elapsed: float,
        task: DevelopmentTask,
        condition: str,
        arm: str,
        *,
        compact_calls: list[dict[str, Any]],
    ) -> dict[str, object]:
        relay = agent.relay
        assert isinstance(relay, StagedResponseRelay)
        executed = {step.selected.edge_id for step in episode.steps if step.dispatched}
        events = [
            dict(event, target_executed=event["target_edge_id"] in executed)
            for event in relay.events
        ]
        summary = {
            "identity": path.stem,
            "semantic_family": task.public.contract.semantic_family,
            "condition": condition,
            "arm": arm,
            **episode_metrics(episode),
            "elapsed_seconds": elapsed,
            "model_calls": len(agent.calls),
            "prompt_tokens": sum(call.prompt_tokens for call in agent.calls),
            "completion_tokens": sum(call.completion_tokens for call in agent.calls),
            "defender_calls": len(compact_calls),
            "defender_fallbacks": sum(call["status"] != "ok" for call in compact_calls),
            "defender_prompt_tokens": sum(int(call["prompt_tokens"]) for call in compact_calls),
            "defender_completion_tokens": sum(
                int(call["completion_tokens"]) for call in compact_calls
            ),
            "defender_seconds": sum(float(call["elapsed_seconds"]) for call in compact_calls),
            "relay_stages_reached": len(events),
            "relay_substitutions": sum(bool(event["changed"]) for event in events),
            "relay_targets_executed": sum(bool(event["target_executed"]) for event in events),
            "resources_used": dict(environment.budget.used),
        }
        write_json(
            path,
            {
                "source_revision": self.revision,
                "split": "development",
                "formal_protocol_id": None,
                "metrics": summary,
                "relay_events": events,
                "calls": [call.model_dump(mode="json") for call in agent.calls],
                "compact_calls": compact_calls,
                "transitions": [row.model_dump(mode="json") for row in build_transitions(episode)],
                "final_state": episode.final_state,
            },
        )
        return summary

    async def collect(self, telemetry: GpuTelemetry) -> None:
        self.check_server()
        directory = self.output / "collection"
        directory.mkdir(exist_ok=False)
        for task in self.tasks:
            for mode in self.config.modes:
                for attacked in (False, True):
                    await self.episode(
                        task,
                        mode,
                        attacked,
                        "logging",
                        MixtureLoggingPolicy(),
                        telemetry,
                        directory,
                        branch=True,
                    )

    def fit(self, telemetry: GpuTelemetry) -> None:
        telemetry.check()
        groups = [
            BranchGroup.model_validate_json(path.read_text())
            for path in sorted((self.output / "collection").glob("*.group.private.json"))
        ]
        measurement = train_lora(
            groups,
            self.config.compact,
            self.config.lora,
            self.output / "adapter",
            source_revision=self.revision,
            development_smoke=True,
            check=lambda: self.pacer.before(int(self.config.compact.device.split(":")[-1])),
            after_update=self.pacer.after,
        )
        print(json.dumps(measurement), flush=True)
        gc.collect()
        import torch  # type: ignore[import-not-found]

        torch.cuda.empty_cache()

    async def compare(self, telemetry: GpuTelemetry) -> None:
        self.check_server()
        directory = self.output / "comparison"
        directory.mkdir(exist_ok=False)
        compact = LocalCandidateModel(
            self.config.compact, adapter=self.output / "adapter", allow_development=True
        )
        policies: dict[str, DefensePolicy] = {
            "unguarded": PerActionAuthorizationPolicy(),
            "per_action": PerActionAuthorizationPolicy(),
            "path_rule": PublicRulePolicy(),
            "compact_base": PacedCompactPolicy(compact, use_adapter=False, pacer=self.pacer),
            "compact_lora": PacedCompactPolicy(compact, use_adapter=True, pacer=self.pacer),
        }
        jobs = [
            (task, mode, attacked, arm)
            for task in self.tasks
            for mode in self.config.modes
            for attacked in (False, True)
            for arm in ARMS
        ]
        random.Random(self.config.seed).shuffle(jobs)
        for task, mode, attacked, arm in jobs:
            await self.episode(
                task,
                mode,
                attacked,
                arm,
                policies[arm],
                telemetry,
                directory,
                compact_model=compact if arm.startswith("compact_") else None,
            )

    def check_server(self) -> None:
        response = httpx.get(self.agent_config.endpoint.rstrip("/") + "/models", timeout=10)
        response.raise_for_status()
        models = response.json()["data"]
        if not any(
            item["id"] == self.agent_config.model
            and item.get("root") == self.config.task_model_path
            for item in models
        ):
            raise ValueError("task-agent server does not advertise the frozen local snapshot")


def report(output: Path) -> dict[str, object]:
    manifest = json.loads((output / "manifest.json").read_text())
    episodes = []
    for directory in ("collection", "comparison"):
        for path in sorted((output / directory).glob("*.private.json")):
            if ".group." not in path.name:
                episodes.append(json.loads(path.read_text())["metrics"])
    aggregate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in episodes:
        if row["arm"] != "logging" and row["arm"] != "branch":
            aggregate[f"{row['arm']}/{row['condition']}"].append(row)
    table = []
    for key, rows in sorted(aggregate.items()):
        table.append(
            {
                "arm_condition": key,
                "episodes": len(rows),
                "safe_recovery": sum(bool(row["safe_recovery"]) for row in rows) / len(rows),
                "completed": sum(bool(row["completed"]) for row in rows) / len(rows),
                "violations": sum(bool(row["violation"]) for row in rows),
                "attack_successes": sum(bool(row["attack_success"]) for row in rows),
                "defender_fallbacks": sum(int(row["defender_fallbacks"]) for row in rows),
            }
        )
    totals = {
        key: sum(int(row[key]) for row in episodes)
        for key in (
            "model_calls",
            "prompt_tokens",
            "completion_tokens",
            "defender_calls",
            "defender_prompt_tokens",
            "defender_completion_tokens",
        )
    }
    comparison_count = sum(len(rows) for rows in aggregate.values())
    result = {
        "source_revision": manifest["source_revision"],
        "formal_evidence": False,
        "efficacy_claim": False,
        "comparison_episodes": comparison_count,
        "planned_comparison_episodes": manifest["planned_comparison_episodes"],
        "comparison_complete": comparison_count == manifest["planned_comparison_episodes"],
        "recorded_episodes_including_branches": len(episodes),
        "totals": totals,
        "termination_reasons": dict(Counter(str(row["termination_reason"]) for row in episodes)),
        "descriptive_integration_table": table,
        "interpretation": "two development overlays; no independent efficacy estimate",
    }
    phase_costs = {
        phase: json.loads(path.read_text())
        for phase in ("collect", "fit", "compare")
        if (path := output / f"{phase}-cost.json").exists()
    }
    result["phase_costs"] = phase_costs
    result["phase_reserved_device_hours_excluding_startup_idle"] = sum(
        item["reserved_device_hours"] for item in phase_costs.values()
    )
    result["branch_groups"] = len(list((output / "collection").glob("*.group.private.json")))
    if (output / "adapter/measurement.json").exists():
        result["adapter_fit"] = json.loads((output / "adapter/measurement.json").read_text())
    thermal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in output.glob("*-telemetry.json"):
        for row in json.loads(path.read_text())["samples"]:
            thermal[str(row["gpu"])].append(row)
    result["gpu_summary"] = {
        gpu: {
            "max_celsius": max(row["celsius"] for row in rows),
            "max_device_memory_mib": max(row["memory_mib"] for row in rows),
            "thermal_throttling_observed": any(
                row["hardware_thermal"] == "Active" or row["software_thermal"] == "Active"
                for row in rows
            ),
        }
        for gpu, rows in thermal.items()
    }
    write_json(output / "report.json", result)
    return result


async def run(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output).resolve()
    if not output.is_relative_to((root / "artifacts/private").resolve()):
        raise ValueError("pilot traces/adapters must remain under ignored artifacts/private")
    pilot = Pilot(root, Path(args.config), output)
    phases = ("collect", "fit", "compare") if args.phase == "all" else (args.phase,)
    for phase in phases:
        if phase == "report":
            print(json.dumps(report(output)), flush=True)
            continue
        began = time.perf_counter()
        status = "aborted"
        with GpuTelemetry(
            output / f"{phase}-telemetry.json",
            gpu_ids=pilot.config.gpu_ids,
            maximum_celsius=pilot.config.maximum_celsius,
        ) as telemetry:
            pilot.pacer = ThermalPacer(
                telemetry,
                minimum_gap_seconds=pilot.config.minimum_request_gap_seconds,
                pause_celsius=pilot.config.cooling_pause_celsius,
                resume_celsius=pilot.config.cooling_resume_celsius,
            )
            try:
                if phase == "collect":
                    await pilot.collect(telemetry)
                elif phase == "fit":
                    pilot.fit(telemetry)
                else:
                    await pilot.compare(telemetry)
                telemetry.check()
                status = "complete"
            finally:
                elapsed = time.perf_counter() - began
                # The first configured GPU hosts the externally launched task server;
                # both are reserved during fit/compare. Do not double count branches.
                occupied = (
                    [pilot.config.gpu_ids[0]] if phase == "collect" else list(pilot.config.gpu_ids)
                )
                write_json(
                    output / f"{phase}-cost.json",
                    {
                        "source_revision": pilot.revision,
                        "status": status,
                        "phase": phase,
                        "wall_seconds": elapsed,
                        "reserved_gpu_ids": occupied,
                        "reserved_device_hours": elapsed * len(occupied) / 3600,
                        "scheduled_wait_seconds": pilot.pacer.wait_seconds,
                        "scheduled_wait_count": pilot.pacer.waits,
                        "note": "phase estimate; add server startup and idle gaps separately",
                        "packages": {
                            name: importlib.metadata.version(name)
                            for name in ("torch", "transformers", "peft", "httpx")
                        },
                    },
                )
    report(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/defense/compact-pilot.yaml")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--phase", choices=("all", "collect", "fit", "compare", "report"), default="all"
    )
    asyncio.run(run(parser.parse_args()))
