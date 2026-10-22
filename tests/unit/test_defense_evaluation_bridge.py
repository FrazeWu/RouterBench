from __future__ import annotations

from pathlib import Path

from routebench.defense.development import load_development_tasks
from routebench.defense.evaluation_bridge import (
    build_public_evaluation_context,
    evaluation_context_manifest,
)

ROOT = Path(__file__).parents[2]


def test_evaluation_context_reuses_graph_audit_without_private_route_data() -> None:
    task = load_development_tasks(ROOT, ROOT / "configs/defense/development-contracts.yaml")[0]
    context = build_public_evaluation_context(task.bundle)
    manifest = evaluation_context_manifest(context)

    assert context.scenario_id == task.public.contract.task_id
    assert context.total_terminal_paths == 9
    assert context.functional_paths == 4
    assert context.compliant_functional_paths == 3
    assert context.attack_paths == 3
    # Development overlays use the legacy graph contract; the bridge still
    # exports aggregate audit counts without inventing a public optimum.
    assert not context.public_optimum_available
    assert manifest["online_runtime_input"] is False
    assert manifest["hidden_evaluator_data"] is False
    assert "unique_optimal_edge_ids" not in manifest
    assert "optimal_authority_footprint" not in manifest
    assert "fixtures" not in manifest


def test_context_keeps_development_and_formal_split_visible() -> None:
    task = load_development_tasks(ROOT, ROOT / "configs/defense/development-contracts.yaml")[0]
    context = build_public_evaluation_context(task.bundle)
    assert context.split == "dev"
    assert context.semantic_family == "tf_dev_resource_inventory"
    assert context.stratification_key[0] == context.semantic_family
