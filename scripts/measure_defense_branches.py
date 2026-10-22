"""Real frozen-agent continuations from one identical development simulator state."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import subprocess
import time
from pathlib import Path

import yaml

from routebench.defense.agent import JsonRecoveryAgent, RecoveryAgentConfig
from routebench.defense.collect import PolicyChoice, collect_episode
from routebench.defense.development import SimulatedApprover, load_development_tasks
from routebench.defense.ecpa import AgentReply, AgentReplyKind, BudgetLimits, ECPAEnvironment
from routebench.defense.evaluation import HiddenOutcomeEvaluator, episode_metrics
from routebench.defense.evaluation_bridge import evaluation_context_manifest
from routebench.defense.policies import PublicRulePolicy
from routebench.defense.traces import build_transitions
from routebench.runtime.reference import ScenarioState


async def measure(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--short"], cwd=root, text=True)
    dirty = bool(status)
    if dirty and not args.allow_dirty_development:
        raise ValueError("commit the source before development measurement")
    output = root / args.output
    output.mkdir(parents=True, exist_ok=False)
    task = load_development_tasks(root, root / "configs/defense/development-contracts.yaml")[0]
    config = RecoveryAgentConfig.model_validate(
        yaml.safe_load((root / "configs/defense/development-agent.yaml").read_text())
    )
    environment = ECPAEnvironment(
        task.public,
        ScenarioState.from_fixture(task.bundle.root / "fixtures/state.json"),
        approval_provider=SimulatedApprover(),
        budgets=BudgetLimits(decisions=12, agent_calls=20),
    )
    # Explicit boundary probe, NOT claimed to have been induced by an attack.
    observation = await environment.observe(
        AgentReply(kind=AgentReplyKind.PROPOSE, edge_id="inspect_owner_contacts_early")
    )
    assert observation is not None
    manifest = {
        "purpose": "development_boundary_probe_only",
        "formal_evidence": False,
        "source_revision": revision,
        "dirty_development": dirty,
        "source_status": status.splitlines(),
        "formal_protocol_id": None,
        "seed": args.seed,
        "budgets": environment.budget.limits.model_dump(mode="json"),
        "packages": {name: importlib.metadata.version(name) for name in ("httpx", "pydantic")},
        "initial_proposal_origin": "explicit_development_probe_not_model_generated",
        "parent_state_token": observation.state_token,
        "branch_assignment": "enumerate_all_registered_interventions",
        "branch_assignment_probability": 1.0,
        "agent": config.model_dump(mode="json"),
        "evaluation_context": evaluation_context_manifest(task.evaluation_context),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for index, candidate in enumerate(observation.menu):
        branch, agent = environment.clone_for_collection(), JsonRecoveryAgent(config)
        started = time.perf_counter()
        try:
            episode = await collect_episode(
                branch,
                agent,
                PublicRulePolicy(),
                seed=args.seed + index,
                first_observation=observation,
                first_choice=PolicyChoice(candidate.candidate_id),
                evaluator=HiddenOutcomeEvaluator(task.bundle),
            )
        finally:
            await agent.aclose()
        summary = {
            "candidate_id": candidate.candidate_id,
            **episode_metrics(episode),
            "elapsed_seconds": time.perf_counter() - started,
            "model_calls": len(agent.calls),
            "acceptance_calls": sum(call.purpose == "acceptance" for call in agent.calls),
            "prompt_tokens": sum(call.prompt_tokens for call in agent.calls),
            "completion_tokens": sum(call.completion_tokens for call in agent.calls),
        }
        private = {
            **manifest,
            "branch_seed": args.seed + index,
            "split": "development",
            "task_id": task.public.contract.task_id,
            "semantic_family": task.public.contract.semantic_family,
            "attack_mechanism": "explicit_boundary_probe",
            "metrics": summary,
            "transitions": [row.model_dump(mode="json") for row in build_transitions(episode)],
            "calls": [call.model_dump(mode="json") for call in agent.calls],
        }
        (output / f"branch-{index}.private.json").write_text(json.dumps(private, indent=2) + "\n")
        print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/private/ecpa-feasibility/branches")
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument("--allow-dirty-development", action="store_true")
    asyncio.run(measure(parser.parse_args()))
