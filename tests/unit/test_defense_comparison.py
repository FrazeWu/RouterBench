"""Explicit TEST outcomes and HTTP fixtures; no model experiments or reviews."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from test_defense_study import fixture_study

from routebench.defense.agent import JsonRecoveryAgent
from routebench.defense.comparison import (
    ComparisonRow,
    PolicySession,
    comparison_analysis,
    comparison_schedule,
    descriptive_summary,
    load_comparison,
    load_completed_phase,
    load_fit_phase,
    phase_files,
    run_comparison,
    select_comparator,
)
from routebench.defense.ecpa import AgentReply, AgentReplyKind, AgentView
from routebench.defense.lora import file_digest
from routebench.defense.policies import PerActionAuthorizationPolicy, PublicRulePolicy
from routebench.defense.protocol import AcquisitionLedger
from routebench.defense.relay import StagedResponseRelay
from routebench.defense.study import FrozenStudy, write_exclusive
from scripts.run_defense_study import PacedStudySelector, evaluation_inputs


def case_rows(study: FrozenStudy, split: str = "tune") -> list[ComparisonRow]:
    """Invented outcomes only exercise accounting/selection, never efficacy."""
    assert split in {"tune", "calibration", "test"}
    return [
        ComparisonRow(
            case=case,
            completed=True,
            safe_recovery=True,
            violation=False,
            attack_success=False,
            truncated=False,
            termination_reason="agent_stop",
            online_budget_units=10,
            agent_calls=4,
            selector_calls=0,
            elapsed_seconds=1,
            rollout_file=f"{case.case_id}.rollout.private.json",
            rollout_sha256="c" * 64,
        )
        for case in comparison_schedule(study, split)  # type: ignore[arg-type]
    ]


def complete_phase(path: Path, study: FrozenStudy, phase: str) -> None:
    write_exclusive(
        path / "phase-result.json",
        {
            "source_revision": study.revision,
            "formal_protocol_id": study.protocol_id,
            "frozen_manifest_digest": study.manifest_digest,
            "phase": phase,
            "status": "complete",
            "error_kind": None,
            "artifact_files": phase_files(path),
            "comparison_files": {
                str(file.relative_to(path / "comparison")): file_digest(file)
                for file in (path / "comparison").rglob("*")
                if file.is_file()
            },
        },
    )


def test_schedule_retains_every_arm_seed_and_common_case_seed() -> None:
    study = fixture_study()
    rows = comparison_schedule(study, "tune")
    assert rows == comparison_schedule(study, "tune")
    assert len(rows) == 5 * 2 * 2 * 7
    assert len({row.case_id for row in rows}) == len(rows)
    assert {row.task_id for row in rows} == {
        task.entry.task_id for task in study.tasks if task.entry.split == "tune"
    }
    assert set(Counter(row.arm for row in rows).values()) == {20}
    seeds: dict[tuple[str, str], set[int]] = {}
    for row in rows:
        seeds.setdefault((row.task_id, row.mode), set()).add(row.episode_seed)
    assert all(len(values) == 1 for values in seeds.values())
    assert len({row.episode_seed for row in rows}) == 10
    assert {row.adapter_seed for row in rows} == {None, *study.spec.adapter_seeds}
    changed = replace(study, spec=study.spec.model_copy(update={"arm_order_seed": 100}))
    assert comparison_schedule(changed, "tune") != rows
    assert set(row.case_id for row in comparison_schedule(changed, "tune")) == {
        row.case_id for row in rows
    }


def test_tune_selection_uses_safety_first_family_means_and_explicit_tie_order() -> None:
    study = fixture_study()
    rows = case_rows(study)
    assert select_comparator(rows, study)["selected_comparator"] == "path_rule"
    # An observed violation loses even if utility is otherwise higher.
    path = next(row for row in rows if row.case.arm == "path_rule")
    rows = [
        row.model_copy(update={"violation": True, "safe_recovery": False}) if row is path else row
        for row in rows
    ]
    assert select_comparator(rows, study)["selected_comparator"] == "per_action"
    rows = case_rows(study)
    # Repeat variants contribute one family mean, not two independent votes.
    repeated = next(
        family
        for family, count in Counter(
            task.entry.semantic_family for task in study.tasks if task.entry.split == "tune"
        ).items()
        if count == 2
    )
    rows = [
        row.model_copy(update={"online_budget_units": 50})
        if row.case.arm == "path_rule" and row.case.semantic_family == repeated
        else row
        for row in rows
    ]
    decision = select_comparator(rows, study)
    assert decision["ranking"]["path_rule"][2] == 20
    assert decision["selected_comparator"] == "per_action"
    with pytest.raises(ValueError, match="complete tuning schedule"):
        select_comparator(rows[:-1], study)
    with pytest.raises(ValueError, match="tuning schedule"):
        select_comparator(case_rows(study, "test"), study)


@pytest.mark.parametrize("split", ["calibration", "test"])
def test_analysis_retains_seeds_modes_and_inconclusive_family_precision(split: str) -> None:
    study = fixture_study()
    rows = case_rows(study, split)
    report = comparison_analysis(rows, study, "path_rule")
    assert report["all_seeds_retained"] == list(study.spec.adapter_seeds)
    assert set(report["by_adapter_seed"]) == {str(seed) for seed in study.spec.adapter_seeds}
    assert set(report["by_mode"]) == {"text", "structured"}
    pooled = report["pooled"]
    task_count = sum(task.entry.split == split for task in study.tasks)
    family_count = len(
        {task.entry.semantic_family for task in study.tasks if task.entry.split == split}
    )
    assert pooled["benign"]["pairs"] == task_count * 2 * 3
    assert pooled["benign"]["semantic_families"] == family_count
    assert pooled["benign"]["safe_completion_difference"] == 0
    assert pooled["benign"]["inference_supported"] is False
    assert pooled["meets_prespecified_criteria"] is False
    # All training seeds are retained after a failure in any one seed.
    failed = next(row for row in rows if row.case.adapter_seed and not row.case.attacked)
    rows = [
        row.model_copy(update={"completed": False, "safe_recovery": False, "violation": True})
        if row is failed
        else row
        for row in rows
    ]
    report = comparison_analysis(rows, study, "path_rule")
    assert report["pooled"]["benign"]["safe_completion_difference"] < 0
    assert report["pooled"]["criteria"]["no_observed_violation_increase"] is False


def test_matched_kernel_retains_http_failures_and_validates_measured_artifacts(
    tmp_path: Path,
) -> None:
    study = fixture_study()
    heldout = [task for task in study.tasks if task.entry.split == "tune"][:2]
    study = replace(study, tasks=(study.tasks[0], *heldout))
    safe = {
        task.entry.task_id: {
            next(
                edge.source for edge in task.public.graph.edges if edge.edge_id == edge_id
            ): edge_id
            for edge_id in task.authoring.safe_paths[0]
        }
        for task in heldout
    }
    used, sessions = [], []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        view = AgentView.model_validate_json(body["messages"][1]["content"])
        used.append(view.task.contract.task_id)
        # Retain one complete task's transport failures in every arm/condition.
        if view.task.contract.task_id == heldout[0].entry.task_id:
            raise httpx.ReadTimeout("TEST-only timeout", request=request)
        if view.offer:
            reply = AgentReply(
                kind=AgentReplyKind.ACCEPT,
                edge_id=view.offer.edge_id,
                action=view.offer.action,
                request_hash=view.offer.request_hash,
            )
        elif set(view.task.contract.goal_all) <= set(view.facts):
            reply = AgentReply(kind=AgentReplyKind.STOP)
        else:
            reply = AgentReply(
                kind=AgentReplyKind.PROPOSE, edge_id=safe[view.task.contract.task_id].get(view.node)
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": reply.model_dump_json()}}
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )

    @contextmanager
    def policy(arm: str) -> Iterator[PolicySession]:
        sessions.append(arm)
        yield PolicySession(
            PerActionAuthorizationPolicy() if arm == "unguarded" else PublicRulePolicy()
        )

    async def run() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

            def factory(relay: StagedResponseRelay) -> JsonRecoveryAgent:
                return JsonRecoveryAgent(
                    study.spec.agent, client=client, relay=relay, text_receiver=relay.mode == "text"
                )

            return await run_comparison(
                study, "tune", tmp_path / "comparison", factory, policy, check=lambda: None
            )

    report = asyncio.run(run())
    rows = [ComparisonRow.model_validate(row) for row in report["rows"]]
    assert len(rows) == 2 * 4 * 7 and len(sessions) == 7
    assert set(used) == {task.entry.task_id for task in heldout}
    failures = [row for row in rows if row.case.task_id == heldout[0].entry.task_id]
    assert len(failures) == 28
    assert all(
        not row.completed and row.termination_reason == "agent_response_error" for row in failures
    )
    assert len(list((tmp_path / "comparison").glob("*.rollout.private.json"))) == len(rows)
    assert report["summary"] == descriptive_summary(rows)
    with pytest.raises(FileNotFoundError):
        load_comparison(tmp_path / "comparison", study, "tune")
    complete_phase(tmp_path, study, "tune")
    assert load_comparison(tmp_path / "comparison", study, "tune") == rows
    assert select_comparator(rows, study)
    first = tmp_path / "comparison" / rows[0].rollout_file
    first.write_text("TEST tamper")
    with pytest.raises(ValueError, match="artifact integrity"):
        load_comparison(tmp_path / "comparison", study, "tune")


def test_aborted_phase_and_changed_identity_never_load(tmp_path: Path) -> None:
    study = fixture_study()
    write_exclusive(tmp_path / "TEST.json", {"TEST": True})
    complete_phase(tmp_path, study, "calibration")
    assert load_completed_phase(tmp_path, study, "calibration")["status"] == "complete"
    with pytest.raises(ValueError, match="matching measured phase"):
        load_completed_phase(tmp_path, study, "test")
    path = tmp_path / "phase-result.json"
    raw = json.loads(path.read_text())
    raw["status"] = "aborted"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="matching measured phase"):
        load_completed_phase(tmp_path, study, "calibration")


def test_prerequisites_refuse_missing_fit_and_tuning_before_model_allocation(
    tmp_path: Path,
) -> None:
    study = fixture_study()
    args = argparse.Namespace(phase="test", fit=None, tune=None, calibration=None)
    with pytest.raises(ValueError, match="three-seed"):
        evaluation_inputs(study, args, tmp_path)
    with pytest.raises(FileNotFoundError):
        load_fit_phase(tmp_path / "missing-fit", study)


def test_fit_loader_binds_all_seed_recipes_and_the_verified_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from routebench.defense.contracts import content_hash

    study = fixture_study()
    source_group = SimpleNamespace(
        group_id="TEST-GROUP", model_dump=lambda **kwargs: {"TEST": True}
    )
    groups = {source_group.group_id: content_hash({"TEST": True})}
    collection = tmp_path / "collection-phase/collection"
    collection.mkdir(parents=True)
    write_exclusive(collection.parent / "phase-result.json", {"TEST": "complete collection"})
    fit = tmp_path / "fit"
    write_exclusive(
        fit / "phase-manifest.json",
        {
            "collection": str(collection),
            "collection_phase_sha256": file_digest(collection.parent / "phase-result.json"),
        },
    )
    write_exclusive(
        fit / "fit-complete.json",
        {
            "source_revision": study.revision,
            "formal_protocol_id": study.protocol_id,
            "adapter_seeds": study.spec.adapter_seeds,
        },
    )
    for seed in study.spec.adapter_seeds:
        write_exclusive(fit / f"adapter-seed-{seed}/TEST.json", {"TEST": seed})

    def adapter_manifest(path: Path, *args: Any, **kwargs: Any) -> dict[str, Any]:
        seed = int(path.name.removeprefix("adapter-seed-"))
        return {
            "source_revision": study.revision,
            "spec": study.spec.lora.model_copy(update={"seed": seed}).model_dump(mode="json"),
            "data_source_revisions": [study.revision],
            "source_group_hashes": groups,
        }

    # Fake adapter bytes/labels are isolated TEST fixtures. The loader still
    # checks real phase hashes and seed/recipe/group equality before inference.
    monkeypatch.setattr(
        "routebench.defense.comparison.load_training_phase", lambda *args: [source_group]
    )
    monkeypatch.setattr("routebench.defense.comparison.validate_adapter", adapter_manifest)
    complete_phase(fit, study, "fit")
    assert set(load_fit_phase(fit, study)) == set(study.spec.adapter_seeds)

    def wrong_recipe(path: Path, *args: Any, **kwargs: Any) -> dict[str, Any]:
        manifest = adapter_manifest(path)
        manifest["spec"]["updates"] += 1
        return manifest

    monkeypatch.setattr("routebench.defense.comparison.validate_adapter", wrong_recipe)
    with pytest.raises(ValueError, match="recipe/source"):
        load_fit_phase(fit, study)
    monkeypatch.setattr("routebench.defense.comparison.validate_adapter", adapter_manifest)
    (collection.parent / "phase-result.json").write_text('{"TEST":"changed"}')
    with pytest.raises(ValueError, match="collection phase identity"):
        load_fit_phase(fit, study)


def test_test_entry_requires_same_fit_tuning_and_calibration_decisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    study = fixture_study()
    base = tmp_path / "artifacts/private"
    fit, tune, calibration = (base / name for name in ("fit", "tune", "calibration"))
    for path in (fit, tune, calibration):
        write_exclusive(path / "phase-result.json", {"TEST": "complete phase"})
    monkeypatch.setattr(
        "scripts.run_defense_study.load_fit_phase",
        lambda *args: {seed: fit / str(seed) for seed in study.spec.adapter_seeds},
    )
    rows = case_rows(study)
    monkeypatch.setattr("scripts.run_defense_study.load_comparison", lambda *args: rows)
    selection = select_comparator(rows, study)
    identity = {"fit": str(fit), "fit_result_sha256": file_digest(fit / "phase-result.json")}
    write_exclusive(tune / "phase-manifest.json", {"prerequisites": identity})
    write_exclusive(tune / "decision.json", selection)
    identity.update(
        {
            "tune": str(tune),
            "tune_result_sha256": file_digest(tune / "phase-result.json"),
            "selection_sha256": file_digest(tune / "decision.json"),
        }
    )
    write_exclusive(calibration / "phase-manifest.json", {"prerequisites": identity})
    write_exclusive(calibration / "decision.json", selection)
    args = argparse.Namespace(phase="test", fit=fit, tune=tune, calibration=calibration)
    result = evaluation_inputs(study, args, tmp_path)
    assert result["selection"] == selection
    assert result["prerequisites"]["calibration"] == str(calibration)
    changed = {**selection, "selected_comparator": "compact_base"}
    (calibration / "decision.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="cannot alter"):
        evaluation_inputs(study, args, tmp_path)
    (calibration / "decision.json").write_text(json.dumps(selection))
    (fit / "phase-result.json").write_text('{"TEST":"different fit"}')
    with pytest.raises(ValueError, match="exact three fitted adapters"):
        evaluation_inputs(study, args, tmp_path)


def test_local_selector_calls_share_hard_accounting_and_persist_fallbacks() -> None:
    class FakeModel:
        config = fixture_study().spec.compact

        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def choose(self, observation: object, **kwargs: object) -> Any:
            self.calls.append(
                {"prompt_tokens": 20, "completion_tokens": 3, "status": "invalid_output_fallback"}
            )
            from routebench.defense.collect import PolicyChoice

            return PolicyChoice("deny")

    class FakeTelemetry:
        def check(self) -> None:
            pass

    class FakePacer:
        def before(self, gpu: int) -> None:
            assert gpu == 0

        def after(self) -> None:
            pass

    ledger = AcquisitionLedger(1, 10000)
    records: list[dict[str, Any]] = []
    selector = PacedStudySelector(
        FakeModel(),  # type: ignore[arg-type]
        use_adapter=True,
        telemetry=FakeTelemetry(),  # type: ignore[arg-type]
        pacer=FakePacer(),  # type: ignore[arg-type]
        ledger=ledger,
        record=records.append,
    )
    import random

    assert selector.choose(None, rng=random.Random(0)).candidate_id == "deny"  # type: ignore[arg-type]
    assert ledger.calls == {"rollout": 1} and ledger.tokens == {"rollout": 23}
    assert records[0]["call"]["status"] == "invalid_output_fallback"
    with pytest.raises(RuntimeError, match="call budget"):
        selector.choose(None, rng=random.Random(0))  # type: ignore[arg-type]
