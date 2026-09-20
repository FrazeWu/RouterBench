#!/usr/bin/env python3
"""Audit and freeze the 776-case formal schema-v4 inventory.

The audit is deterministic and does not invoke a model.  It validates the v2
capability-binding/public-route contract, then checks the evaluator-owned safe
and forbidden path certificates with the trusted graph simulator.  The freeze
manifest contains only provenance and aggregate metrics; prompts, fixtures,
routes, and certificates remain outside the public manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routebench.runtime.graph import audit_candidate_graph  # noqa: E402
from routebench.scenarios import load_scenario  # noqa: E402
from scripts.validate_capability_universe import (  # noqa: E402
    load_catalog,
    validate_binding_selection,
)

SCENARIO_ROOT = ROOT / "scenarios" / "formal_v1" / "test"
CATALOG_PATH = ROOT / "catalog" / "capability_universe.yaml"
DEFAULT_OUTPUT = ROOT / "configs" / "benchmark" / "formal-v2-freeze.json"


def _catalog_digest() -> str:
    return hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()


def _audit_one(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    bundle = load_scenario(path)
    metadata = bundle.definition.metadata
    graph = bundle.definition.graph
    if metadata.schema_version != 4:
        raise ValueError(
            f"{metadata.scenario_id} is schema v{metadata.schema_version}, expected v4"
        )
    if metadata.split.value != "test":
        raise ValueError(f"{metadata.scenario_id} is not in the held-out test split")
    if graph is None:
        raise ValueError(f"{metadata.scenario_id} has no candidate graph")

    catalog = load_catalog(CATALOG_PATH)
    edge_count = 0
    for edge in graph.edges:
        edge_count += 1
        binding = edge.capability_binding
        if binding is None:
            raise ValueError(f"{metadata.scenario_id}:{edge.edge_id} has no capability binding")
        binding_payload = binding.model_dump()
        binding_payload["skill_ids"] = list(binding_payload["skill_ids"])
        validate_binding_selection(catalog, binding_payload, require_runtime=False)
        if edge.public_route_attributes is None:
            raise ValueError(
                f"{metadata.scenario_id}:{edge.edge_id} has no public route attributes"
            )

    result = audit_candidate_graph(bundle)
    certificates = bundle.definition.routes.certificates
    assert certificates is not None
    return {
        "scenario_id": metadata.scenario_id,
        "digest": bundle.digest,
        "edge_count": edge_count,
        "terminal_paths": result.total_terminal_paths,
        "functional_paths": result.functional_paths,
        "compliant_functional_paths": result.compliant_functional_paths,
        "attack_paths": result.attack_paths,
        "safe_certificate_verified": True,
        "attack_certificates_verified": len(certificates.attack),
        "public_exact_optimum_unique": result.observable_optimum.public_rule_unique,
        "public_candidate_count": result.observable_optimum.public_candidate_count,
        "public_ambiguity": result.observable_optimum.ambiguity_kind,
    }


def _scenario_set_digest(rows: list[dict[str, Any]]) -> str:
    payload = "\n".join(f"{row['scenario_id']}:{row['digest']}" for row in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit(workers: int) -> dict[str, Any]:
    paths = sorted(path for path in SCENARIO_ROOT.iterdir() if (path / "scenario.yaml").is_file())
    if workers <= 1:
        rows = [_audit_one(str(path)) for path in paths]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_audit_one, (str(path) for path in paths)))
    rows.sort(key=lambda row: row["scenario_id"])
    if len(rows) != 776:
        raise ValueError(f"expected 776 formal scenarios, found {len(rows)}")

    edge_count = sum(row["edge_count"] for row in rows)
    public_unique = sum(row["public_exact_optimum_unique"] for row in rows)
    ambiguity_counts: dict[str, int] = {}
    for row in rows:
        key = row["public_ambiguity"]
        ambiguity_counts[key] = ambiguity_counts.get(key, 0) + 1
    return {
        "schema_version": 1,
        "kind": "routebench_formal_v2_freeze",
        "protocol_revision": 2,
        "scenario_root": str(SCENARIO_ROOT.relative_to(ROOT)),
        "scenario_count": len(rows),
        "edge_count": edge_count,
        "catalog_sha256": _catalog_digest(),
        "scenario_set_digest": _scenario_set_digest(rows),
        "binding_contract": {
            "version": "v2",
            "validated_edges": edge_count,
            "modeled_providers_allowed": True,
        },
        "graph_audit": {
            "scenarios_valid": len(rows),
            "safe_certificates_verified": sum(row["safe_certificate_verified"] for row in rows),
            "attack_certificates_verified": sum(
                row["attack_certificates_verified"] for row in rows
            ),
            "public_exact_optimum_unique": public_unique,
            "public_tie_policy_cases": len(rows) - public_unique,
            "public_ambiguity": dict(sorted(ambiguity_counts.items())),
            "min_terminal_paths": min(row["terminal_paths"] for row in rows),
            "max_terminal_paths": max(row["terminal_paths"] for row in rows),
        },
        "scenario_digests": {row["scenario_id"]: row["digest"] for row in rows},
        "status": "valid",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = audit(max(1, args.workers))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in payload.items() if key != "scenario_digests"},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
