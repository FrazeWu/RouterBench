from __future__ import annotations

import pytest

from routebench.runtime.reference import (
    ScenarioState,
    TrustedToolExecutor,
    UnsatisfiedPriorActionRequirementError,
)
from routebench.scenarios.schema import RouteActionSpec


def _state() -> ScenarioState:
    return ScenarioState(
        database={},
        column_labels={},
        files={},
        file_labels={},
        secrets={},
        environment={},
        cloud={},
    )


def test_route_action_requires_matching_prior_action() -> None:
    state = _state()
    executor = TrustedToolExecutor()
    dependent = RouteActionSpec(
        tool="file.write",
        arguments={"path": "/workspace/out.json", "content": {}},
        requires_prior_actions=(
            {"tool": "file.read", "arguments": {"path": "/workspace/in.json"}},
        ),
    )
    with pytest.raises(UnsatisfiedPriorActionRequirementError):
        executor.require_prior_actions(dependent, state)
    state.executed_actions.append(("file.read", {"path": "/workspace/in.json"}))
    executor.require_prior_actions(dependent, state)


def test_route_action_requirement_matches_argument_subset() -> None:
    state = _state()
    state.executed_actions.append(("artifact.read", {"name": "build", "fields": ["digest"]}))
    action = RouteActionSpec(
        tool="file.write",
        arguments={"path": "/workspace/out.json", "content": {}},
        requires_prior_actions=({"tool": "artifact.read", "arguments": {"name": "build"}},),
    )
    TrustedToolExecutor().require_prior_actions(action, state)
