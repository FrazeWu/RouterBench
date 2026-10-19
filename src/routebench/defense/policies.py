"""Deterministic public-input policies used as defense baselines."""

from __future__ import annotations

from routebench.defense.ecpa import DefenseDecision, DefenseDecisionKind, DefenseObservation
from routebench.scenarios.schema import RouteActionSpec


class PublicRulePolicy:
    """A conservative rule policy that never treats private fixture values as input."""

    def __init__(self, protected_labels: frozenset[str] = frozenset({"protected", "personal"})):
        self.protected_labels = protected_labels

    def decide(
        self,
        observation: DefenseObservation,
        replacements: tuple[RouteActionSpec, ...] = (),
    ) -> DefenseDecision:
        del replacements
        if self.protected_labels.intersection(observation.labels):
            return DefenseDecision(DefenseDecisionKind.ESCALATE)
        return DefenseDecision(DefenseDecisionKind.ALLOW)
