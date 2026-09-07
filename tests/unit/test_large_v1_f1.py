from pathlib import Path

from routebench.authorization import NoAuthorizationController, PathStateAuthorizationController
from routebench.contracts import FeedbackMode
from routebench.runtime.graph import enumerate_terminal_paths
from routebench.runtime.reference import validate_route_spec
from routebench.runtime.runner import run_reference_route
from routebench.scenarios import load_scenario

CASE = Path(__file__).parents[2] / (
    "examples/capability-routing/large_v1/rblg_f1_001_redacted_alert_triage"
)


def test_large_v1_f1_is_materialized_and_bounded() -> None:
    bundle = load_scenario(CASE)
    graph = bundle.definition.graph
    assert graph is not None
    assert len(graph.nodes) >= 32
    assert len(graph.edges) >= 56
    assert len(enumerate_terminal_paths(graph)) >= 300
    validate_route_spec(bundle.definition.routes.safe)
    for route in bundle.definition.routes.attack.values():
        validate_route_spec(route)


def test_large_v1_f1_reference_safe_and_attack_outcomes() -> None:
    bundle = load_scenario(CASE)
    safe = run_reference_route(
        bundle,
        bundle.definition.routes.safe,
        PathStateAuthorizationController(),
        FeedbackMode.MINIMAL,
        "observe_service_secret",
    )
    assert safe.functional_success
    assert safe.policy_compliance
    assert not safe.attack_success
    assert not safe.intervened

    attack = run_reference_route(
        bundle,
        bundle.definition.routes.attack["observe_service_secret"],
        NoAuthorizationController(),
        FeedbackMode.MINIMAL,
        "observe_service_secret",
    )
    assert attack.joint_success
    assert not attack.policy_compliance

    protected_attack = run_reference_route(
        bundle,
        bundle.definition.routes.attack["observe_service_secret"],
        PathStateAuthorizationController(),
        FeedbackMode.MINIMAL,
        "observe_service_secret",
    )
    assert protected_attack.functional_success
    assert protected_attack.policy_compliance
    assert protected_attack.intervened
    assert not protected_attack.attack_success
