#!/usr/bin/env python3
"""Prepare an auditable graph-component ablation subset.

The formal 776-case inventory is immutable.  This command selects a balanced,
deterministic diagnostic subset and optionally materializes graph variants under
``artifacts/``.  Every materialized variant keeps the evaluator-owned safe and
attack certificates, so it can be checked by the existing graph audit before a
model is run.

The command never edits ``scenarios/formal_v1/test`` and never stores prompts or
model responses in its manifest.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml

from routebench.runtime.graph import audit_candidate_graph, evaluate_candidate_paths
from routebench.scenarios import load_scenario
from routebench.scenarios.loader import ScenarioBundle

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO_ROOT = ROOT / "scenarios" / "formal_v1" / "test"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "private" / "component-ablation-v1-20261003"
DEFAULT_SELECTION_SEED = 20261003
DEFAULT_PER_CELL = 4

VARIANTS = (
    "complete",
    "danger_decoys_removed",
    "functional_alternatives_pruned",
    "dependencies_stripped",
    "authority_contrast_flattened",
)


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return payload


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8"
    )


def _labels(bundle: ScenarioBundle) -> tuple[str, str]:
    metadata = bundle.definition.metadata
    target_id = metadata.primary_target_id
    if target_id is None:
        raise ValueError(f"{metadata.scenario_id} has no primary target")
    profile = metadata.case_profiles[target_id]
    return profile.primary_effect_family.value, profile.route_length.value


def _stable_rank(scenario_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{scenario_id}".encode("utf-8")).hexdigest()


def select_balanced(
    bundles: Iterable[ScenarioBundle], *, per_cell: int, seed: int
) -> tuple[ScenarioBundle, ...]:
    """Select the first ``per_cell`` cases in each effect-family/length cell."""

    if per_cell < 1:
        raise ValueError("per_cell must be positive")
    cells: dict[tuple[str, str], list[ScenarioBundle]] = defaultdict(list)
    for bundle in bundles:
        cells[_labels(bundle)].append(bundle)
    selected: list[ScenarioBundle] = []
    for key in sorted(cells):
        ranked = sorted(
            cells[key],
            key=lambda bundle: _stable_rank(bundle.definition.metadata.scenario_id, seed),
        )
        if len(ranked) < per_cell:
            raise ValueError(f"cell {key} has only {len(ranked)} cases; need {per_cell}")
        selected.extend(ranked[:per_cell])
    return tuple(sorted(selected, key=lambda bundle: bundle.definition.metadata.scenario_id))


def _certificate_edge_ids(bundle: ScenarioBundle) -> tuple[set[str], set[str]]:
    certificates = bundle.definition.routes.certificates
    if certificates is None:
        raise ValueError(f"{bundle.root} has no path certificates")
    safe = set(certificates.safe.edge_ids)
    attack = set(
        edge_id
        for certificate in certificates.attack.values()
        for edge_id in certificate.edge_ids
    )
    return safe, attack


def _witness_paths(bundle: ScenarioBundle) -> tuple[set[str], set[str]]:
    """Return edge IDs for safe and shortest non-optimal witness paths.

    The existing graph-audit contract deliberately requires a non-optimal path
    no longer than the optimum.  Most cases have a benign functional witness;
    a few short scenarios do not, so we retain the shortest non-safe terminal
    path as a structural witness and record its outcome in the audit manifest.
    """

    safe_ids, _ = _certificate_edge_ids(bundle)
    certificates = bundle.definition.routes.certificates
    if certificates is None:
        raise ValueError(f"{bundle.root} has no path certificates")
    safe_path = tuple(certificates.safe.edge_ids)
    paths = evaluate_candidate_paths(bundle)
    safe_length = len(safe_path)
    candidates = [
        path
        for path in paths
        if path.edge_ids != safe_path and path.action_count <= safe_length
    ]
    candidates.sort(
        key=lambda path: (
            bool(path.attack_target_ids),
            not path.functional_success,
            path.action_count,
            path.edge_ids,
        )
    )
    witness = set(candidates[0].edge_ids) if candidates else set()
    return safe_ids, witness


def _reachable_path_edge_ids(bundle: ScenarioBundle) -> dict[str, set[str]]:
    """Classify edges by the terminal paths exposed by the original graph."""

    paths = evaluate_candidate_paths(bundle)
    no_attack: set[str] = set()
    attack: set[str] = set()
    for path in paths:
        if path.attack_target_ids:
            attack.update(path.edge_ids)
        else:
            no_attack.update(path.edge_ids)
    return {"no_attack": no_attack, "attack": attack}


def _variant_edge_ids(bundle: ScenarioBundle, variant: str) -> set[str]:
    graph = bundle.definition.graph
    if graph is None:
        raise ValueError(f"{bundle.root} has no candidate graph")
    all_ids = {edge.edge_id for edge in graph.edges}
    safe_ids, attack_certificate_ids = _certificate_edge_ids(bundle)
    if variant == "complete" or variant in {"dependencies_stripped", "authority_contrast_flattened"}:
        return all_ids
    if variant == "danger_decoys_removed":
        # Retain all benign paths, plus the one attack certificate required by
        # the schema.  Attack-only decoy edges are the ablated component.  A
        # short structural witness is retained when a case has no benign
        # non-optimal route, because the graph audit requires one.
        benign = _reachable_path_edge_ids(bundle)["no_attack"]
        _, witness = _witness_paths(bundle)
        return benign | witness | attack_certificate_ids | safe_ids
    if variant == "functional_alternatives_pruned":
        safe, witness = _witness_paths(bundle)
        # A missing witness is reported by the audit manifest rather than
        # silently manufacturing a route.  The retained graph remains schema-
        # valid because all attack certificates are retained.
        return safe | witness | attack_certificate_ids
    raise ValueError(f"unknown variant: {variant}")


def _project_graph(graph: dict[str, Any], retained_ids: set[str]) -> dict[str, Any]:
    edges = [edge for edge in graph["edges"] if edge["edge_id"] in retained_ids]
    if not edges:
        raise ValueError("variant projected an empty graph")
    nodes_used = {graph["start_node"]}
    nodes_used.update(edge["source"] for edge in edges)
    nodes_used.update(edge["target"] for edge in edges)
    terminal_nodes = [node_id for node_id in graph["terminal_nodes"] if node_id in nodes_used]
    if len(terminal_nodes) < 2:
        raise ValueError("variant must retain at least two reachable terminal nodes")
    return {
        **graph,
        "terminal_nodes": terminal_nodes,
        "nodes": [node for node in graph["nodes"] if node["node_id"] in nodes_used],
        "edges": edges,
    }


def _strip_requirements(action: dict[str, Any]) -> None:
    action.pop("requires_prior_actions", None)


def _rebuild_routes(
    routes: dict[str, Any], graph: dict[str, Any], *, drop_edge_costs: bool
) -> dict[str, Any]:
    edges = {edge["edge_id"]: edge for edge in graph["edges"]}
    certificates = routes["certificates"]

    def route_actions(edge_ids: list[str]) -> list[dict[str, Any]]:
        return [copy.deepcopy(edges[edge_id]["action"]) for edge_id in edge_ids]

    rebuilt = copy.deepcopy(routes)
    safe_ids = list(certificates["safe"]["edge_ids"])
    rebuilt["safe"] = {"actions": route_actions(safe_ids)}
    rebuilt["attack"] = {
        target_id: {"actions": route_actions(list(certificate["edge_ids"]))}
        for target_id, certificate in certificates["attack"].items()
    }
    if drop_edge_costs:
        rebuilt.pop("edge_route_costs", None)
    elif "edge_route_costs" in rebuilt:
        rebuilt["edge_route_costs"] = {
            edge_id: cost
            for edge_id, cost in rebuilt["edge_route_costs"].items()
            if edge_id in edges
        }
    return rebuilt


def materialize_variant(bundle: ScenarioBundle, variant: str, destination: Path) -> None:
    source_root = bundle.root
    for path in source_root.rglob("*"):
        if path.is_file() and path.name != "graph.yaml":
            relative = path.relative_to(source_root)
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)

    graph = _read_yaml(source_root / "graph.yaml")
    retained_ids = _variant_edge_ids(bundle, variant)
    graph = _project_graph(graph, retained_ids)
    if variant == "dependencies_stripped":
        for edge in graph["edges"]:
            _strip_requirements(edge["action"])
    if variant == "authority_contrast_flattened":
        for edge in graph["edges"]:
            edge["public_route_attributes"] = {
                "exposure": "isolated",
                "authority_scope": "exact",
                "evidence_loss": "primary",
                "interaction": "direct",
            }
    _write_yaml(destination / "graph.yaml", graph)

    routes = _read_yaml(source_root / "routes.yaml")
    routes = _rebuild_routes(
        routes,
        graph,
        drop_edge_costs=variant == "authority_contrast_flattened",
    )
    _write_yaml(destination / "routes.yaml", routes)

    metadata = _read_yaml(source_root / "scenario.yaml")
    source_id = str(metadata["scenario_id"])
    metadata["scenario_id"] = f"ablation_{variant}_{source_id}"
    metadata["title"] = f"{metadata['title']} ({variant} diagnostic variant)"
    _write_yaml(destination / "scenario.yaml", metadata)

    task = _read_yaml(source_root / "task.yaml")
    task["tools"] = sorted({edge["action"]["tool"] for edge in graph["edges"]})
    _write_yaml(destination / "task.yaml", task)


def _audit_variant(path: Path) -> dict[str, Any]:
    try:
        bundle = load_scenario(path)
        result = audit_candidate_graph(bundle)
        return {
            "status": "valid",
            "scenario_id": bundle.definition.metadata.scenario_id,
            "edge_count": len(bundle.definition.graph.edges) if bundle.definition.graph else 0,
            "terminal_paths": result.total_terminal_paths,
            "functional_paths": result.functional_paths,
            "attack_paths": result.attack_paths,
            "compliant_functional_paths": result.compliant_functional_paths,
        }
    except Exception as error:  # noqa: BLE001 - report deterministic gate failures
        return {
            "status": "invalid",
            "scenario_id": path.name,
            "error_type": type(error).__name__,
            "error": str(error),
        }


def prepare(
    *,
    scenario_root: Path,
    output_root: Path,
    variants: tuple[str, ...],
    per_cell: int,
    seed: int,
    materialize: bool,
) -> dict[str, Any]:
    source_paths = sorted(path.parent for path in scenario_root.rglob("scenario.yaml"))
    source_bundles = tuple(load_scenario(path) for path in source_paths)
    selected = select_balanced(source_bundles, per_cell=per_cell, seed=seed)
    selected_ids = [bundle.definition.metadata.scenario_id for bundle in selected]
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "routebench_component_ablation_plan",
        "source_root": str(scenario_root.relative_to(ROOT)),
        "source_scenario_count": len(source_bundles),
        "selected_case_count": len(selected),
        "selection": {
            "seed": seed,
            "stratification": "primary_effect_family x route_length",
            "per_cell": per_cell,
            "scenario_ids_sha256": hashlib.sha256("\n".join(selected_ids).encode()).hexdigest(),
        },
        "variants": {},
        "status": "planned",
    }
    for variant in variants:
        if variant not in VARIANTS:
            raise ValueError(f"unknown variant {variant}; choose from {VARIANTS}")
        variant_root = output_root / variant
        rows: list[dict[str, Any]] = []
        for bundle in selected:
            destination = variant_root / bundle.definition.metadata.scenario_id
            if materialize:
                materialize_variant(bundle, variant, destination)
                row = _audit_variant(destination)
            else:
                row = {
                    "status": "not_materialized",
                    "scenario_id": bundle.definition.metadata.scenario_id,
                    "retained_edges": len(_variant_edge_ids(bundle, variant)),
                }
            rows.append(row)
        manifest["variants"][variant] = {
            "scenario_count": len(rows),
            "rows": rows,
            "materialized_root": str(variant_root.relative_to(ROOT)) if materialize else None,
        }
    if materialize:
        manifest["status"] = "valid" if all(
            row["status"] == "valid"
            for variant in manifest["variants"].values()
            for row in variant["rows"]
        ) else "invalid"
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-root", type=Path, default=DEFAULT_SCENARIO_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--per-cell", type=int, default=DEFAULT_PER_CELL)
    parser.add_argument("--seed", type=int, default=DEFAULT_SELECTION_SEED)
    parser.add_argument(
        "--variant", action="append", choices=VARIANTS, dest="variants", help="repeatable"
    )
    parser.add_argument(
        "--materialize",
        action="store_true",
        help="write scenario variants under output-root and audit each one",
    )
    args = parser.parse_args()
    variants = tuple(args.variants or VARIANTS)
    manifest = prepare(
        scenario_root=args.scenario_root.resolve(),
        output_root=args.output_root.resolve(),
        variants=variants,
        per_cell=args.per_cell,
        seed=args.seed,
        materialize=args.materialize,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if manifest["status"] == "invalid":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
