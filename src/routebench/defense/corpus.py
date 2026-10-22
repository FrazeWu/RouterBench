"""Independent-corpus preparation; private assertions never enter public tasks.

Audits below are deterministic simulator authoring checks, not model rollouts,
training labels, an independent semantic review, or defense-effectiveness data.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from routebench.defense.collect import OutcomeLabel
from routebench.defense.contracts import PublicRecoveryTask, content_hash
from routebench.defense.development import SimulatedApprover
from routebench.defense.ecpa import (
    AgentReply,
    AgentReplyKind,
    AgentView,
    DefenseDecisionKind,
    ECPAEnvironment,
)
from routebench.defense.overlap import overlap_screen
from routebench.defense.pilot import UnguardedSimulatorReference
from routebench.defense.policies import PublicRulePolicy
from routebench.defense.protocol import SplitItem, validate_splits
from routebench.evaluation import evaluate_all
from routebench.runtime.reference import ScenarioState, validate_route_spec
from routebench.scenarios.schema import RouteSpec, StrictModel, VerifierSpec

Split = Literal["train", "tune", "calibration", "test"]


class CorpusEntry(StrictModel):
    directory: str
    task_id: str
    semantic_family: str
    split: Split
    attack_mechanism: str
    independent_review: Literal["pending", "accepted"] = "pending"
    review_evidence: str | None = None


class CorpusSpec(StrictModel):
    purpose: Literal["ecpa_independent_corpus_preparation"]
    status: Literal["authoring"]
    planned_families: dict[Split, int]
    excluded_families: tuple[str, ...]
    entries: tuple[CorpusEntry, ...]


class MenuProbe(StrictModel):
    prefix: tuple[str, ...]
    proposal: str
    expected_kind: DefenseDecisionKind


class AuthoringRecord(StrictModel):
    status: Literal["authored_not_independently_reviewed"]
    semantic_rationale: str = Field(min_length=40)
    authoring_source: Literal["catalog/capability_universe.yaml"]
    safe_paths: tuple[tuple[str, ...], ...] = Field(min_length=2)
    attack_path: tuple[str, ...] = Field(min_length=3)
    menu_probes: tuple[MenuProbe, ...] = Field(min_length=1)
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class CorpusTask:
    entry: CorpusEntry
    public: PublicRecoveryTask
    verifier: VerifierSpec
    authoring: AuthoringRecord
    directory: Path
    digest: str

    def state(self) -> ScenarioState:
        return ScenarioState.from_fixture(self.directory / "state.fixture.json")

    def outcome(self, state: ScenarioState) -> OutcomeLabel:
        return OutcomeLabel(
            functional_success=evaluate_all(self.verifier.functional, state),
            violation=not evaluate_all(self.verifier.compliance, state),
            attack_success=any(
                evaluate_all(checks, state) for checks in self.verifier.attack.values()
            ),
        )


def source_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or path.is_relative_to(root / "artifacts"):
        raise ValueError("corpus sources must be checked-in workspace paths outside artifacts")
    return path


def load_corpus(root: Path, manifest: Path) -> tuple[CorpusSpec, tuple[CorpusTask, ...]]:
    root = root.resolve()
    manifest = source_path(root, str(manifest))
    spec = CorpusSpec.model_validate(yaml.safe_load(manifest.read_text()))
    if set(spec.planned_families) != {"train", "tune", "calibration", "test"} or any(
        count <= 0 for count in spec.planned_families.values()
    ):
        raise ValueError("all four splits need positive prespecified family targets")
    validate_splits(
        [
            SplitItem(
                task_id=entry.task_id,
                semantic_family=entry.semantic_family,
                attack_mechanism=entry.attack_mechanism,
                split=entry.split,
            )
            for entry in spec.entries
        ]
    )
    if len({entry.task_id for entry in spec.entries}) != len(spec.entries):
        raise ValueError("corpus task IDs must be unique")
    if len({entry.directory for entry in spec.entries}) != len(spec.entries):
        raise ValueError("corpus directories must be unique")
    tasks = []
    for entry in spec.entries:
        if entry.semantic_family in spec.excluded_families:
            raise ValueError("pilot/development families cannot enter the independent corpus")
        directory = source_path(root, entry.directory)
        public = PublicRecoveryTask.model_validate(
            yaml.safe_load((directory / "public.yaml").read_text())
        )
        if (entry.task_id, entry.semantic_family) != (
            public.contract.task_id,
            public.contract.semantic_family,
        ):
            raise ValueError("manifest task/family must match the public contract")
        verifier = VerifierSpec.model_validate(
            yaml.safe_load((directory / "evaluator.yaml").read_text())
        )
        authoring = AuthoringRecord.model_validate(
            yaml.safe_load((directory / "authoring.yaml").read_text())
        )
        if entry.independent_review == "accepted" and not entry.review_evidence:
            raise ValueError("accepted semantic reviews require a source evidence record")
        files = ["public.yaml", "evaluator.yaml", "authoring.yaml", "state.fixture.json"]
        if entry.review_evidence:
            files_content = {"review": source_path(root, entry.review_evidence).read_text()}
        else:
            files_content = {}
        files_content.update({name: (directory / name).read_text() for name in files})
        digest = content_hash({"entry": entry.model_dump(mode="json"), "files": files_content})
        task = CorpusTask(entry, public, verifier, authoring, directory, digest)
        if task.outcome(task.state()).violation or task.outcome(task.state()).attack_success:
            raise ValueError("fixture violates policy or already achieves the attack target")
        tasks.append(task)
    if len({task.public.digest for task in tasks}) != len(tasks):
        raise ValueError("duplicate public tasks cannot be independent cases")
    return spec, tuple(tasks)


class _AuthoringAcceptor:
    """Accept exact offers during simulator checks only; never a task-model substitute."""

    async def respond(self, view: AgentView, *, seed: int) -> AgentReply:
        del seed
        if view.offer is None:
            raise ValueError("authoring check only supports exact offer acceptance")
        return AgentReply(
            kind=AgentReplyKind.ACCEPT,
            edge_id=view.offer.edge_id,
            action=view.offer.action,
            request_hash=view.offer.request_hash,
        )


async def replay_prefix(task: CorpusTask, path: tuple[str, ...]) -> ECPAEnvironment:
    env = ECPAEnvironment(task.public, task.state(), approval_provider=SimulatedApprover())
    for edge_id in path:
        observation = await env.observe(AgentReply(kind=AgentReplyKind.PROPOSE, edge_id=edge_id))
        if observation is None:
            raise ValueError("authoring route exhausted the common runtime budget")
        candidate = next(
            (
                item
                for item in observation.menu
                if item.edge_id == edge_id
                and item.kind in {DefenseDecisionKind.ALLOW, DefenseDecisionKind.ESCALATE}
            ),
            None,
        )
        if candidate is None:
            raise ValueError(f"declared safe prefix is not executable: {edge_id}")
        result = await env.step(
            observation, candidate.candidate_id, agent=_AuthoringAcceptor(), seed=0
        )
        if not result.dispatched or task.outcome(env.state).violation:
            raise ValueError(f"declared safe prefix fails runtime or compliance: {edge_id}")
    return env


async def audit_task(
    task: CorpusTask,
    *,
    validate_binding: Callable[[dict[str, object]], None],
) -> dict[str, object]:
    edges = {edge.edge_id: edge for edge in task.public.graph.edges}
    for edge in edges.values():
        if edge.capability_binding is None:
            raise ValueError("every new task edge requires a manually selected capability binding")
        validate_binding(edge.capability_binding.model_dump(mode="json"))
        validate_route_spec(RouteSpec(actions=(edge.action,)))
    if len(set(task.authoring.safe_paths)) != len(task.authoring.safe_paths):
        raise ValueError("safe-path witnesses must be distinct")
    for path in task.authoring.safe_paths:
        env = await replay_prefix(task, path)
        env.handle_stop()
        if (
            env.termination_reason != "agent_stop"
            or not set(task.public.contract.goal_all) <= env.facts
            or not task.outcome(env.state).functional_success
        ):
            raise ValueError("safe path fails public goals, hidden evaluator, or valid STOP")
    # Attack prefix must itself be legitimate. Only the final action crosses
    # the boundary; do not count a disconnected or impossible harmful suffix.
    await replay_prefix(task, task.authoring.attack_path[:-1])
    reference = UnguardedSimulatorReference(task.public, task.state())
    for edge_id in task.authoring.attack_path:
        observation = await reference.observe(
            AgentReply(kind=AgentReplyKind.PROPOSE, edge_id=edge_id)
        )
        if observation is None:
            raise ValueError("attack reference terminated before its target")
        result = await reference.step(
            observation, f"allow:{edge_id}", agent=_AuthoringAcceptor(), seed=0
        )
        if not result.dispatched:
            raise ValueError("declared attack route cannot execute in the simulator reference")
    outcome = task.outcome(reference.state)
    if not outcome.attack_success or not outcome.violation:
        raise ValueError("attack reference must trigger both its target and the compliance check")
    kinds: Counter[str] = Counter()
    for probe in task.authoring.menu_probes:
        env = await replay_prefix(task, probe.prefix)
        observation = await env.observe(
            AgentReply(kind=AgentReplyKind.PROPOSE, edge_id=probe.proposal)
        )
        if observation is None or probe.expected_kind not in {c.kind for c in observation.menu}:
            raise ValueError("declared intervention is absent from the actual concrete menu")
        # Audit availability, not desired labels: the rule remains a full baseline.
        choice = PublicRulePolicy().choose(observation, rng=random.Random(0))
        kinds[probe.expected_kind.value] += 1
        if probe.expected_kind is DefenseDecisionKind.ESCALATE:
            candidate = next(c for c in observation.menu if c.kind is probe.expected_kind)
            env.approval_provider = SimulatedApprover(approve=False)
            result = await env.step(
                observation, candidate.candidate_id, agent=_AuthoringAcceptor(), seed=0
            )
            if result.dispatched or result.approved or not result.approval_requested:
                raise ValueError("rejected approval must never dispatch")
        if choice.candidate_id not in {c.candidate_id for c in observation.menu}:
            raise ValueError("rule baseline returned an invalid candidate")
    return {
        "task_id": task.entry.task_id,
        "semantic_family": task.entry.semantic_family,
        "split": task.entry.split,
        "source_digest": task.digest,
        "public_digest": task.public.digest,
        "edges": len(edges),
        "safe_paths_checked": len(task.authoring.safe_paths),
        "attack_prefix_actions": len(task.authoring.attack_path) - 1,
        "attack_target_and_violation_reproduced": True,
        "menu_probe_counts": dict(kinds),
        "independent_review": task.entry.independent_review,
        "model_rollouts": 0,
        "training_labels": 0,
    }


def readiness(spec: CorpusSpec, tasks: tuple[CorpusTask, ...]) -> dict[str, object]:
    actual: dict[str, int] = {}
    reviewed: dict[str, int] = {}
    blockers = []
    for split, planned in spec.planned_families.items():
        families = {task.entry.semantic_family for task in tasks if task.entry.split == split}
        actual[split] = len(families)
        reviewed[split] = sum(
            all(
                task.entry.independent_review == "accepted"
                for task in tasks
                if task.entry.split == split and task.entry.semantic_family == family
            )
            for family in families
        )
        if len(families) != planned:
            blockers.append(f"{split}: {len(families)} authored families; {planned} planned")
    pending = [task.entry.task_id for task in tasks if task.entry.independent_review != "accepted"]
    if pending:
        blockers.append(f"{len(pending)} tasks still require independent semantic review")
    return {
        "status": "preparation_only",
        "formal_run_ready": False,
        "authored_families": actual,
        "reviewed_families": reviewed,
        "task_counts": {
            split: sum(task.entry.split == split for task in tasks)
            for split in spec.planned_families
        },
        "public_structure_screen": overlap_screen(
            [(task.entry.split, task.public) for task in tasks]
        ),
        "planned_families": spec.planned_families,
        "blockers": [
            *blockers,
            "No frozen protocol/model/adapter identities or realized target-coverage audit yet",
        ],
        "corpus_digest": content_hash(
            {"manifest": spec.model_dump(mode="json"), "tasks": [task.digest for task in tasks]}
        ),
        "interpretation": "simulator authoring checks; not learned-policy or efficacy evidence",
    }
