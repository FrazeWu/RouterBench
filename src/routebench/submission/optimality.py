"""SMT topology enumeration and an independent public-score implementation."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from routebench.runtime.graph import (
    _evaluate_path,
    enumerate_terminal_paths,
    public_route_optimality,
)
from routebench.scenarios.loader import load_scenario
from routebench.submission.graph import ordinal_score


def smt_paths(graph: Any) -> tuple[tuple[str, ...], ...]:
    import z3

    solver = z3.Solver()
    solver.set(timeout=30000)
    length = z3.Int("length")
    source = z3.Function("edge_source", z3.IntSort(), z3.IntSort())
    target = z3.Function("edge_target", z3.IntSort(), z3.IntSort())
    nodes = {node.node_id: index for index, node in enumerate(graph.nodes)}
    positions = [z3.Int(f"edge_{i}") for i in range(graph.max_path_length)]
    solver.add(length >= 1, length <= graph.max_path_length)
    for index, edge in enumerate(graph.edges):
        solver.add(source(index) == nodes[edge.source], target(index) == nodes[edge.target])
    for i, position in enumerate(positions):
        solver.add(
            z3.If(i < length, z3.And(position >= 0, position < len(graph.edges)), position == -1)
        )
        if i:
            solver.add(z3.Implies(i < length, source(position) == target(positions[i - 1])))
    solver.add(source(positions[0]) == nodes[graph.start_node])
    solver.add(
        z3.Or(
            *[
                z3.And(
                    length == i + 1,
                    z3.Or(*[target(position) == nodes[node] for node in graph.terminal_nodes]),
                )
                for i, position in enumerate(positions)
            ]
        )
    )
    paths: list[tuple[str, ...]] = []
    while True:
        result = solver.check()
        if result == z3.unsat:
            return tuple(sorted(paths))
        if result != z3.sat:
            raise RuntimeError(f"independent SMT enumeration incomplete: {solver.reason_unknown()}")
        model = solver.model()
        count = model.eval(length).as_long()
        chosen = [model.eval(position).as_long() for position in positions[:count]]
        paths.append(tuple(graph.edges[index].edge_id for index in chosen))
        if len(paths) > 100000:
            raise RuntimeError("independent SMT path limit exceeded")
        solver.add(
            z3.Or(
                length != count,
                *[
                    position != index
                    for position, index in zip(positions[:count], chosen, strict=True)
                ],
            )
        )


def audit_scenario(path: Path) -> dict[str, Any]:
    import z3

    began = time.perf_counter()
    bundle = load_scenario(path)
    graph = bundle.definition.graph
    if graph is None:
        raise ValueError("optimality validation requires a candidate graph")
    independent = smt_paths(graph)
    native = tuple(sorted(enumerate_terminal_paths(graph)))
    if independent != native:
        raise ValueError("SMT and native bounded path sets disagree")
    edges = {edge.edge_id: edge for edge in graph.edges}
    eligible = []
    attacks = []
    for edge_ids in independent:
        evaluated = _evaluate_path(bundle, graph, edge_ids)
        if evaluated.attack_target_ids:
            attacks.append(edge_ids)
        if (
            evaluated.functional_success
            and evaluated.policy_compliance
            and not evaluated.attack_target_ids
        ):
            cost = tuple(
                sum(ordinal_score(edges[edge_id])[dimension] for edge_id in edge_ids)
                for dimension in range(4)
            )
            eligible.append((edge_ids, cost))
    if not eligible:
        raise ValueError("no eligible public route optimum")
    best = min(score for _, score in eligible)
    optimum = tuple(sorted(route for route, score in eligible if score == best))
    expected = tuple(sorted(public_route_optimality(bundle).exact_optimal_edge_ids))
    if optimum != expected:
        raise ValueError("independent public lexicographic optimum differs")
    # The explicit interface can traverse intermediate terminal nodes and stop
    # at the declared final terminal, making every bounded path selectable.
    for route in independent:
        node = graph.start_node
        for edge_id in route:
            if edges[edge_id].source != node:
                raise ValueError("a bounded route is not selectable")
            node = edges[edge_id].target
        if node not in graph.terminal_nodes:
            raise ValueError("a bounded route cannot explicitly stop")
    return {
        "scenario_id": bundle.definition.metadata.scenario_id,
        "scenario_digest": bundle.digest,
        "status": "complete",
        "solver": f"Z3 {z3.get_version_string()}",
        "bounded_paths": len(independent),
        "safe_functional_paths": len(eligible),
        "attack_paths": len(attacks),
        "equal_optima": len(optimum),
        "topology_agrees": True,
        "optimum_agrees": True,
        "all_paths_selectable": True,
        "duration_seconds": time.perf_counter() - began,
        "shared_component": "trusted simulator eligibility evaluation",
    }
