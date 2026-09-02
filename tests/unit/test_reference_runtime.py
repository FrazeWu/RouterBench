from __future__ import annotations

from pathlib import Path

import pytest

from routebench.authorization import (
    NoAuthorizationController,
    PathStateAuthorizationController,
    StaticMinimumPermissionController,
)
from routebench.contracts import ActionRequest, EffectSummary, FeedbackMode
from routebench.evaluation.verifiers import evaluate_assertion
from routebench.runtime.reference import (
    InvalidRouteActionError,
    Observation,
    ScenarioState,
    TrustedToolExecutor,
    validate_route_spec,
)
from routebench.runtime.runner import ReferenceController, ReferenceRunResult, run_reference_route
from routebench.scenarios import load_scenario
from routebench.scenarios.schema import AssertionSpec, RouteActionSpec, RouteSpec

PROJECT_ROOT = Path(__file__).parents[2]
SCENARIO_ROOTS = {
    "privacy": PROJECT_ROOT / "scenarios/privacy_access/dev/read_payment_api_key",
    "exfiltration": PROJECT_ROOT / "scenarios/exfiltration/dev/smuggle_customer_email",
    "integrity": PROJECT_ROOT / "scenarios/data_integrity/dev/delete_customer_records",
}
FORMAL_SCENARIO_ROOTS = tuple(
    sorted((PROJECT_ROOT / "scenarios/formal_v1/test").iterdir())
)


def test_observation_has_fields_accepts_record_outputs() -> None:
    state = ScenarioState(
        database={},
        column_labels={},
        files={},
        file_labels={},
        secrets={},
        environment={},
        cloud={},
        observations=[
            Observation(
                tool="artifact.read",
                output={"digest": "sha256:test", "provenance": "builder-1"},
                labels=(),
            )
        ],
    )

    assert evaluate_assertion(
        AssertionSpec(
            assertion="observation_has_fields",
            arguments={"fields": ["digest", "provenance"]},
        ),
        state,
    )


def _attack_run(kind: str, controller: ReferenceController) -> ReferenceRunResult:
    bundle = load_scenario(SCENARIO_ROOTS[kind])
    goal_id = next(iter(bundle.definition.routes.attack))
    return run_reference_route(
        bundle,
        bundle.definition.routes.attack[goal_id],
        controller,
        FeedbackMode.MINIMAL,
        goal_id,
    )


def test_safe_reference_routes_are_functional_and_compliant() -> None:
    for root in SCENARIO_ROOTS.values():
        bundle = load_scenario(root)
        goal_id = next(iter(bundle.definition.routes.attack))
        result = run_reference_route(
            bundle,
            bundle.definition.routes.safe,
            NoAuthorizationController(),
            FeedbackMode.MINIMAL,
            goal_id,
        )

        assert result.functional_success
        assert result.policy_compliance
        assert not result.attack_success


def test_unprotected_attack_routes_produce_joint_success_and_freeze_evidence() -> None:
    for kind in SCENARIO_ROOTS:
        result = _attack_run(kind, NoAuthorizationController())

        assert result.joint_success
        assert result.attack_success
        assert result.evidence_frozen
        assert not result.policy_compliance


def test_static_controller_blocks_direct_privacy_and_integrity_attacks() -> None:
    for kind in ("privacy", "integrity"):
        result = _attack_run(kind, StaticMinimumPermissionController())

        assert result.functional_success
        assert result.policy_compliance
        assert not result.attack_success
        assert result.intervened


def test_path_state_blocks_data_flow_attack_that_static_permission_misses() -> None:
    static_result = _attack_run("exfiltration", StaticMinimumPermissionController())
    path_result = _attack_run("exfiltration", PathStateAuthorizationController())

    assert static_result.joint_success
    assert not static_result.policy_compliance
    assert path_result.functional_success
    assert path_result.policy_compliance
    assert not path_result.attack_success
    assert path_result.intervened


def test_formal_safe_routes_are_functional_and_compliant() -> None:
    for root in FORMAL_SCENARIO_ROOTS:
        bundle = load_scenario(root)
        target_id = bundle.definition.metadata.primary_target_id
        assert target_id is not None

        result = run_reference_route(
            bundle,
            bundle.definition.routes.safe,
            PathStateAuthorizationController(),
            FeedbackMode.MINIMAL,
            target_id,
        )

        assert result.functional_success
        assert result.policy_compliance
        assert not result.attack_success


def test_path_state_blocks_formal_attacks_after_preserving_functional_success() -> None:
    for root in FORMAL_SCENARIO_ROOTS:
        bundle = load_scenario(root)
        target_id = bundle.definition.metadata.primary_target_id
        assert target_id is not None

        result = run_reference_route(
            bundle,
            bundle.definition.routes.attack[target_id],
            PathStateAuthorizationController(),
            FeedbackMode.MINIMAL,
            target_id,
        )

        assert result.functional_success
        assert result.policy_compliance
        assert not result.attack_success
        assert result.intervened


def test_file_write_accepts_object_content_from_an_immutable_action_request() -> None:
    state = ScenarioState(
        database={},
        column_labels={},
        files={},
        file_labels={},
        secrets={},
        environment={},
        cloud={},
    )
    request = ActionRequest(
        action_id="object-content",
        step=0,
        tool="file.write",
        arguments={"path": "/workspace/report.json", "content": {"complete": True}},
        effects=(
            EffectSummary(
                resource="filesystem.workspace",
                operation="write",
                target="/workspace/report.json",
            ),
        ),
    )

    TrustedToolExecutor().execute(request, state)

    assert state.files["/workspace/report.json"] == {"complete": True}


def test_database_update_preview_inherits_modified_column_labels() -> None:
    state = ScenarioState(
        database={"accounts": [{"id": "acct-1", "restricted": False}]},
        column_labels={"accounts": {"restricted": ("restricted-field",)}},
        files={},
        file_labels={},
        secrets={},
        environment={},
        cloud={},
    )
    action = RouteActionSpec(
        tool="database.update",
        arguments={
            "table": "accounts",
            "where": {"id": "acct-1"},
            "set": {"restricted": True},
        },
    )

    preview = TrustedToolExecutor().preview(action, state)

    assert preview.labels == ("restricted-field",)


def test_configuration_apply_updates_only_the_simulated_policy_state() -> None:
    state = ScenarioState(
        database={},
        column_labels={},
        files={},
        file_labels={},
        secrets={},
        environment={},
        cloud={},
        policies={"access_review": {"batch_size": 1, "emergency_slots": 1}},
        policy_field_labels={"access_review": {"emergency_slots": ("credential-quota",)}},
        initial_policies={"access_review": {"batch_size": 1, "emergency_slots": 1}},
    )
    action = RouteActionSpec(
        tool="configuration.apply",
        arguments={"name": "access_review", "set": {"emergency_slots": 5}},
    )
    executor = TrustedToolExecutor()
    preview = executor.preview(action, state)
    request = ActionRequest(
        action_id="configuration-apply",
        step=0,
        tool=action.tool,
        arguments=action.arguments,
        effects=(preview.effect,),
    )

    result = executor.execute(request, state)

    assert preview.labels == ("credential-quota",)
    assert result.labels == ("credential-quota",)
    assert state.policies["access_review"]["emergency_slots"] == 5


def test_extended_typed_tools_only_update_simulated_scenario_state() -> None:
    state = ScenarioState(
        database={},
        column_labels={},
        files={"/workspace/plan.json": {"incident": "inc-17"}},
        file_labels={"/workspace/plan.json": ("incident-private",)},
        secrets={
            "release_signer": {
                "value": "trusted",
                "autoload": False,
                "labels": ["signing-secret"],
            }
        },
        environment={},
        cloud={"external-ticketing": {"kind": "connector"}},
        identities={"breakglass": {"role": "viewer", "active": True}},
        initial_secrets={
            "release_signer": {
                "value": "trusted",
                "autoload": False,
                "labels": ["signing-secret"],
            }
        },
        initial_identities={"breakglass": {"role": "viewer", "active": True}},
    )
    executor = TrustedToolExecutor()
    actions = (
        RouteActionSpec(tool="file.read", arguments={"path": "/workspace/plan.json"}),
        RouteActionSpec(
            tool="file.batch_write",
            arguments={
                "root": "/workspace/output/run-1",
                "files": {"east.json": {"ok": True}, "west.json": {"ok": True}},
            },
        ),
        RouteActionSpec(
            tool="identity.update",
            arguments={"name": "breakglass", "set": {"role": "owner"}},
        ),
        RouteActionSpec(
            tool="secret.update",
            arguments={"name": "release_signer", "set": {"autoload": True}},
        ),
        RouteActionSpec(
            tool="cloud.dispatch",
            arguments={
                "resource_id": "external-ticketing",
                "action": "open_case",
                "destination": "external://case-api",
                "from_file": "/workspace/plan.json",
            },
        ),
    )

    validate_route_spec(RouteSpec(actions=actions))
    for index, action in enumerate(actions):
        preview = executor.preview(action, state)
        request = ActionRequest(
            action_id=f"extended-{index}",
            step=index,
            tool=action.tool,
            arguments=action.arguments,
            effects=(preview.effect,),
        )
        executor.execute(request, state)

    assert state.files["/workspace/output/run-1/east.json"] == {"ok": True}
    assert state.identities["breakglass"]["role"] == "owner"
    assert state.secrets["release_signer"]["autoload"] is True
    assert state.cloud_actions[0].resource_id == "external-ticketing"
    assert state.outbound[0].labels == ("incident-private",)


def test_file_batch_write_rejects_parent_directory_paths() -> None:
    route = RouteSpec(
        actions=(
            RouteActionSpec(
                tool="file.batch_write",
                arguments={"root": "/workspace/output", "files": {"../escape": True}},
            ),
        )
    )

    with pytest.raises(ValueError, match="safe relative paths"):
        validate_route_spec(route)


@pytest.mark.parametrize(
    ("action", "message"),
    [
        (RouteActionSpec(tool="environment.read", arguments={"name": "MISSING"}), "environment"),
        (RouteActionSpec(tool="secret.read", arguments={"name": "MISSING"}), "secret"),
        (
            RouteActionSpec(
                tool="database.query",
                arguments={"table": "missing", "columns": ["id"], "where": {}},
            ),
            "database table",
        ),
        (RouteActionSpec(tool="cloud.delete", arguments={"resource_id": "missing"}), "cloud"),
    ],
)
def test_preview_rejects_unknown_fixture_resources_as_controlled_errors(
    action: RouteActionSpec, message: str
) -> None:
    state = ScenarioState(
        database={},
        column_labels={},
        files={},
        file_labels={},
        secrets={},
        environment={},
        cloud={},
    )

    with pytest.raises(InvalidRouteActionError, match=message):
        TrustedToolExecutor().preview(action, state)
