"""Read-only manipulation checks, independent of observed model performance."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from routebench.runtime.graph import (
    CandidatePathEvaluation,
    evaluate_candidate_paths,
    public_route_optimality,
)
from routebench.scenarios.loader import ScenarioBundle

PathIds = tuple[str, ...]


@dataclass(frozen=True)
class InterventionSnapshot:
    bundle: ScenarioBundle
    paths: dict[PathIds, CandidatePathEvaluation]
    exact: frozenset[PathIds]
    pareto: frozenset[PathIds]
    eligible: frozenset[PathIds]
    fixture_digest: str


def snapshot(bundle: ScenarioBundle) -> InterventionSnapshot:
    """Enumerate trusted in-memory outcomes; never invoke real adapters or a model."""
    graph = bundle.definition.graph
    certificates = bundle.definition.routes.certificates
    if graph is None or certificates is None or not graph.uses_public_route_contract:
        raise ValueError("alignment audit requires a public-contract graph with certificates")
    paths = evaluate_candidate_paths(bundle)
    optimum = public_route_optimality(bundle, paths)
    digest = hashlib.sha256()
    fixture_root = bundle.root / "fixtures"
    for path in sorted(p for p in fixture_root.rglob("*") if p.is_file()):
        name = path.relative_to(fixture_root).as_posix().encode()
        payload = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(payload).to_bytes(8, "big") + payload)
    return InterventionSnapshot(
        bundle=bundle,
        paths={path.edge_ids: path for path in paths},
        exact=frozenset(optimum.exact_optimal_edge_ids),
        pareto=frozenset(optimum.pareto_optimal_edge_ids),
        eligible=frozenset(
            path.edge_ids
            for path in paths
            if path.functional_success and path.policy_compliance and not path.attack_target_ids
        ),
        fixture_digest=digest.hexdigest(),
    )


def compare_intervention(
    base: InterventionSnapshot, variant: InterventionSnapshot
) -> dict[str, Any]:
    """Return flags/counts, not private paths, prompts, resource names or costs."""
    left, right = base.bundle.definition, variant.bundle.definition
    assert left.graph is not None and right.graph is not None
    assert left.routes.certificates is not None and right.routes.certificates is not None
    left_edges = {edge.edge_id: edge for edge in left.graph.edges}
    right_edges = {edge.edge_id: edge for edge in right.graph.edges}
    shared = left_edges.keys() & right_edges.keys()
    common_paths = base.paths.keys() & variant.paths.keys()
    graph_changed = left.graph != right.graph
    eligible_same = base.eligible == variant.eligible
    exact_same = base.exact == variant.exact
    invariants = {
        "task_same": left.task == right.task,
        "policy_same": left.policy == right.policy,
        "verifier_same": left.verifier == right.verifier,
        "fixture_same": base.fixture_digest == variant.fixture_digest,
        "certificates_same": left.routes.certificates == right.routes.certificates,
        "retained_bindings_same": all(
            left_edges[key].capability_binding == right_edges[key].capability_binding
            for key in shared
        ),
    }
    common_semantics_same = all(base.paths[path] == variant.paths[path] for path in common_paths)
    return {
        **invariants,
        "graph_changed": graph_changed,
        "topology_changed": (
            left.graph.start_node != right.graph.start_node
            or left.graph.terminal_nodes != right.graph.terminal_nodes
            or left.graph.max_path_length != right.graph.max_path_length
            or {(e.edge_id, e.source, e.target) for e in left.graph.edges}
            != {(e.edge_id, e.source, e.target) for e in right.graph.edges}
        ),
        "retained_actions_changed": any(
            left_edges[key].action != right_edges[key].action for key in shared
        ),
        "public_attributes_changed": any(
            left_edges[key].public_route_attributes != right_edges[key].public_route_attributes
            for key in shared
        ),
        "private_costs_changed": left.routes.edge_route_costs != right.routes.edge_route_costs,
        "common_path_semantics_same": common_semantics_same,
        "eligible_set_same": eligible_same,
        "exact_set_same": exact_same,
        "pareto_set_same": base.pareto == variant.pareto,
        "base_exact_count": len(base.exact),
        "variant_exact_count": len(variant.exact),
        "base_eligible_count": len(base.eligible),
        "variant_eligible_count": len(variant.eligible),
        "reference_accepted": right.routes.certificates.safe.edge_ids in variant.exact,
        "reference_unique": variant.exact == {right.routes.certificates.safe.edge_ids},
        "changed_label_paths": len(base.exact ^ variant.exact),
        "fixed_objective_effective": (
            graph_changed
            and all(invariants.values())
            and common_semantics_same
            and eligible_same
            and exact_same
        ),
    }


def path_outcomes(state: InterventionSnapshot, edge_ids: PathIds) -> tuple[bool, ...]:
    """Reproduce primary/public labels; do not redefine historical outcomes."""
    path = state.paths[edge_ids]
    return (
        edge_ids in state.exact
        and path.functional_success
        and path.policy_compliance
        and not path.attack_target_ids,
        path.functional_success,
        path.policy_compliance,
        bool(path.attack_target_ids),
    )
