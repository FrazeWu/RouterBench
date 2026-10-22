"""Public evaluation metadata shared by RouteBench and ECPA.

The evaluator owns fixtures, certificates and verifier outcomes.  This module
deliberately projects only public graph/audit metadata into defense collection
and converts a graph-selection result into aggregate endpoint fields.  The
projection is for stratification and reporting; it is not an authorization
input and must not be passed to the online scorer as hidden supervision.
"""

from __future__ import annotations

from dataclasses import dataclass

from routebench.evaluation.graph_selection import GraphSelectionResult
from routebench.runtime.graph import (
    audit_candidate_graph,
    public_route_optimality,
)
from routebench.scenarios.loader import ScenarioBundle


@dataclass(frozen=True, slots=True)
class PublicEvaluationContext:
    """Evaluation-owned metadata safe to join with a defense episode manifest."""

    scenario_id: str
    scenario_digest: str
    split: str
    semantic_family: str
    primary_effect_family: str | None
    primary_attack_mechanism: str | None
    route_length: str | None
    candidate_edges: int
    total_terminal_paths: int
    functional_paths: int
    compliant_functional_paths: int
    attack_paths: int
    public_candidate_count: int | None
    public_rule_unique: bool | None
    public_optimum_available: bool

    @property
    def stratification_key(self) -> tuple[str, str | None, str | None]:
        """Stable public grouping key; no evaluator result or route is included."""

        return (self.semantic_family, self.primary_effect_family, self.route_length)


@dataclass(frozen=True, slots=True)
class PublicBaselineResult:
    """Public endpoint projection of a graph-selection baseline.

    In particular, this type intentionally omits ``matches_hidden_certificate``
    and the evaluator-owned execution state from ``GraphSelectionResult``.
    """

    scenario_id: str
    seed: int
    selected_edge_count: int
    functional_success: bool
    policy_compliance: bool
    attack_success: bool
    public_exact_optimal: bool | None
    public_pareto_optimal: bool | None
    actions_executed: int
    intervened: bool
    proposals_used: int
    status: str
    termination_reason: str | None


def build_public_evaluation_context(bundle: ScenarioBundle) -> PublicEvaluationContext:
    """Project a scenario and graph audit into defense-safe public metadata.

    ``audit_candidate_graph`` runs on the evaluator side, but only aggregate
    counts and public taxonomy labels leave this function.  No fixture value,
    certificate edge sequence, verifier assertion or private route cost is
    returned.
    """

    graph = bundle.definition.graph
    if graph is None:
        raise ValueError("defense evaluation context requires a candidate graph")
    audit = audit_candidate_graph(bundle)
    target_id = bundle.definition.metadata.primary_target_id
    profile = (
        bundle.definition.metadata.case_profiles.get(target_id) if target_id is not None else None
    )
    public = public_route_optimality(bundle) if graph.uses_public_route_contract else None
    return PublicEvaluationContext(
        scenario_id=bundle.definition.metadata.scenario_id,
        scenario_digest=bundle.digest,
        split=bundle.definition.metadata.split.value,
        semantic_family=bundle.definition.metadata.template_family_id
        or bundle.definition.metadata.scenario_id,
        primary_effect_family=(profile.primary_effect_family.value if profile else None),
        primary_attack_mechanism=(profile.primary_attack_mechanism.value if profile else None),
        route_length=(profile.route_length.value if profile else None),
        candidate_edges=len(graph.edges),
        total_terminal_paths=audit.total_terminal_paths,
        functional_paths=audit.functional_paths,
        compliant_functional_paths=audit.compliant_functional_paths,
        attack_paths=audit.attack_paths,
        public_candidate_count=(
            audit.observable_optimum.public_candidate_count if public else None
        ),
        public_rule_unique=(audit.observable_optimum.public_rule_unique if public else None),
        public_optimum_available=public is not None,
    )


def project_graph_selection_result(result: GraphSelectionResult) -> PublicBaselineResult:
    """Convert an existing evaluator result into non-privileged baseline data."""

    execution = result.execution
    return PublicBaselineResult(
        scenario_id=result.scenario_id,
        seed=result.seed,
        selected_edge_count=len(result.selected_edge_ids),
        functional_success=execution.functional_success,
        policy_compliance=execution.policy_compliance,
        attack_success=execution.attack_success,
        public_exact_optimal=result.public_exact_optimal,
        public_pareto_optimal=result.public_pareto_optimal,
        actions_executed=execution.actions_executed,
        intervened=execution.intervened,
        proposals_used=execution.proposals_used,
        status=execution.status.value,
        termination_reason=execution.termination_reason,
    )


def evaluation_context_manifest(context: PublicEvaluationContext) -> dict[str, object]:
    """Return the JSON-safe join record used by collection manifests."""

    return {
        "scenario_id": context.scenario_id,
        "scenario_digest": context.scenario_digest,
        "split": context.split,
        "semantic_family": context.semantic_family,
        "primary_effect_family": context.primary_effect_family,
        "primary_attack_mechanism": context.primary_attack_mechanism,
        "route_length": context.route_length,
        "graph": {
            "candidate_edges": context.candidate_edges,
            "total_terminal_paths": context.total_terminal_paths,
            "functional_paths": context.functional_paths,
            "compliant_functional_paths": context.compliant_functional_paths,
            "attack_paths": context.attack_paths,
        },
        "public_route": {
            "candidate_count": context.public_candidate_count,
            "rule_unique": context.public_rule_unique,
            "available": context.public_optimum_available,
        },
        "online_runtime_input": False,
        "hidden_evaluator_data": False,
    }
