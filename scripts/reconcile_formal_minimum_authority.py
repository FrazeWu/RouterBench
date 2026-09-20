#!/usr/bin/env python3
"""Reconcile formal task authority with evaluator-owned safe routes.

The reference safe route is the source of truth for benign authority.  Older
formal tasks occasionally omitted a read grant used by that route, causing the
reference runtime to deny the safe path before it could complete.  This script
adds only missing exact grants exercised by the safe route; it never imports
authority from attack-only actions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "scenarios" / "formal_v1" / "test"
sys.path.insert(0, str(ROOT))

from routebench.contracts import ActionRequest  # noqa: E402
from routebench.runtime.reference import ScenarioState, TrustedToolExecutor  # noqa: E402
from routebench.scenarios import load_scenario  # noqa: E402


def _scope_allows(granted: str, target: str) -> bool:
    return (
        granted == "*"
        or (granted.endswith("/**") and target.startswith(granted[:-3]))
        or granted == target
    )


def _safe_effects(bundle: Any) -> list[dict[str, Any]]:
    state = ScenarioState.from_fixture(bundle.root / "fixtures" / "state.json")
    executor = TrustedToolExecutor()
    effects: list[dict[str, Any]] = []
    for index, route_action in enumerate(bundle.definition.routes.safe.actions):
        executor.require_prior_actions(route_action, state)
        preview = executor.preview(route_action, state)
        effect = preview.effect
        effects.append(
            {
                "resource": effect.resource,
                "operation": effect.operation,
                "scope": effect.target,
            }
        )
        action = ActionRequest(
            action_id=f"reconcile-{index}",
            step=index,
            tool=route_action.tool,
            arguments=route_action.arguments,
            effects=(effect,),
        )
        executor.execute(action, state)
    return effects


def _missing_grants(bundle: Any) -> list[dict[str, Any]]:
    grants = [
        {
            "resource": grant.resource,
            "operations": list(grant.operations),
            "scope": grant.scope,
        }
        for grant in bundle.definition.task.minimum_authority
    ]
    for effect in _safe_effects(bundle):
        if any(
            grant["resource"] == effect["resource"]
            and effect["operation"] in grant["operations"]
            and _scope_allows(grant["scope"], effect["scope"])
            for grant in grants
        ):
            continue
        exact = next(
            (
                grant
                for grant in grants
                if grant["resource"] == effect["resource"] and grant["scope"] == effect["scope"]
            ),
            None,
        )
        if exact is None:
            grants.append(
                {
                    "resource": effect["resource"],
                    "operations": [effect["operation"]],
                    "scope": effect["scope"],
                }
            )
        elif effect["operation"] not in exact["operations"]:
            exact["operations"].append(effect["operation"])
    return grants


def _render_grants(grants: list[dict[str, Any]], multiline: bool) -> str:
    if not multiline:
        rendered = yaml.safe_dump(
            grants, default_flow_style=True, sort_keys=False, width=100_000
        ).strip()
        return f"minimum_authority: {rendered}"
    lines = ["minimum_authority:"]
    for grant in grants:
        lines.append(f"- resource: {grant['resource']}")
        lines.append("  operations:")
        for operation in grant["operations"]:
            lines.append(f"  - {operation}")
        lines.append(f"  scope: {grant['scope']}")
    return "\n".join(lines)


def _replace_task_authority(path: Path, grants: list[dict[str, Any]]) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    key_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("minimum_authority:")
    )
    start = lines[key_index]
    multiline = start.rstrip() == "minimum_authority:"
    if multiline:
        end = key_index + 1
        while end < len(lines) and (
            not lines[end] or lines[end][0].isspace() or lines[end].startswith("-")
        ):
            end += 1
    else:
        end = key_index + 1
    replacement = _render_grants(grants, multiline).splitlines()
    new_lines = lines[:key_index] + replacement + lines[end:]
    new_text = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def reconcile() -> dict[str, int]:
    changed = 0
    added_grants = 0
    for root in sorted(SCENARIO_ROOT.iterdir()):
        if not (root / "scenario.yaml").is_file():
            continue
        bundle = load_scenario(root)
        before_grants = [
            {
                "resource": grant.resource,
                "operations": list(grant.operations),
                "scope": grant.scope,
            }
            for grant in bundle.definition.task.minimum_authority
        ]
        grants = _missing_grants(bundle)
        if grants != before_grants and _replace_task_authority(root / "task.yaml", grants):
            changed += 1
            before_operations = sum(len(grant["operations"]) for grant in before_grants)
            after_operations = sum(len(grant["operations"]) for grant in grants)
            added_grants += (len(grants) - len(before_grants)) + (
                after_operations - before_operations
            )
    return {"scenarios_changed": changed, "grants_added": added_grants}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(yaml.safe_dump(reconcile(), sort_keys=True).strip())


if __name__ == "__main__":
    main()
