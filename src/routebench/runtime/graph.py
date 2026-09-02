"""Bounded candidate-graph execution and unique least-authority validation."""

from __future__ import annotations

from dataclasses import dataclass

from routebench.contracts import ActionRequest
from routebench.evaluation import evaluate_all
from routebench.runtime.reference import ScenarioState, TrustedToolExecutor
from routebench.scenarios.loader import ScenarioBundle
from routebench.scenarios.schema import AuthorityAtom, CandidateGraph, GraphEdgeSpec, RouteSpec

_MAX_ENUMERATED_PATHS = 100_000


class GraphAuditError(ValueError):
    """A candidate graph does not establish the benchmark's path-selection contract."""


@dataclass(frozen=True, slots=True)
class CandidatePathEvaluation:
    edge_ids: tuple[str, ...]
    functional_success: bool
    policy_compliance: bool
    attack_target_ids: tuple[str, ...]
    authority_footprint: frozenset[AuthorityAtom]

    @property
    def action_count(self) -> int:
        return len(self.edge_ids)


@dataclass(frozen=True, slots=True)
class GraphAuditResult:
    scenario_id: str
    total_terminal_paths: int
    functional_paths: int
    compliant_functional_paths: int
    attack_paths: int
    nonoptimal_paths_no_longer_than_optimum: int
    unique_optimal_edge_ids: tuple[str, ...]
    optimal_authority_footprint: frozenset[AuthorityAtom]


def route_from_graph_path(graph: CandidateGraph, edge_ids: tuple[str, ...]) -> RouteSpec:
    """Validate path continuity and materialize its evaluator-owned actions."""

    return RouteSpec(actions=graph.actions_for_path(edge_ids))


def enumerate_terminal_paths(graph: CandidateGraph) -> tuple[tuple[str, ...], ...]:
    """Enumerate every terminal path within the declared finite search bound."""

    outgoing: dict[str, list[GraphEdgeSpec]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source, []).append(edge)
    for edges in outgoing.values():
        edges.sort(key=lambda edge: edge.edge_id)

    paths: list[tuple[str, ...]] = []

    def visit(node_id: str, prefix: tuple[str, ...]) -> None:
        if node_id in graph.terminal_nodes:
            paths.append(prefix)
            if len(paths) > _MAX_ENUMERATED_PATHS:
                raise GraphAuditError(
                    f"candidate graph exceeds {_MAX_ENUMERATED_PATHS} bounded terminal paths"
                )
        if len(prefix) >= graph.max_path_length:
            return
        for edge in outgoing.get(node_id, ()):
            visit(edge.target, (*prefix, edge.edge_id))

    visit(graph.start_node, ())
    if not paths:
        raise GraphAuditError("candidate graph has no reachable terminal path within its bound")
    return tuple(paths)


def _fixture_state(bundle: ScenarioBundle) -> ScenarioState:
    fixture = bundle.root / "fixtures" / "state.json"
    if not fixture.is_file():
        raise GraphAuditError(f"scenario is missing fixture state: {fixture}")
    return ScenarioState.from_fixture(fixture)


def _evaluate_path(
    bundle: ScenarioBundle, graph: CandidateGraph, edge_ids: tuple[str, ...]
) -> CandidatePathEvaluation:
    edges = {edge.edge_id: edge for edge in graph.edges}
    graph.actions_for_path(edge_ids)
    state = _fixture_state(bundle)
    executor = TrustedToolExecutor()
    footprint: set[AuthorityAtom] = set()

    for index, edge_id in enumerate(edge_ids):
        edge = edges[edge_id]
        preview = executor.preview(edge.action, state)
        actual = frozenset(
            {
                AuthorityAtom(
                    resource=preview.effect.resource,
                    operation=preview.effect.operation,
                    target=preview.effect.target,
                )
            }
        )
        declared = frozenset(edge.authority)
        if actual != declared:
            raise GraphAuditError(
                f"graph edge {edge_id!r} authority does not match trusted preview: "
                f"declared={sorted((a.resource, a.operation, a.target) for a in declared)}, "
                f"actual={sorted((a.resource, a.operation, a.target) for a in actual)}"
            )
        request = ActionRequest(
            action_id=f"graph-audit-{index}",
            step=index,
            tool=edge.action.tool,
            arguments=edge.action.arguments,
            effects=(preview.effect,),
        )
        executor.execute(request, state)
        footprint.update(actual)

    attack_targets = tuple(
        target_id
        for target_id, assertions in bundle.definition.verifier.attack.items()
        if evaluate_all(assertions, state)
    )
    return CandidatePathEvaluation(
        edge_ids=edge_ids,
        functional_success=evaluate_all(bundle.definition.verifier.functional, state),
        policy_compliance=evaluate_all(bundle.definition.verifier.compliance, state),
        attack_target_ids=attack_targets,
        authority_footprint=frozenset(footprint),
    )


def _unique_least_authority_path(
    paths: tuple[CandidatePathEvaluation, ...],
) -> CandidatePathEvaluation:
    successful = tuple(path for path in paths if path.functional_success)
    if not successful:
        raise GraphAuditError("candidate graph has no functionally successful terminal path")

    minimal = tuple(
        candidate
        for candidate in successful
        if not any(
            other.authority_footprint < candidate.authority_footprint for other in successful
        )
    )
    minimal_footprints = {candidate.authority_footprint for candidate in minimal}
    if len(minimal_footprints) != 1:
        raise GraphAuditError("candidate graph has incomparable least-authority successful paths")

    shortest_length = min(candidate.action_count for candidate in minimal)
    shortest = tuple(
        candidate for candidate in minimal if candidate.action_count == shortest_length
    )
    if len(shortest) != 1:
        raise GraphAuditError(
            "candidate graph has multiple equally short successful paths with the same "
            "least-authority footprint"
        )
    return shortest[0]


def audit_candidate_graph(bundle: ScenarioBundle) -> GraphAuditResult:
    """Prove the hidden safe certificate is the unique global optimum."""

    graph = bundle.definition.graph
    certificates = bundle.definition.routes.certificates
    if graph is None or certificates is None:
        raise GraphAuditError("scenario does not declare a schema v4 candidate graph")

    terminal_paths = enumerate_terminal_paths(graph)
    covered_edges = {edge_id for path in terminal_paths for edge_id in path}
    declared_edges = {edge.edge_id for edge in graph.edges}
    if covered_edges != declared_edges:
        raise GraphAuditError(
            "candidate graph contains edges that are absent from every bounded terminal path: "
            f"{sorted(declared_edges - covered_edges)}"
        )

    evaluations = tuple(_evaluate_path(bundle, graph, path) for path in terminal_paths)
    optimum = _unique_least_authority_path(evaluations)
    nonoptimal_short_paths = tuple(
        path
        for path in evaluations
        if path.edge_ids != optimum.edge_ids and path.action_count <= optimum.action_count
    )
    if not nonoptimal_short_paths:
        raise GraphAuditError(
            "candidate graph is solvable by selecting its unique shortest terminal path"
        )
    if optimum.edge_ids != certificates.safe.edge_ids:
        raise GraphAuditError(
            "hidden safe certificate is not the computed unique least-authority successful path"
        )
    if not optimum.policy_compliance or optimum.attack_target_ids:
        raise GraphAuditError("computed optimal path is not policy-compliant and attack-free")

    evaluations_by_path = {evaluation.edge_ids: evaluation for evaluation in evaluations}
    for target_id, certificate in certificates.attack.items():
        try:
            evaluation = evaluations_by_path[certificate.edge_ids]
        except KeyError as error:
            raise GraphAuditError(
                f"attack certificate {target_id!r} is not a bounded terminal path"
            ) from error
        if not evaluation.functional_success or target_id not in evaluation.attack_target_ids:
            raise GraphAuditError(f"attack certificate {target_id!r} does not produce JointSuccess")
        if evaluation.policy_compliance:
            raise GraphAuditError(
                f"attack certificate {target_id!r} unexpectedly remains policy-compliant"
            )

    return GraphAuditResult(
        scenario_id=bundle.definition.metadata.scenario_id,
        total_terminal_paths=len(evaluations),
        functional_paths=sum(path.functional_success for path in evaluations),
        compliant_functional_paths=sum(
            path.functional_success and path.policy_compliance for path in evaluations
        ),
        attack_paths=sum(bool(path.attack_target_ids) for path in evaluations),
        nonoptimal_paths_no_longer_than_optimum=len(nonoptimal_short_paths),
        unique_optimal_edge_ids=optimum.edge_ids,
        optimal_authority_footprint=optimum.authority_footprint,
    )
