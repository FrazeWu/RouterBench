#!/usr/bin/env python3
"""Validate and materialize the manually curated capability-routing universe.

This intentionally does not create scenarios.  It only makes the finite choices
available to human benchmark authors explicit and validates their references.
"""

import argparse
import itertools
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "catalog" / "capability_universe.yaml"


def load_catalog(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("catalog root must be a mapping")
    return raw


def flatten_providers(groups: dict[str, list[str]]) -> set[str]:
    return {provider for values in groups.values() for provider in values}


def primitive_adapters(catalog: dict[str, Any], root: Path) -> set[str]:
    primitive_path = root / "catalog" / str(catalog["primitive_catalog"])
    with primitive_path.open(encoding="utf-8") as handle:
        primitive = yaml.safe_load(handle)
    return {
        adapter
        for family in primitive["execution_tool_families"].values()
        for adapter in family["tools"]
    }


def resource_instances(catalog: dict[str, Any]) -> Iterator[str]:
    dimensions = catalog["instance_dimensions"]
    for family, templates in catalog["resource_instance_templates"].items():
        for template, scope, environment, region in itertools.product(
            templates,
            dimensions["scope"],
            dimensions["environment"],
            dimensions["region"],
        ):
            yield ".".join((family, template, scope, environment, region))


def pool_bindings(catalog: dict[str, Any], pool_name: str) -> Iterator[str]:
    pool = catalog["capability_binding_pools"].get(pool_name)
    if pool is None:
        available = ", ".join(sorted(catalog["capability_binding_pools"]))
        raise ValueError(f"unknown pool {pool_name!r}; choose one of: {available}")
    instances = (
        instance
        for instance in resource_instances(catalog)
        if instance.startswith(f"{pool['resources']}.")
    )
    for provider, instance, mode in itertools.product(pool["providers"], instances, pool["modes"]):
        yield "::".join((provider, instance, mode))


def validate_binding_selection(
    catalog: dict[str, Any], selection: dict[str, Any], *, require_runtime: bool = True
) -> None:
    """Validate one manually authored provider/resource/mode/adapter selection."""

    required = set(catalog["binding_selection_contract"]["required_fields"])
    if set(selection) != required:
        raise ValueError(
            "capability binding fields mismatch: "
            f"missing={sorted(required - set(selection))}, "
            f"extra={sorted(set(selection) - required)}"
        )
    binding_id = selection["binding_id"]
    if not isinstance(binding_id, str) or len(binding_id.split("::")) != 3:
        raise ValueError("capability binding_id must contain provider, resource, and mode")
    provider, resource, mode = binding_id.split("::")
    profile = catalog["provider_profiles"].get(provider)
    if profile is None:
        raise ValueError(f"capability binding uses unknown provider: {provider}")
    matching_pools = [
        (name, pool)
        for name, pool in catalog["capability_binding_pools"].items()
        if provider in pool["providers"] and resource.startswith(f"{pool['resources']}.")
    ]
    if not matching_pools or all(mode not in pool["modes"] for _, pool in matching_pools):
        raise ValueError("capability binding is not materialized by a declared pool")
    if resource not in set(resource_instances(catalog)):
        raise ValueError("capability binding uses an unknown concrete resource instance")
    adapter = selection["adapter"]
    if adapter not in profile["adapters"]:
        raise ValueError(f"provider {provider} does not support adapter {adapter}")
    if require_runtime and profile["execution_status"] != "runtime_supported":
        raise ValueError(f"provider {provider} is not runtime_supported")
    known_skills = {
        skill for skills in catalog["planning_skills"].values() for skill in skills
    }
    skill_ids = selection["skill_ids"]
    if not isinstance(skill_ids, list) or not skill_ids or not set(skill_ids) <= known_skills:
        raise ValueError("capability binding uses unknown or empty planning skills")
    known_workflows = {
        workflow
        for workflows in catalog["workflow_templates"].values()
        for workflow in workflows
    }
    if selection["workflow_template"] not in known_workflows:
        raise ValueError("capability binding uses an unknown workflow template")


def validate_graph_bindings(catalog: dict[str, Any], graph_path: Path) -> dict[str, int | str]:
    """Require every edge in a capability-routing graph to carry a valid binding."""

    with graph_path.open(encoding="utf-8") as handle:
        graph = yaml.safe_load(handle)
    if not isinstance(graph, dict) or not isinstance(graph.get("edges"), list):
        raise ValueError("graph file must contain an edges list")
    edges = graph["edges"]
    for edge in edges:
        if not isinstance(edge, dict) or "capability_binding" not in edge:
            raise ValueError("every capability-routing graph edge requires capability_binding")
        binding = edge["capability_binding"]
        if not isinstance(binding, dict):
            raise ValueError("graph edge capability_binding must be a mapping")
        validate_binding_selection(catalog, binding)
        if binding["adapter"] != edge.get("action", {}).get("tool"):
            raise ValueError("graph edge binding adapter must match its action tool")
    return {"edges": len(edges), "status": "valid"}


def validate_batch_design(catalog: dict[str, Any], batch_path: Path) -> dict[str, int | str]:
    """Validate the frozen manual choices for one capability-routing authoring batch."""

    with batch_path.open(encoding="utf-8") as handle:
        batch = yaml.safe_load(handle)
    if not isinstance(batch, dict) or not isinstance(batch.get("cases"), list):
        raise ValueError("batch design must contain a cases list")
    cases = batch["cases"]
    if len(cases) != batch.get("target_cases"):
        raise ValueError("batch case count does not match target_cases")
    case_ids = [case.get("case_id") for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("batch case IDs must be unique")
    strategies = batch.get("provider_strategies")
    if not isinstance(strategies, dict):
        raise ValueError("batch design must declare provider_strategies")
    known_families = {f"f{index}_" for index in range(1, 9)}
    selected_bindings = 0
    for case in cases:
        workflow = case.get("workflow_template")
        skills = case.get("planning_skills")
        dependencies = case.get("dependencies")
        sequence = case.get("capability_sequence")
        capability_sets = case.get("capability_sets")
        if not isinstance(skills, list) or len(set(skills)) < batch[
            "minimum_planning_skills_per_case"
        ]:
            raise ValueError(f"{case['case_id']} has too few planning skills")
        if not isinstance(dependencies, list) or len(dependencies) < batch[
            "minimum_dependencies_per_case"
        ]:
            raise ValueError(f"{case['case_id']} has too few dependencies")
        if not isinstance(sequence, list) or len(sequence) != len(dependencies):
            raise ValueError(f"{case['case_id']} capability sequence must match dependencies")
        if not isinstance(capability_sets, dict):
            raise ValueError(f"{case['case_id']} has no capability sets")
        if not set(sequence) <= set(capability_sets):
            raise ValueError(f"{case['case_id']} capability sequence has unknown set names")
        resource_families: set[str] = set()
        for set_name, capability_set in capability_sets.items():
            pool_name = capability_set["pool"]
            pool = catalog["capability_binding_pools"].get(pool_name)
            if pool is None:
                raise ValueError(f"{case['case_id']}:{set_name} uses an unknown pool")
            resource = capability_set["resource"]
            resource_family = resource.split(".", maxsplit=1)[0]
            resource_families.add(resource_family)
            if resource_family != pool["resources"]:
                raise ValueError(f"{case['case_id']}:{set_name} resource family mismatches pool")
            strategy_name = capability_set["strategy"]
            choices = strategies.get(strategy_name)
            if not isinstance(choices, list) or len({item["provider"] for item in choices}) < batch[
                "minimum_provider_choices_per_milestone"
            ]:
                raise ValueError(f"{case['case_id']}:{set_name} has too few provider choices")
            for choice in choices:
                validate_binding_selection(
                    catalog,
                    {
                        "binding_id": "::".join(
                            (choice["provider"], resource, capability_set["mode"])
                        ),
                        "adapter": choice["adapter"],
                        "skill_ids": skills,
                        "workflow_template": workflow,
                    },
                )
                selected_bindings += 1
        if len(resource_families) < batch["minimum_resource_families_per_case"]:
            raise ValueError(f"{case['case_id']} has too few resource families")
        effect = case.get("effect_family")
        if not isinstance(effect, str) or not any(
            effect.startswith(prefix) for prefix in known_families
        ):
            raise ValueError(f"{case['case_id']} has an unknown effect family")
    return {
        "cases": len(cases),
        "manual_binding_choices": selected_bindings,
        "status": "valid",
    }


def validate(catalog: dict[str, Any], root: Path) -> dict[str, int | str]:
    providers = flatten_providers(catalog["providers"])
    profiles = catalog["provider_profiles"]
    if providers != set(profiles):
        missing = sorted(providers - set(profiles))
        extra = sorted(set(profiles) - providers)
        raise ValueError(f"provider profiles mismatch: missing={missing}, extra={extra}")

    adapters = primitive_adapters(catalog, root)
    for provider, profile in profiles.items():
        unsupported = set(profile["adapters"]) - adapters
        if unsupported:
            raise ValueError(f"{provider} uses unknown adapters: {sorted(unsupported)}")
        if profile["execution_status"] not in {"runtime_supported", "modeled_only"}:
            raise ValueError(f"{provider} has invalid execution_status")

    families = set(catalog["resource_instance_families"])
    templates = catalog["resource_instance_templates"]
    if families != set(templates):
        raise ValueError("resource families and resource templates must have identical keys")
    if any(not values for values in templates.values()):
        raise ValueError("every resource family needs at least one concrete template")

    pool_slots = 0
    bindings = catalog["capability_binding_pools"]
    dim_size = 1
    for values in catalog["instance_dimensions"].values():
        dim_size *= len(values)
    for pool_name, pool in bindings.items():
        unknown_providers = set(pool["providers"]) - providers
        if unknown_providers:
            raise ValueError(
                f"{pool_name} refers to unknown providers: {sorted(unknown_providers)}"
            )
        if pool["resources"] not in families:
            raise ValueError(f"{pool_name} refers to unknown resource family")
        if len(pool["modes"]) != len(set(pool["modes"])):
            raise ValueError(f"{pool_name} repeats a mode")
        expected_abstract_slots = (
            len(pool["providers"])
            * len(catalog["resource_instance_families"][pool["resources"]])
            * len(pool["modes"])
        )
        if pool["slots"] != expected_abstract_slots:
            raise ValueError(f"{pool_name} slots must equal provider x family-resource x mode")
        pool_slots += (
            len(pool["providers"])
            * len(templates[pool["resources"]])
            * dim_size
            * len(pool["modes"])
        )

    runtime_supported = sum(
        profile["execution_status"] == "runtime_supported" for profile in profiles.values()
    )
    return {
        "providers": len(providers),
        "runtime_supported_providers": runtime_supported,
        "modeled_only_providers": len(providers) - runtime_supported,
        "resource_instance_families": len(families),
        "resource_instance_templates": sum(len(values) for values in templates.values()),
        "materialized_resource_instances": sum(1 for _ in resource_instances(catalog)),
        "planning_skills": sum(len(values) for values in catalog["planning_skills"].values()),
        "workflow_templates": sum(len(values) for values in catalog["workflow_templates"].values()),
        "materialized_provider_resource_mode_bindings": pool_slots,
        "status": "valid",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--list-resources", action="store_true")
    parser.add_argument("--list-bindings", metavar="POOL_NAME")
    parser.add_argument("--validate-graph-bindings", type=Path)
    parser.add_argument("--validate-batch-design", type=Path)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    summary = validate(catalog, args.catalog.resolve().parents[1])
    if args.list_resources:
        print("\n".join(resource_instances(catalog)))
        return
    if args.list_bindings:
        print("\n".join(pool_bindings(catalog, args.list_bindings)))
        return
    if args.validate_graph_bindings:
        print(
            json.dumps(
                validate_graph_bindings(catalog, args.validate_graph_bindings), sort_keys=True
            )
        )
        return
    if args.validate_batch_design:
        print(
            json.dumps(
                validate_batch_design(catalog, args.validate_batch_design), sort_keys=True
            )
        )
        return
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
