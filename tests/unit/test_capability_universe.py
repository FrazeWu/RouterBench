from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "validate_capability_universe.py"
BATCH_PATH = (
    Path(__file__).resolve().parents[2]
    / "catalog"
    / "capability_routing_calibration_batch_v1.yaml"
)
SPEC = importlib.util.spec_from_file_location("validate_capability_universe", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_capability_universe_is_internally_consistent() -> None:
    catalog = MODULE.load_catalog(MODULE.DEFAULT_CATALOG)

    summary = MODULE.validate(catalog, MODULE.DEFAULT_CATALOG.parents[1])

    assert summary["status"] == "valid"
    assert summary["runtime_supported_providers"] == 36
    assert summary["modeled_only_providers"] == 19
    assert summary["materialized_resource_instances"] == 5_184
    assert summary["materialized_provider_resource_mode_bindings"] == 55_296


def test_binding_pool_materializes_a_concrete_author_choice() -> None:
    catalog = MODULE.load_catalog(MODULE.DEFAULT_CATALOG)

    first_binding = next(MODULE.pool_bindings(catalog, "configuration_change"))
    resource_count = sum(1 for _ in MODULE.resource_instances(catalog))

    assert first_binding == (
        "policy_mcp::configuration.request_timeout.product_api.development.us_east::read"
    )
    assert resource_count == 5_184


def test_binding_selection_rejects_a_provider_adapter_mismatch() -> None:
    catalog = MODULE.load_catalog(MODULE.DEFAULT_CATALOG)
    selection = {
        "binding_id": (
            "repo_mcp::source_artifacts.checkout_api.product_api.development.us_east::read"
        ),
        "adapter": "cloud.read",
        "skill_ids": ["repository_navigation"],
        "workflow_template": "production_bugfix",
    }

    with pytest.raises(ValueError, match="does not support adapter"):
        MODULE.validate_binding_selection(catalog, selection)


def test_manual_calibration_batch_has_valid_concrete_capability_choices() -> None:
    catalog = MODULE.load_catalog(MODULE.DEFAULT_CATALOG)

    summary = MODULE.validate_batch_design(catalog, BATCH_PATH)

    assert summary == {"cases": 20, "manual_binding_choices": 240, "status": "valid"}
