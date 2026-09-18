"""Regression checks for the manually authored capability-routing v2 inventory."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from routebench.scenarios import load_scenario


ROOT = Path(__file__).resolve().parents[2]
SCENARIO_ROOTS = (
    ROOT / "examples/capability-routing/pilot_v2",
    ROOT / "examples/capability-routing/large_v1",
)


def _bundles():
    return tuple(
        load_scenario(path)
        for root in SCENARIO_ROOTS
        for path in sorted(root.iterdir())
        if (path / "scenario.yaml").is_file()
    )


def _rows():
    rows = []
    for bundle in _bundles():
        metadata = bundle.definition.metadata
        profile = next(iter(metadata.case_profiles.values()))
        rows.append(
            {
                "id": metadata.scenario_id,
                "split": metadata.split.value,
                "template": metadata.template_family_id,
                "effect": profile.primary_effect_family.value,
                "digest": bundle.digest,
                "profile": profile,
            }
        )
    return rows


def test_v2_inventory_matches_balanced_split_contract():
    rows = _rows()
    assert len(rows) == 96
    assert len({row["id"] for row in rows}) == 96
    assert Counter(row["split"] for row in rows) == {"dev": 32, "test": 64}

    by_effect = defaultdict(Counter)
    for row in rows:
        by_effect[row["effect"]][row["split"]] += 1
    assert set(by_effect) == {
        "f1_unauthorized_observation",
        "f2_unauthorized_transfer",
        "f3_unauthorized_modification",
        "f4_destruction_disruption",
        "f5_privilege_identity_manipulation",
        "f6_audit_evidence_manipulation",
        "f7_persistence_supply_chain",
        "f8_unauthorized_external_action",
    }
    assert all(counts == Counter({"dev": 4, "test": 8}) for counts in by_effect.values())

    dev_templates = {row["template"] for row in rows if row["split"] == "dev"}
    test_templates = {row["template"] for row in rows if row["split"] == "test"}
    assert dev_templates.isdisjoint(test_templates)


def test_v2_pilot_freeze_and_split_manifest_are_content_addressed():
    rows = _rows()
    pilot = sorted(
        (row for row in rows if row["id"].startswith("rbv2_")),
        key=lambda row: row["id"],
    )
    freeze_path = ROOT / "configs/benchmark/v2-pilot-freeze-v2.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert freeze["protocol_revision"] == 2
    assert freeze["scenario_digests"] == {row["id"]: row["digest"] for row in pilot}
    digest_input = "\n".join(f'{row["id"]}:{row["digest"]}' for row in pilot)
    assert freeze["scenario_set_digest"] == hashlib.sha256(digest_input.encode()).hexdigest()

    split_manifest = yaml.safe_load(
        (ROOT / "configs/benchmark/v2-large-scale-split.yaml").read_text(encoding="utf-8")
    )
    manifest_ids = {
        scenario_id
        for assignment in split_manifest["assignments"]
        for scenario_id in assignment["scenario_ids"]
    }
    assert manifest_ids == {row["id"] for row in rows}
    assert split_manifest["development_test_template_family_overlap"] == []


def test_v2_materialized_inventory_is_explicitly_reconciled():
    rows = _rows()
    design = yaml.safe_load(
        (ROOT / "configs/benchmark/v2-large-scale-sample-design.yaml").read_text(
            encoding="utf-8"
        )
    )
    inventory = design["materialized_inventory"]
    assert inventory["status"] == "observed_hard_graph_subset"
    assert inventory["balanced_targets_satisfied"] is False

    fields = {
        "primary_asset_type": "primary_asset_type",
        "tool_surface": "primary_tool_surface",
        "attack_mechanism": "primary_attack_mechanism",
        "permission_dimension": "primary_permission_dimension",
        "route_topology": "primary_topology",
        "task_goal_coupling": "coupling",
        "target_composition": "target_composition",
        "optimum_route_length": "route_length",
    }
    for inventory_axis, profile_field in fields.items():
        observed = Counter(
            getattr(row["profile"], profile_field).value for row in rows
        )
        expected = inventory[inventory_axis]
        assert set(observed).issubset(expected)
        assert {key: observed.get(key, 0) for key in expected} == expected
