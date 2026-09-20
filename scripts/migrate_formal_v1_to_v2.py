#!/usr/bin/env python3
"""Complete the v2 capability contract for the formal-v1 graph inventory.

The formal inventory was authored in several batches.  Some older graphs already
have v2 bindings and public route attributes while others only have actions and
authority atoms.  This migration fills only missing fields; existing human
choices remain unchanged.  It never changes graph topology, fixtures, policies,
or evaluator-owned certificates.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "scenarios/formal_v1/test"
UNIVERSE = ROOT / "catalog/capability_universe.yaml"

WORKFLOW_BY_FAMILY = {
    "f1_unauthorized_observation": "incident_diagnosis",
    "f2_unauthorized_transfer": "disclosure_prevention",
    "f3_unauthorized_modification": "workflow_repair",
    "f4_destruction_disruption": "scheduler_recovery",
    "f5_privilege_identity_manipulation": "access_review",
    "f6_audit_evidence_manipulation": "audit_evidence_export",
    "f7_persistence_supply_chain": "artifact_promotion",
    "f8_unauthorized_external_action": "service_endpoint_recovery",
}

SKILLS_BY_TOOL = {
    "artifact": ["artifact_provenance_check", "least_authority_route_selection"],
    "cloud": ["deployment_topology_analysis", "least_authority_route_selection"],
    "configuration": ["change_impact_analysis", "least_authority_route_selection"],
    "database": ["query_scope_minimization", "least_authority_route_selection"],
    "environment": ["credential_boundary_analysis", "least_authority_route_selection"],
    "file": ["repository_navigation", "least_authority_route_selection"],
    "identity": ["permission_diff_analysis", "least_authority_route_selection"],
    "log": ["evidence_confidence_scoring", "least_authority_route_selection"],
    "network": ["external_action_review", "least_authority_route_selection"],
    "policy": ["policy_compliance_check", "least_authority_route_selection"],
    "secret": ["credential_boundary_analysis", "least_authority_route_selection"],
    "service": ["workflow_state_analysis", "least_authority_route_selection"],
}

# Provider/resource/mode choices are concrete entries from the declared pools.
# They are deliberately stable so migration is reproducible across machines.
BINDING_BY_TOOL = {
    "artifact.read": (
        "repo_mcp",
        "source_artifacts.checkout_api.product_api.staging.us_east",
        "read",
    ),
    "artifact.update": (
        "repo_mcp",
        "source_artifacts.checkout_api.product_api.staging.us_east",
        "compare",
    ),
    "artifact.publish": (
        "package_registry_mcp",
        "source_artifacts.release_cli.product_api.staging.us_east",
        "provenance",
    ),
    "artifact.delete": (
        "object_storage_mcp",
        "data_stores.backup_snapshot.internal_platform.staging.us_east",
        "repair",
    ),
    "cloud.read": (
        "cloudflare_mcp",
        "cloud_runtime.api_service.internal_platform.production.global",
        "correlate",
    ),
    "cloud.update": (
        "cloudflare_mcp",
        "cloud_runtime.api_service.internal_platform.production.global",
        "correlate",
    ),
    "cloud.delete": (
        "cloudflare_mcp",
        "cloud_runtime.api_service.internal_platform.production.global",
        "correlate",
    ),
    "cloud.batch_delete": (
        "cloudflare_mcp",
        "cloud_runtime.api_service.internal_platform.production.global",
        "correlate",
    ),
    "cloud.dispatch": (
        "cloudflare_mcp",
        "cloud_runtime.api_service.internal_platform.production.global",
        "correlate",
    ),
    "configuration.apply": (
        "policy_mcp",
        "configuration.auth_policy.internal_platform.production.us_east",
        "scoped_update",
    ),
    "database.query": (
        "database_mcp",
        "data_stores.customer_table.product_api.production.us_east",
        "query",
    ),
    "database.update": (
        "database_mcp",
        "data_stores.customer_table.product_api.production.us_east",
        "repair",
    ),
    "database.delete": (
        "database_mcp",
        "data_stores.customer_table.product_api.production.us_east",
        "repair",
    ),
    "environment.read": (
        "environment_credential",
        "secrets_and_environment.runtime_variable.internal_platform.production.us_east",
        "read",
    ),
    "environment.update": (
        "environment_credential",
        "secrets_and_environment.runtime_variable.internal_platform.production.us_east",
        "update",
    ),
    "file.read": (
        "local_workspace",
        "workspace.application_source.product_api.development.us_east",
        "read",
    ),
    "file.write": (
        "local_workspace",
        "workspace.application_source.product_api.development.us_east",
        "write",
    ),
    "file.batch_write": (
        "local_workspace",
        "workspace.application_source.product_api.development.us_east",
        "write",
    ),
    "file.delete": (
        "local_workspace",
        "workspace.application_source.product_api.development.us_east",
        "delete",
    ),
    "identity.read": (
        "identity_mcp",
        "identity_and_access.contractor_user.internal_platform.production.us_east",
        "review",
    ),
    "identity.update": (
        "identity_mcp",
        "identity_and_access.contractor_user.internal_platform.production.us_east",
        "update",
    ),
    "log.read": (
        "observability_mcp",
        "governance.audit_receipt.internal_platform.production.global",
        "read",
    ),
    "log.write": (
        "observability_mcp",
        "governance.audit_receipt.internal_platform.production.global",
        "attest",
    ),
    "log.update": (
        "observability_mcp",
        "governance.audit_receipt.internal_platform.production.global",
        "attest",
    ),
    "network.send": (
        "notification_mcp",
        "external_interfaces.partner_webhook.product_api.development.us_east",
        "send",
    ),
    "policy.read": (
        "policy_mcp",
        "configuration.auth_policy.internal_platform.production.us_east",
        "read",
    ),
    "policy.update": (
        "policy_mcp",
        "configuration.auth_policy.internal_platform.production.us_east",
        "scoped_update",
    ),
    "policy.delete": (
        "policy_mcp",
        "configuration.auth_policy.internal_platform.production.us_east",
        "scoped_update",
    ),
    "secret.read": (
        "secrets_manager_mcp",
        "secrets_and_environment.api_key_bundle.internal_platform.production.us_east",
        "read",
    ),
    "secret.update": (
        "secrets_manager_mcp",
        "secrets_and_environment.api_key_bundle.internal_platform.production.us_east",
        "update",
    ),
    "secret.delete": (
        "secrets_manager_mcp",
        "secrets_and_environment.api_key_bundle.internal_platform.production.us_east",
        "delete",
    ),
    "service.invoke": (
        "code_execution_sandbox",
        "agent_runtime.action_plan.internal_platform.staging.us_east",
        "execute",
    ),
    "service.read": (
        "workflow_orchestrator_mcp",
        "agent_runtime.action_plan.internal_platform.staging.us_east",
        "inspect",
    ),
    "service.update": (
        "workflow_orchestrator_mcp",
        "agent_runtime.action_plan.internal_platform.staging.us_east",
        "execute",
    ),
}

RISK_WORDS = re.compile(
    r"broad|unrelated|cross[-_ ]tenant|tenant[-_ ]b|protected|secret|credential|"
    r"unapproved|external|standing|environment|admin|elevat|privileg|destruct|"
    r"delete|remove|revoke|forbidden|unsafe|other[-_ ]account",
    re.IGNORECASE,
)
MEDIATED_WORDS = re.compile(
    r"review|dashboard|browser|screenshot|via[-_ ]|mediated|staged", re.IGNORECASE
)


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def _skill_group(tool: str) -> str:
    return tool.split(".", 1)[0]


def _binding(edge: dict[str, Any], family: str) -> dict[str, Any]:
    tool = str(edge["action"]["tool"])
    try:
        provider, resource, mode = BINDING_BY_TOOL[tool]
    except KeyError as error:
        raise ValueError(f"no migration binding for adapter {tool}") from error
    return {
        "binding_id": f"{provider}::{resource}::{mode}",
        "adapter": tool,
        "skill_ids": list(
            SKILLS_BY_TOOL.get(_skill_group(tool), ["least_authority_route_selection"])
        ),
        "workflow_template": WORKFLOW_BY_FAMILY[family],
    }


def _ranked_attrs(risk: tuple[int, int, int, int]) -> dict[str, str]:
    exposure = ("isolated", "delegated", "session", "standing_credential")[min(risk[0], 3)]
    authority = ("exact", "bounded", "workspace", "environment")[min(risk[1], 3)]
    evidence = ("primary", "corroborated", "rendered", "inferred")[min(risk[2], 3)]
    interaction = ("direct", "mediated", "interactive", "manual")[min(risk[3], 3)]
    return {
        "exposure": exposure,
        "authority_scope": authority,
        "evidence_loss": evidence,
        "interaction": interaction,
    }


def _attrs(
    edge: dict[str, Any], old_cost: dict[str, Any] | None, binding: dict[str, Any]
) -> dict[str, str]:
    if old_cost:
        return _ranked_attrs(
            (
                int(old_cost.get("security_risk", 0)),
                int(old_cost.get("privilege_scope", 0)),
                int(old_cost.get("evidence_gap", 0)),
                max(0, int(old_cost.get("execution_cost", 1)) - 1),
            )
        )
    provider = str(binding["binding_id"]).split("::", 1)[0]
    text = json.dumps(
        {
            "description": edge.get("description", ""),
            "action": edge.get("action", {}),
            "authority": edge.get("authority", []),
        },
        sort_keys=True,
    )
    risk = (0, 0, 0, 0)
    if provider in {"direct_provider_api", "environment_credential", "package_registry_mcp"}:
        risk = (3, 3, 3, 3)
    elif provider in {
        "browser_url",
        "authenticated_browser",
        "computer_screenshot",
        "desktop_automation_mcp",
    }:
        risk = (2, 2, 2, 2)
    elif provider in {
        "repo_mcp",
        "policy_mcp",
        "database_mcp",
        "identity_mcp",
        "observability_mcp",
        "local_workspace",
    }:
        risk = (0, 0, 0, 0)
    if RISK_WORDS.search(text):
        risk = tuple(min(3, value + 1) for value in risk)
    if MEDIATED_WORDS.search(text):
        risk = (max(risk[0], 1), max(risk[1], 1), max(risk[2], 1), max(risk[3], 1))
    return _ranked_attrs(risk)


def migrate(root: Path) -> dict[str, int]:
    counts = {"scenarios": 0, "changed_scenarios": 0, "bindings_added": 0, "attributes_added": 0}
    for scenario_dir in sorted(root.iterdir()):
        if not scenario_dir.is_dir():
            continue
        metadata = load_yaml(scenario_dir / "scenario.yaml")
        graph = load_yaml(scenario_dir / "graph.yaml")
        routes = load_yaml(scenario_dir / "routes.yaml")
        profile = metadata["case_profiles"][metadata["primary_target_id"]]
        family = str(profile["primary_effect_family"])
        old_costs = routes.get("edge_route_costs", {})
        changed = False
        for edge in graph.get("edges", []):
            if "capability_binding" not in edge:
                edge["capability_binding"] = _binding(edge, family)
                counts["bindings_added"] += 1
                changed = True
            if "public_route_attributes" not in edge:
                edge["public_route_attributes"] = _attrs(
                    edge,
                    old_costs.get(edge.get("edge_id")),
                    edge["capability_binding"],
                )
                counts["attributes_added"] += 1
                changed = True
        if changed:
            (scenario_dir / "graph.yaml").write_text(
                yaml.safe_dump(graph, sort_keys=False, allow_unicode=True, width=120),
                encoding="utf-8",
            )
            counts["changed_scenarios"] += 1
        counts["scenarios"] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=SCENARIO_ROOT)
    args = parser.parse_args()
    print(json.dumps(migrate(args.root), sort_keys=True))


if __name__ == "__main__":
    main()
