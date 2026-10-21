"""Public, executable recovery contracts, independent of evaluator certificates.

Facts are trusted abstractions certified by successful tool receipts. They are not
inferred from model text, and a contract's soundness is an authoring obligation.
This module deliberately has no fixture, verifier, reference-route or executor API.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import Field, model_validator

from routebench.scenarios.schema import (
    AuthorityAtom,
    AuthorityGrant,
    CandidateGraph,
    GraphEdgeSpec,
    PolicySpec,
    StrictModel,
)


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def scope_covers(scope: str, target: str) -> bool:
    if scope == "*":
        return True
    if scope.endswith("/**"):
        root = scope[:-3].rstrip("/")
        return target == root or target.startswith(root + "/")
    return scope == target


def granted(atom: AuthorityAtom, grants: tuple[AuthorityGrant, ...]) -> bool:
    return any(
        atom.resource == grant.resource
        and atom.operation in grant.operations
        and scope_covers(grant.scope, atom.target)
        for grant in grants
    )


class PublicEffect(StrictModel):
    resource: str
    operation: str
    target: str
    # Subtargets touched by this action, e.g. jobs.owner_email. These are effect
    # contracts, not values read from hidden fixtures by the witness.
    subtargets: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()


class ActionContract(StrictModel):
    requires: tuple[str, ...] = ()
    adds: tuple[str, ...] = ()
    removes: tuple[str, ...] = ()
    effects: tuple[PublicEffect, ...] = Field(min_length=1)
    deterministic: bool = True

    @model_validator(mode="after")
    def consistent_effects(self) -> ActionContract:
        if set(self.adds).intersection(self.removes):
            raise ValueError("a fact cannot be both added and removed")
        return self

    def successor(self, facts: frozenset[str]) -> frozenset[str]:
        return (facts - set(self.removes)) | set(self.adds)


class ApprovalRule(StrictModel):
    grant_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    edge_ids: tuple[str, ...] = Field(min_length=1)
    grants: tuple[AuthorityGrant, ...] = Field(min_length=1)
    validity_decisions: int = Field(gt=0)


class RecoveryContract(StrictModel):
    protocol: str = "ecpa-recovery"
    task_id: str
    semantic_family: str
    initial_facts: tuple[str, ...] = ()
    goal_all: tuple[str, ...] = Field(min_length=1)
    actions: dict[str, ActionContract]
    initial_grants: tuple[AuthorityGrant, ...] = ()
    approvals: tuple[ApprovalRule, ...] = ()

    def validate_graph(self, graph: CandidateGraph) -> None:
        edge_ids = {edge.edge_id for edge in graph.edges}
        if set(self.actions) != edge_ids:
            raise ValueError("public contracts must cover exactly the registered graph edges")
        grant_ids = [item.grant_id for item in self.approvals]
        if len(set(grant_ids)) != len(grant_ids):
            raise ValueError("approval grant IDs must be unique")
        if any(set(rule.edge_ids) - edge_ids for rule in self.approvals):
            raise ValueError("approval references an unknown edge")


class PublicRecoveryTask(StrictModel):
    prompt: str
    functional_goal: str
    graph: CandidateGraph
    policy: PolicySpec
    contract: RecoveryContract

    @model_validator(mode="after")
    def complete_contract(self) -> PublicRecoveryTask:
        self.contract.validate_graph(self.graph)
        return self

    @property
    def digest(self) -> str:
        return content_hash(self.model_dump(mode="json"))


def load_recovery_contract(path: Path) -> RecoveryContract:
    return RecoveryContract.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def public_policy_allows(task: PublicRecoveryTask, edge: GraphEdgeSpec) -> bool:
    """Conservative structural check using declared public effect contracts only."""
    for effect in task.contract.actions[edge.edge_id].effects:
        for forbidden in task.policy.forbidden_effects:
            if effect.resource != forbidden.resource or effect.operation != forbidden.operation:
                continue
            touched = (effect.target, *effect.subtargets)
            if not any(scope_covers(forbidden.scope, target) for target in touched):
                continue
            if not forbidden.protected_labels or set(effect.labels).intersection(
                forbidden.protected_labels
            ):
                return False
    return True


class WitnessStatus(StrEnum):
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"


class WitnessResult(StrictModel):
    status: WitnessStatus
    expansions: int = Field(ge=0)


def completion_witness(
    task: PublicRecoveryTask,
    *,
    node: str,
    facts: frozenset[str],
    executed_edge_ids: tuple[str, ...],
    grants: tuple[AuthorityGrant, ...],
    remaining_executions: int,
    max_expansions: int,
    remaining_approvals: int = 0,
) -> WitnessResult:
    """Bounded contract search; returns no path or private cost/answer information.

    No tool is executed, even on a clone. Unknown outcomes or a search limit yield
    UNKNOWN unless a structurally certified suffix is found. A future declared
    approval is a possible transition, charged to the approval budget. Its real
    rejection remains a rollout failure, not a guarantee of success.
    """
    pending = deque([(node, facts, executed_edge_ids, remaining_executions, remaining_approvals)])
    visited: set[tuple[str, frozenset[str], tuple[str, ...], int, int]] = set()
    unknown = False
    expansions = 0
    edges = {edge.edge_id: edge for edge in task.graph.edges}
    while pending:
        current, current_facts, history, remaining, approvals_left = pending.popleft()
        if current in task.graph.terminal_nodes and set(task.contract.goal_all) <= current_facts:
            return WitnessResult(status=WitnessStatus.FEASIBLE, expansions=expansions)
        key = (current, current_facts, history, remaining, approvals_left)
        if key in visited or remaining <= 0:
            continue
        if expansions >= max_expansions:
            unknown = True
            break
        visited.add(key)
        expansions += 1
        prior = [edges[edge_id].action for edge_id in history]
        for edge in task.graph.edges:
            contract = task.contract.actions[edge.edge_id]
            if (
                edge.source != current
                or not set(contract.requires) <= current_facts
                or not public_policy_allows(task, edge)
                or any(
                    not any(
                        action.tool == requirement.tool
                        and action.arguments == requirement.arguments
                        for action in prior
                    )
                    for requirement in edge.action.requires_prior_actions
                )
            ):
                continue
            approval_cost = 0
            if not all(granted(atom, grants) for atom in edge.authority):
                approvable = approvals_left > 0 and any(
                    edge.edge_id in rule.edge_ids
                    and all(granted(atom, grants + rule.grants) for atom in edge.authority)
                    for rule in task.contract.approvals
                )
                if not approvable:
                    continue
                approval_cost = 1
            if not contract.deterministic:
                unknown = True
                continue
            pending.append(
                (
                    edge.target,
                    contract.successor(current_facts),
                    (*history, edge.edge_id),
                    remaining - 1,
                    approvals_left - approval_cost,
                )
            )
    return WitnessResult(
        status=WitnessStatus.UNKNOWN if unknown else WitnessStatus.INFEASIBLE,
        expansions=expansions,
    )
