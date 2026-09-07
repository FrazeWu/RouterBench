from __future__ import annotations

from pathlib import Path

from routebench.authorization import NoAuthorizationController, PathStateAuthorizationController
from routebench.contracts import FeedbackMode
from routebench.runtime.graph import audit_observable_optimum
from routebench.runtime.runner import run_reference_route
from routebench.scenarios import load_scenario

PROJECT_ROOT = Path(__file__).parents[2]
PILOT_ROOT = PROJECT_ROOT / "examples/capability-routing/pilot_v1"
PILOT_CASES = {
    "rbcal_f1_001_scoped_customer_access_review": (
        "observe_customer_contact",
        "observe_review_credential",
        "delete_review_receipt",
    ),
    "rbcal_f2_001_bounded_audit_export": (
        "transfer_private_audit_data",
        "observe_delivery_credential",
        "delete_source_evidence",
    ),
    "rbcal_f3_001_request_timeout_repair": (
        "modify_retry_budget",
        "disable_authentication",
        "observe_runtime_credential",
    ),
    "rbcal_f4_001_retention_cleanup": (
        "delete_held_record",
        "delete_active_record",
        "delete_entire_partition",
    ),
}


def test_pilot_safe_routes_complete_under_path_state_authorization() -> None:
    for scenario_id, target_ids in PILOT_CASES.items():
        bundle = load_scenario(PILOT_ROOT / scenario_id)
        result = run_reference_route(
            bundle,
            bundle.definition.routes.safe,
            PathStateAuthorizationController(),
            FeedbackMode.MINIMAL,
            target_ids[0],
        )

        assert result.functional_success
        assert result.policy_compliance
        assert not result.attack_success
        assert not result.intervened


def test_pilot_attack_certificates_are_executable_and_denied_after_task_completion() -> None:
    for scenario_id, target_ids in PILOT_CASES.items():
        bundle = load_scenario(PILOT_ROOT / scenario_id)
        for target_id in target_ids:
            unprotected = run_reference_route(
                bundle,
                bundle.definition.routes.attack[target_id],
                NoAuthorizationController(),
                FeedbackMode.MINIMAL,
                target_id,
            )
            protected = run_reference_route(
                bundle,
                bundle.definition.routes.attack[target_id],
                PathStateAuthorizationController(),
                FeedbackMode.MINIMAL,
                target_id,
            )

            assert unprotected.joint_success
            assert not unprotected.policy_compliance
            assert protected.functional_success
            assert protected.policy_compliance
            assert not protected.attack_success
            assert protected.intervened


def test_current_pilot_fails_observable_optimum_gate_without_disclosing_routes() -> None:
    bundle = load_scenario(PILOT_ROOT / next(iter(PILOT_CASES)))
    audit = audit_observable_optimum(bundle)

    assert audit.decisive_hidden_information
    assert not audit.public_rule_unique or not audit.private_optimum_matches_public_optimum
    assert audit.ambiguity_kind in {
        "incomparable_authority",
        "equal_public_rank",
        "none",
    }
