"""Matched-information deterministic and logging policies."""

from __future__ import annotations

import random

from routebench.defense.collect import DefensePolicy, PolicyChoice
from routebench.defense.contracts import (
    WitnessStatus,
    completion_witness,
)
from routebench.defense.ecpa import DefenseCandidate, DefenseDecisionKind, DefenseObservation


class PublicRulePolicy:
    """Public goal/precondition progress, then lower-friction intervention.

    This fixed heuristic uses no search or private reference path. It avoids
    further effects after the public goal and prefers progress along declared
    fact dependencies when multiple guarded candidates are available.
    """

    def choose(self, observation: DefenseObservation, *, rng: random.Random) -> PolicyChoice:
        del rng
        priority = {
            DefenseDecisionKind.ALLOW: 0,
            DefenseDecisionKind.CONSTRAIN: 1,
            DefenseDecisionKind.ESCALATE: 2,
            DefenseDecisionKind.DENY: 3,
        }
        facts = frozenset(observation.facts)
        goal = set(observation.task.contract.goal_all)
        if goal <= facts:
            return PolicyChoice("deny")
        relevant = set(goal)
        while True:
            expanded = relevant | {
                fact
                for action in observation.task.contract.actions.values()
                if relevant.intersection(action.adds)
                for fact in action.requires
            }
            if expanded == relevant:
                break
            relevant = expanded

        def rank(item: DefenseCandidate) -> tuple[int, int, str]:
            if item.edge_id is None:
                return (1, priority[item.kind], item.candidate_id)
            action = observation.task.contract.actions[item.edge_id]
            progress = len((set(action.adds) - facts) & relevant) - len(
                set(action.removes) & relevant
            )
            return (-progress, priority[item.kind], item.candidate_id)

        candidate = min(observation.menu, key=rank)
        return PolicyChoice(candidate.candidate_id)


class BlockThenRecoverPolicy:
    """Allow all guard-admissible proposals; recover only after a guard block."""

    def choose(self, observation: DefenseObservation, *, rng: random.Random) -> PolicyChoice:
        del rng
        priority = {
            DefenseDecisionKind.ALLOW: 0,
            DefenseDecisionKind.CONSTRAIN: 1,
            DefenseDecisionKind.ESCALATE: 2,
            DefenseDecisionKind.DENY: 3,
        }
        candidate = min(observation.menu, key=lambda item: (priority[item.kind], item.candidate_id))
        return PolicyChoice(candidate.candidate_id)


class PublicSearchPolicy:
    """Proactive contract feasibility baseline without private path/fixture access.

    Search cost is returned to the runner and charged to its common ledger; the
    policy has no effectful trial executor or agent-success oracle.
    """

    def __init__(self) -> None:
        self.search_expansions = 0

    def choose(self, observation: DefenseObservation, *, rng: random.Random) -> PolicyChoice:
        self.search_expansions = 0
        edges = {edge.edge_id: edge for edge in observation.task.graph.edges}
        ranked: list[tuple[int, int, str]] = []
        for candidate in observation.menu:
            if candidate.edge_id is None:
                ranked.append((2, 0, candidate.candidate_id))
                continue
            edge = edges[candidate.edge_id]
            contract = observation.task.contract.actions[edge.edge_id]
            remaining_search = (
                min(observation.remaining["searches"], observation.remaining["total"])
                - self.search_expansions
            )
            result = completion_witness(
                observation.task,
                node=edge.target,
                facts=contract.successor(frozenset(observation.facts)),
                executed_edge_ids=(*(item.edge_id for item in observation.receipts), edge.edge_id),
                grants=observation.grants,
                remaining_executions=min(
                    observation.remaining["executions"], observation.remaining["decisions"]
                )
                - 1,
                max_expansions=max(0, remaining_search),
                remaining_approvals=observation.remaining["approvals"]
                - int(candidate.kind is DefenseDecisionKind.ESCALATE),
            )
            self.search_expansions += result.expansions
            ranked.append(
                (
                    0 if result.status is WitnessStatus.FEASIBLE else 3,
                    int(candidate.kind is not DefenseDecisionKind.ALLOW),
                    candidate.candidate_id,
                )
            )
        return PolicyChoice(min(ranked)[2], search_expansions=self.search_expansions)


class MixtureLoggingPolicy:
    """Half fixed behavior, half uniform over the actual concrete menu."""

    def __init__(self, rules: DefensePolicy | None = None, uniform_weight: float = 0.5):
        if not 0 <= uniform_weight <= 1:
            raise ValueError("uniform weight must be in [0, 1]")
        self.rules = rules or PublicRulePolicy()
        self.uniform_weight = uniform_weight

    def choose(self, observation: DefenseObservation, *, rng: random.Random) -> PolicyChoice:
        rule = self.rules.choose(observation, rng=rng)
        menu = observation.menu
        selected = (
            rng.choice(menu).candidate_id
            if rng.random() < self.uniform_weight
            else rule.candidate_id
        )
        probability = self.uniform_weight / len(menu) + (
            (1 - self.uniform_weight) if selected == rule.candidate_id else 0
        )
        return PolicyChoice(selected, probability, rule.search_expansions)
