from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from routebench.evaluation.interventions import compare_intervention, path_outcomes, snapshot
from routebench.scenarios import load_scenario
from routebench.scenarios.loader import ScenarioBundle
from routebench.scenarios.schema import PublicRouteAttributes

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/capability-routing/pilot_v2/pv2_001_public_timeout_repair"


def _flatten(bundle: ScenarioBundle) -> ScenarioBundle:
    graph = bundle.definition.graph
    assert graph is not None
    attributes = PublicRouteAttributes(
        exposure="isolated", authority_scope="exact", evidence_loss="primary", interaction="direct"
    )
    changed = graph.model_copy(
        update={
            "edges": tuple(
                edge.model_copy(update={"public_route_attributes": attributes})
                for edge in graph.edges
            )
        }
    )
    return replace(bundle, definition=bundle.definition.model_copy(update={"graph": changed}))


def test_identical_material_is_not_an_effective_intervention() -> None:
    state = snapshot(load_scenario(EXAMPLE))
    flags = compare_intervention(state, state)
    assert not flags["graph_changed"]
    assert not flags["fixed_objective_effective"]
    assert flags["exact_set_same"]
    assert flags["reference_unique"]
    assert flags["fixture_same"]


def test_flattening_detects_new_public_ties_not_just_certificate_acceptance() -> None:
    bundle = load_scenario(EXAMPLE)
    base, flat = snapshot(bundle), snapshot(_flatten(bundle))
    flags = compare_intervention(base, flat)
    assert flags["public_attributes_changed"]
    assert not flags["topology_changed"]
    assert flags["eligible_set_same"]
    assert flags["common_path_semantics_same"]
    assert flags["reference_accepted"]
    assert not flags["reference_unique"]
    assert not flags["exact_set_same"]
    assert not flags["fixed_objective_effective"]
    assert flags["variant_exact_count"] > flags["base_exact_count"]
    selected = next(iter(flat.exact - base.exact))
    assert path_outcomes(flat, selected)[0]
    assert not path_outcomes(base, selected)[0]


def test_detects_goal_change_even_if_eligible_paths_and_optimum_are_unchanged() -> None:
    bundle = load_scenario(EXAMPLE)
    changed = _flatten(bundle)
    task = changed.definition.task.model_copy(update={"prompt": "Changed goal information."})
    changed = replace(changed, definition=changed.definition.model_copy(update={"task": task}))
    flags = compare_intervention(snapshot(bundle), snapshot(changed))
    assert not flags["task_same"]
    assert not flags["fixed_objective_effective"]


def test_path_outcomes_reproduce_safe_and_attack_semantics() -> None:
    bundle = load_scenario(EXAMPLE)
    state = snapshot(bundle)
    certificates = bundle.definition.routes.certificates
    assert certificates is not None
    assert path_outcomes(state, certificates.safe.edge_ids) == (True, True, True, False)
    for certificate in certificates.attack.values():
        assert path_outcomes(state, certificate.edge_ids) == (False, True, False, True)
    with pytest.raises(KeyError):
        path_outcomes(state, ("not_a_route",))


def test_legacy_graph_is_not_silently_scored_as_public_contract() -> None:
    bundle = load_scenario(ROOT / "examples/capability-routing/bugfix_capability_routing")
    with pytest.raises(ValueError, match="public-contract"):
        snapshot(bundle)
