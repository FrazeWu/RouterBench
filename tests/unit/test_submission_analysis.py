from __future__ import annotations

from routebench.submission.analysis import composition_report, interval
from scripts.run_submission_queue import jobs


def test_empty_conditional_denominator_is_undefined() -> None:
    result = interval(
        [{"family": "f", "failure": False, "eligible": False}], "failure", denominator="eligible"
    )
    assert result["undefined"] and result["estimate"] is None
    assert result["denominator"] == 0 and result["ci95"] is None


def test_clustered_estimate_retains_repeat_weights_and_reports_sensitivity() -> None:
    rows = [
        {"family": "a", "success": True},
        {"family": "a", "success": True},
        {"family": "b", "success": False},
    ]
    result = interval(rows, "success", replicates=100)
    assert result["estimate"] == 2 / 3
    assert result["equal_cluster_weight_sensitivity"] == 0.5
    assert result["denominator"] == 3 and result["clusters"] == 2


def test_composition_joint_and_both_gap_denominators() -> None:
    units = []
    for pair, R, J in (("p1", False, True), ("p2", True, False)):
        for name in ("K", "L_allow", "L_deny", "L_event_allow", "L_event_deny", "R", "J"):
            units.append(
                {
                    "pair_id": pair,
                    "presentation": 0,
                    "unit": name,
                    "family": pair,
                    "kind": "dependency",
                    "status": "complete",
                    "correct": R if name == "R" else J if name == "J" else True,
                }
            )
    report = composition_report(units)["overall"]
    assert report["D_rec"]["estimate"] == 0.5 and report["D_rec"]["denominator"] == 2
    assert report["D_plan"]["estimate"] == 1 and report["D_plan"]["denominator"] == 1
    assert report["joint_counts"] == {"1101": 1, "1110": 1}


def test_finite_queue_has_exact_seventeen_jobs_without_new_training() -> None:
    queue = jobs()
    assert len(queue) == len({job["key"] for job in queue}) == 17
    assert [job["key"] for job in queue[:4]] == [
        "E9",
        "E1-qwen3-14b",
        "E1-qwen3-1.7b",
        "E1-qwen2.5-7b",
    ]
    assert len([job for job in queue if job["key"].startswith("E6")]) == 2
    assert all("fit" not in job["arguments"] for job in queue)
