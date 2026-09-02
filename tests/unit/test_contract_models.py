from __future__ import annotations

import pytest
from pydantic import ValidationError

from routebench.contracts import (
    ActionRequest,
    AttackProgram,
    AttackStep,
    Decision,
    DecisionKind,
)


def test_action_hash_is_stable_for_equivalent_argument_order() -> None:
    first = ActionRequest(
        action_id="a-1",
        step=0,
        tool="file.write",
        arguments={"path": "/workspace/a", "content": "value"},
    )
    second = ActionRequest(
        action_id="a-1",
        step=0,
        tool="file.write",
        arguments={"content": "value", "path": "/workspace/a"},
    )

    assert first.action_hash == second.action_hash


def test_action_arguments_are_deeply_immutable() -> None:
    action = ActionRequest(
        action_id="a-1",
        step=0,
        tool="file.write",
        arguments={"options": {"overwrite": False}, "lines": ["one", "two"]},
    )
    original_hash = action.action_hash

    with pytest.raises(TypeError, match="immutable"):
        action.arguments["path"] = "/workspace/changed"

    options = action.arguments["options"]
    assert isinstance(options, dict)
    with pytest.raises(TypeError, match="immutable"):
        options["overwrite"] = True

    lines = action.arguments["lines"]
    assert isinstance(lines, list)
    with pytest.raises(TypeError, match="immutable"):
        lines.append("three")

    assert action.action_hash == original_hash


def test_reroute_requires_a_replacement_action() -> None:
    action = ActionRequest(action_id="a-1", step=0, tool="file.read")

    with pytest.raises(ValidationError, match="require a replacement"):
        Decision(action_hash=action.action_hash, kind=DecisionKind.REROUTE)


def test_non_reroute_rejects_a_replacement_action() -> None:
    action = ActionRequest(action_id="a-1", step=0, tool="file.read")

    with pytest.raises(ValidationError, match="only reroute"):
        Decision(
            action_hash=action.action_hash,
            kind=DecisionKind.ALLOW,
            replacement=action,
        )


def test_attack_program_rejects_unknown_step_references() -> None:
    with pytest.raises(ValidationError, match="unknown steps"):
        AttackProgram(
            goal="alter the database",
            committed_at_step=0,
            steps=(
                AttackStep(
                    step_id="delete",
                    primitive="database.delete",
                    target="customers",
                    prerequisites=("missing",),
                ),
            ),
        )
