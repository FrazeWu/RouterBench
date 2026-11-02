from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from routebench.defense.contracts import content_hash
from routebench.defense.corpus import CorpusTask, load_corpus, readiness
from routebench.defense.freeze import (
    REVIEW_CHECKS,
    SourceReview,
    StudySpec,
    freeze_study,
    task_source_digest,
    validate_freeze_sources,
    validate_source_reviews,
    write_frozen_study,
)
from routebench.defense.lora import file_digest
from routebench.defense.study import load_frozen_study

ROOT = Path(__file__).parents[2]
MANIFEST = Path("configs/defense/independent-corpus.yaml")


def config(root: Path) -> dict[str, Any]:
    return {
        "purpose": "ecpa_independent_formal_study",
        "corpus_manifest": str(MANIFEST),
        "agent": {"model": "fixture-agent"},
        "task_model_path": str(root / "fixture-models/agent"),
        "compact": {"model_path": str(root / "fixture-models/defender"), "device": "cpu"},
        "lora": {
            "seed": 29,
            "updates": 16,
            "gradient_accumulation": 1,
            "learning_rate": 0.0001,
            "rank": 8,
            "alpha": 16,
            "dropout": 0.0,
            "target_modules": ["q_proj", "v_proj"],
        },
        "budgets": {},
        "comparison": {},
        "adapter_seeds": [29],
        "presentations": 1,
        "episode_seed": 43,
        "arm_order_seed": 47,
        "state_selection_seed": 53,
        "continuation_seed": 59,
        "maximum_branch_states_per_parent": 2,
        "branch_repeats": 1,
        "modes": ["text", "structured"],
        "logging_uniform_weight": 0.5,
        "acquisition_call_limit": 100,
        "acquisition_token_limit": 100000,
        "resources": {
            "gpu_ids": [0, 1],
            "task_agent_gpu": 1,
            "maximum_celsius": 85,
            "minimum_request_gap_seconds": 2,
            "cooling_pause_celsius": 73,
            "cooling_resume_celsius": 71,
            "maximum_cooling_wait_seconds": 300,
        },
        "training_acquisition": "enumerate_each_train_task_transport_condition_once",
        "required_training_target_kinds": ["allow", "constrain", "escalate", "deny"],
        "comparator_selection": "lowest_violations_then_highest_safe_completion_then_cost_on_tune",
        "comparison_schedule": "seeded_arm_blocks_common_episode_seeds",
        "comparator_arms": ["path_rule", "per_action", "compact_base"],
        "comparator_cost": "family_mean_online_budget_units",
        "calibration_policy": "audit_fixed_policy_no_selection_or_test_gate",
        "checkpoint_selection": "single_prespecified_update_count",
        "precision_interpretation": "retain_criteria_report_inconclusive",
        "structured_mechanism_claim": "shared_proposal_substitution_no_holdout",
    }


def review(task: CorpusTask, peers: tuple[CorpusTask, ...]) -> dict[str, object]:
    # These are clearly identified local TEST attestations, never corpus reviews.
    return {
        "purpose": "independent_defense_source_review",
        "task_id": task.entry.task_id,
        "source_digest": task_source_digest(task),
        "reviewer_id": "TEST-REVIEWER",
        "task_author_ids": list(task.entry.task_author_ids),
        "verdict": "accepted",
        "checks": dict.fromkeys(REVIEW_CHECKS, "pass"),
        "rationale": "TEST FIXTURE ONLY: this is not an independent semantic review. " * 2,
        "distinct_from": {
            peer.entry.task_id: task_source_digest(peer)
            for peer in peers
            if peer.entry.task_id != task.entry.task_id
        },
    }


def fixture_repo(root: Path) -> tuple[StudySpec, dict[str, object], dict[str, object]]:
    shutil.copytree(ROOT / "scenarios/defense", root / "scenarios/defense")
    (root / "configs/defense").mkdir(parents=True)
    shutil.copy(ROOT / MANIFEST, root / MANIFEST)
    (root / "catalog").mkdir()
    shutil.copy(
        ROOT / "catalog/capability_universe.yaml", root / "catalog/capability_universe.yaml"
    )
    _, tasks = load_corpus(root, root / MANIFEST)
    raw = yaml.safe_load((root / MANIFEST).read_text())
    # A smaller TEST allocation permits exercising the freeze success path.
    raw["planned_families"] = {
        split: len({task.entry.semantic_family for task in tasks if task.entry.split == split})
        for split in ("train", "tune", "calibration", "test")
    }
    raw["independent_reviewer_id"] = "TEST-REVIEWER"
    (root / "reviews").mkdir()
    for task, entry in zip(tasks, raw["entries"], strict=True):
        entry["independent_review"] = "accepted"
        entry["review_evidence"] = f"reviews/{task.entry.task_id}.json"
        (root / entry["review_evidence"]).write_text(json.dumps(review(task, tasks)))
    (root / MANIFEST).write_text(yaml.safe_dump(raw))
    for name in ("agent", "defender"):
        directory = root / "fixture-models" / name
        directory.mkdir(parents=True)
        (directory / "model.safetensors").write_bytes(b"TEST-NOT-MODEL-WEIGHTS")
        (directory / "tokenizer.json").write_text('{"TEST_ONLY":true}')
    spec = StudySpec.model_validate(config(root))
    (root / "configs/defense/study.yaml").write_text(yaml.safe_dump(spec.model_dump(mode="json")))
    (root / ".gitignore").write_text("artifacts/\nfixture-models/\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "test: source-bound freeze fixture",
        ],
        cwd=root,
        check=True,
    )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    corpus, tasks = load_corpus(root, root / MANIFEST)
    authoring: dict[str, object] = {
        "source_revision": revision,
        **readiness(corpus, tasks),
        "task_checks": [
            {
                "task_id": task.entry.task_id,
                "source_digest": task.digest,
                "attack_target_and_violation_reproduced": True,
                "model_rollouts": 0,
                "training_labels": 0,
            }
            for task in tasks
        ],
    }
    measurements = {
        name: {
            "samples": 1,
            "maximum_prompt_tokens": 100,
            "completion_reserve": 96 if name == "defender_selector" else 768,
            "overflow_samples": 0,
        }
        for name in (
            "agent_proposal",
            "agent_text_fixed_attack",
            "agent_text_representative_benign",
            "agent_text_full_draft_reserve",
            "agent_text_attack_full_draft_reserve",
            "defender_selector",
        )
    }
    contexts: dict[str, object] = {
        "source_revision": revision,
        "corpus_digests": {task.entry.task_id: task.digest for task in tasks},
        "context_tokens": 8192,
        "sampled_inputs_fit": True,
        "measurements": measurements,
        "tokenizer_files": {
            role: {"tokenizer.json": file_digest(root / "fixture-models" / name / "tokenizer.json")}
            for role, name in (("agent", "agent"), ("defender", "defender"))
        },
    }
    return spec, authoring, contexts


def test_underfilled_family_allocation_cannot_be_frozen() -> None:
    spec, tasks = load_corpus(ROOT, ROOT / MANIFEST)
    underfilled = spec.model_copy(
        update={
            "planned_families": {
                **spec.planned_families,
                "test": spec.planned_families["test"] + 1,
            }
        }
    )
    with pytest.raises(ValueError, match="allocation"):
        validate_freeze_sources(ROOT, underfilled, tasks)


@pytest.mark.parametrize(
    "mutation",
    [
        "self_review",
        "wrong_reviewer",
        "missing_check",
        "stale_digest",
        "missing_peer",
        "wrong_author",
    ],
)
def test_source_review_requires_current_nonself_complete_attestations(
    tmp_path: Path, mutation: str
) -> None:
    fixture_repo(tmp_path)
    _, tasks = load_corpus(tmp_path, tmp_path / MANIFEST)
    # Conservation/journal retain different invariant families despite their
    # matching dependency skeleton; merged variants no longer need peer claims.
    task = next(task for task in tasks if task.entry.task_id == "ecpa_test_conserved_transfer")
    assert task.entry.review_evidence is not None
    path = tmp_path / task.entry.review_evidence
    payload = json.loads(path.read_text())
    if mutation == "self_review":
        payload["reviewer_id"] = task.entry.task_author_ids[0]
    elif mutation == "wrong_reviewer":
        payload["reviewer_id"] = "OTHER-REVIEWER"
    elif mutation == "missing_check":
        del payload["checks"]["source_isolation"]
    elif mutation == "stale_digest":
        payload["source_digest"] = "0" * 64
    elif mutation == "missing_peer":
        payload["distinct_from"] = {}
    else:
        payload["task_author_ids"] = ["UNRECORDED-AUTHOR"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        validate_source_reviews(tmp_path, tasks, reviewer_id="TEST-REVIEWER")


def test_freeze_binds_sources_models_audits_and_refuses_dirty_or_overwritten_runs(
    tmp_path: Path,
) -> None:
    spec, authoring, contexts = fixture_repo(tmp_path)
    corpus, tasks = load_corpus(tmp_path, tmp_path / MANIFEST)
    config_path = tmp_path / "configs/defense/study.yaml"

    def freeze(
        context: dict[str, object] = contexts,
        authoring_report: dict[str, object] = authoring,
    ) -> dict[str, object]:
        return freeze_study(
            tmp_path,
            spec,
            corpus,
            tasks,
            config_path=config_path,
            authoring_audit=authoring_report,
            context_audit=context,
        )

    frozen = freeze()
    payload = {key: value for key, value in frozen.items() if key != "protocol_id"}
    assert frozen["protocol_id"] == "ecpa-" + content_hash(payload)
    assert frozen["training_data_collected"] is frozen["adapter_fitted"] is False
    output = tmp_path / "artifacts/private/manifest.json"
    write_frozen_study(tmp_path, output, frozen)
    assert json.loads(output.read_text()) == frozen
    reloaded = load_frozen_study(tmp_path, output)
    assert reloaded.protocol_id == frozen["protocol_id"]
    assert reloaded.revision == frozen["source_revision"]
    with pytest.raises(FileExistsError):
        write_frozen_study(tmp_path, output, frozen)
    with pytest.raises(ValueError, match="artifacts/private"):
        write_frozen_study(tmp_path, tmp_path / "public.json", frozen)
    with pytest.raises(ValueError, match="protocol identity"):
        write_frozen_study(
            tmp_path,
            tmp_path / "artifacts/private/tampered.json",
            {**frozen, "training_data_collected": True},
        )
    changed = dict(contexts, source_revision="0" * 40)
    with pytest.raises(ValueError, match="source-bound"):
        freeze(changed)
    for altered in (
        dict(contexts, measurements={}),
        dict(contexts, measurements={"agent_proposal": {"samples": 1}}),
        dict(contexts, tokenizer_files={}),
    ):
        with pytest.raises(ValueError):
            freeze(altered)
    original_rows = contexts["measurements"]
    assert isinstance(original_rows, dict)
    for patch in ({"completion_reserve": 12}, {"maximum_prompt_tokens": 8192}, {"samples": 0}):
        altered_rows = {
            **original_rows,
            "agent_proposal": {**original_rows["agent_proposal"], **patch},
        }
        with pytest.raises(ValueError, match="completion budgets"):
            freeze({**contexts, "measurements": altered_rows})
    with pytest.raises(ValueError, match="exact frozen corpus"):
        freeze(authoring_report={**authoring, "task_checks": []})
    # Model identity, not only a human-facing model name, determines the freeze.
    weights = tmp_path / "fixture-models/defender/model.safetensors"
    weights.write_bytes(b"DIFFERENT-TEST-NOT-MODEL-WEIGHTS")
    assert freeze()["protocol_id"] != frozen["protocol_id"]
    with pytest.raises(ValueError, match="model snapshot"):
        load_frozen_study(tmp_path, output)
    token_file = tmp_path / "fixture-models/agent/tokenizer.json"
    token_file.write_text("changed tokenizer")
    with pytest.raises(ValueError, match="tokenizer"):
        freeze()
    (tmp_path / "untracked.txt").write_text("dirty")
    with pytest.raises(ValueError, match="commit"):
        freeze()


@pytest.mark.parametrize(
    "field,value",
    [
        ("adapter_seeds", []),
        ("adapter_seeds", [29, 31, 37]),
        ("adapter_seeds", [29, 29]),
        ("adapter_seeds", [31]),
        ("modes", ["structured"]),
        ("comparison", {"maximum_benign_loss": 0.1}),
        ("precision_interpretation", "claim_success_when_all_ties"),
        ("structured_mechanism_claim", "held_out_mechanism"),
        ("lora", {"seed": 29, "updates": 16}),
        ("required_training_target_kinds", ["allow", "deny"]),
        ("presentations", 2),
        ("resources", {"gpu_ids": [0, 0], "task_agent_gpu": 1}),
    ],
)
def test_formal_plan_cannot_silently_relax_prespecified_design(
    tmp_path: Path, field: str, value: object
) -> None:
    payload = config(tmp_path)
    payload[field] = value
    with pytest.raises(ValueError):
        StudySpec.model_validate(payload)


def test_review_schema_does_not_accept_authoring_notes_as_independent_review() -> None:
    with pytest.raises(ValueError):
        SourceReview.model_validate({"independent_review": "accepted", "note": "looks good"})


def test_review_identity_binds_assignment_without_circular_acceptance_fields() -> None:
    _, tasks = load_corpus(ROOT, ROOT / MANIFEST)
    task = tasks[0]
    accepted = replace(
        task,
        entry=task.entry.model_copy(
            update={"independent_review": "accepted", "review_evidence": "review.json"}
        ),
    )
    assert task_source_digest(accepted) == task_source_digest(task)
    for changed in ({"split": "tune"}, {"attack_mechanism": "forged_observation_envelope"}):
        other = replace(task, entry=task.entry.model_copy(update=changed))
        assert task_source_digest(other) != task_source_digest(task)
