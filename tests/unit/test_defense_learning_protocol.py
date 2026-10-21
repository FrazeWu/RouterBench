from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np
import pytest

from routebench.defense.collect import collect_episode
from routebench.defense.development import load_development_tasks
from routebench.defense.ecpa import AgentReply, AgentReplyKind, AgentView, ECPAEnvironment
from routebench.defense.evaluation import HiddenOutcomeEvaluator
from routebench.defense.features import FeatureBuilder, FloatArray
from routebench.defense.learning import (
    LearningEpisode,
    LearningObjective,
    TrainingSpec,
    load_scorer_ensemble,
    prepare_data,
)
from routebench.defense.policies import PublicRulePolicy
from routebench.defense.protocol import (
    AcquisitionLedger,
    ComparisonSpec,
    PairedResult,
    SplitItem,
    approximate_family_requirement,
    paired_family_comparison,
    validate_splits,
)
from routebench.defense.traces import build_transitions
from routebench.runtime.reference import ScenarioState

ROOT = Path(__file__).parents[2]


class FixtureEncoder:
    """Small inspectable feature stub for target/split tests, never a research encoder."""

    identity = "test_fixture_only"

    def encode(self, texts: object) -> FloatArray:
        assert isinstance(texts, (list, tuple))
        return np.asarray(
            [[len(text) / 1000, text.count("read") / 100] for text in texts], dtype=np.float32
        )


def _records(*, cutoff: int | None = None) -> LearningEpisode:
    task = load_development_tasks(ROOT, ROOT / "configs/defense/development-contracts.yaml")[0]
    environment = ECPAEnvironment(
        task.public, ScenarioState.from_fixture(task.bundle.root / "fixtures/state.json")
    )

    class ScriptAgent:
        def __init__(self) -> None:
            self.edges = iter(("query_paused_ids", "stage_inventory", "verify_staged_inventory"))

        async def respond(self, view: AgentView, *, seed: int) -> AgentReply:
            edge = next(self.edges, None)
            return (
                AgentReply(kind=AgentReplyKind.PROPOSE, edge_id=edge)
                if edge
                else AgentReply(kind=AgentReplyKind.STOP)
            )

    episode = asyncio.run(
        collect_episode(
            environment,
            ScriptAgent(),
            PublicRulePolicy(),
            evaluator=HiddenOutcomeEvaluator(task.bundle),
            max_collection_steps=cutoff,
        )
    )
    return LearningEpisode(
        episode_id="actual-failed-rollout",
        semantic_family="inventory",
        attack_mechanism="benign",
        split="train",
        source_revision="a" * 40,
        formal_protocol_id="ecpa-test-v1",
        transitions=build_transitions(episode),
    )


def test_multistep_target_uses_actual_rewards_and_concrete_next_menus() -> None:
    episode = _records()
    spec = TrainingSpec(
        objective=LearningObjective.OFFLINE_TD, seed=1, n_steps=2, minimum_support=1
    )
    data = prepare_data(
        [episode], FeatureBuilder(FixtureEncoder()), spec, formal_protocol_id="ecpa-test-v1"
    )
    assert data.n_step_returns[0] == pytest.approx(sum(r.reward for r in episode.transitions[:2]))
    assert data.bootstrap_features[0] is not None
    assert data.bootstrap_features[-1] is None
    assert data.labels[0, 0] == 0  # Real early STOP failed; never relabel as success.
    assert data.labels[0, 3] == pytest.approx(sum(r.reward for r in episode.transitions))
    assert data.features.shape[0] == len(episode.transitions)


def test_unsupported_backup_uses_observed_return_instead_of_extrapolation() -> None:
    episode = _records()
    spec = TrainingSpec(
        objective=LearningObjective.OFFLINE_TD, seed=1, n_steps=1, minimum_support=100
    )
    data = prepare_data(
        [episode], FeatureBuilder(FixtureEncoder()), spec, formal_protocol_id="ecpa-test-v1"
    )
    assert all(value is None for value in data.bootstrap_features)
    assert data.n_step_returns[0] == pytest.approx(sum(r.reward for r in episode.transitions))


def test_censored_rollout_is_not_a_failure_training_label() -> None:
    episode = _records(cutoff=1)
    assert episode.transitions[0].truncated and not episode.transitions[0].terminal
    spec = TrainingSpec(objective=LearningObjective.SUPERVISED, seed=1)
    with pytest.raises(ValueError, match="no completed"):
        prepare_data(
            [episode], FeatureBuilder(FixtureEncoder()), spec, formal_protocol_id="ecpa-test-v1"
        )


def test_fit_rejects_test_data_and_duplicate_episodes() -> None:
    episode = _records()
    spec = TrainingSpec(objective=LearningObjective.SUPERVISED, seed=1)
    with pytest.raises(ValueError, match="only training"):
        prepare_data(
            [episode.model_copy(update={"split": "test"})],
            FeatureBuilder(FixtureEncoder()),
            spec,
            formal_protocol_id="ecpa-test-v1",
        )
    with pytest.raises(ValueError, match="duplicate"):
        prepare_data(
            [episode, episode],
            FeatureBuilder(FixtureEncoder()),
            spec,
            formal_protocol_id="ecpa-test-v1",
        )


def test_formal_training_records_must_match_a_frozen_protocol_identity() -> None:
    episode = _records()
    spec = TrainingSpec(objective=LearningObjective.SUPERVISED, seed=1)
    with pytest.raises(ValueError, match="requires a frozen"):
        prepare_data([episode], FeatureBuilder(FixtureEncoder()), spec)
    with pytest.raises(ValueError, match="matching frozen"):
        prepare_data(
            [episode.model_copy(update={"formal_protocol_id": "ecpa-other-v1"})],
            FeatureBuilder(FixtureEncoder()),
            spec,
            formal_protocol_id="ecpa-test-v1",
        )


def test_scorer_loading_requires_expected_formal_identity_and_rejects_development(
    tmp_path: Path,
) -> None:
    encoder = FeatureBuilder(FixtureEncoder())

    def write_scorer(path: Path, *, development_smoke: bool, protocol: str | None) -> None:
        path.mkdir()
        np.savez_compressed(path / "weights.npz", placeholder=np.zeros(1, dtype=np.float32))
        (path / "manifest.json").write_text(
            json.dumps(
                {
                    "spec": TrainingSpec(objective=LearningObjective.SUPERVISED, seed=1).model_dump(
                        mode="json"
                    ),
                    "encoder_identity": FixtureEncoder.identity,
                    "support": {},
                    "feature_dimension": 2,
                    "development_smoke": development_smoke,
                    "formal_protocol_id": protocol,
                    "episode_ids": [],
                    "episode_fingerprints": [],
                    "source_revisions": [],
                    "loss_first_last": [],
                }
            )
        )

    development = tmp_path / "development"
    write_scorer(development, development_smoke=True, protocol=None)
    with pytest.raises(ValueError, match="development smoke"):
        load_scorer_ensemble([development], encoder)
    assert load_scorer_ensemble([development], encoder, allow_development_smoke=True)

    formal = tmp_path / "formal"
    write_scorer(formal, development_smoke=False, protocol="ecpa-test-v1")
    with pytest.raises(ValueError, match="requires an expected"):
        load_scorer_ensemble([formal], encoder)
    with pytest.raises(ValueError, match="does not match"):
        load_scorer_ensemble([formal], encoder, expected_formal_protocol_id="ecpa-other-v1")
    assert load_scorer_ensemble([formal], encoder, expected_formal_protocol_id="ecpa-test-v1")


def test_family_and_attack_holdouts_are_independent_requirements() -> None:
    train = SplitItem(
        task_id="train", semantic_family="family_a", attack_mechanism="m_a", split="train"
    )
    test = SplitItem(
        task_id="test", semantic_family="family_b", attack_mechanism="m_b", split="test"
    )
    validate_splits([train, test])
    with pytest.raises(ValueError, match="semantic families"):
        validate_splits([train, test.model_copy(update={"semantic_family": "family_a"})])
    with pytest.raises(ValueError, match="attack mechanisms"):
        validate_splits([train, test.model_copy(update={"attack_mechanism": "m_a"})])


def test_diagnostic_calls_and_failed_calls_consume_acquisition_budget() -> None:
    ledger = AcquisitionLedger(call_limit=3, token_limit=150)
    diagnostic = ledger.reserve("diagnostic", 100)
    with pytest.raises(RuntimeError, match="token budget"):
        ledger.reserve("rollout", 100)
    ledger.reconcile(diagnostic, 20)
    failed = ledger.reserve("rollout", 100)
    ledger.reconcile(failed, None)
    branch = ledger.reserve("branch", 20)
    ledger.reconcile(branch, 20)
    assert sum(ledger.tokens.values()) == 140
    with pytest.raises(RuntimeError, match="call budget"):
        ledger.reserve("rollout", 1)


def test_paired_family_inference_keeps_failed_cases_and_seeds_in_clusters() -> None:
    rows = []
    for family in range(4):
        for condition in ("attacked", "benign"):
            for seed in range(5):
                rows.append(
                    PairedResult(
                        pair_id=f"{family}-{condition}-{seed}",
                        semantic_family=f"family_{family}",
                        condition=condition,
                        learned_success=True,
                        baseline_success=condition == "benign",
                        learned_violation=False,
                        baseline_violation=False,
                    )
                )
    report = paired_family_comparison(rows, ComparisonSpec(bootstrap_replicates=100))
    assert report["meets_prespecified_criteria"]
    assert report["attacked"]["semantic_families"] == 4  # type: ignore[index]
    duplicated_seeds = [row.model_copy(update={"pair_id": row.pair_id + "repeat"}) for row in rows]
    repeated = paired_family_comparison(
        rows + duplicated_seeds, ComparisonSpec(bootstrap_replicates=100)
    )
    assert repeated["attacked"]["paired_95_ci"] == report["attacked"]["paired_95_ci"]  # type: ignore[index]
    with pytest.raises(ValueError, match="unique"):
        paired_family_comparison(rows + rows)


def test_more_correlated_cases_require_more_independent_families() -> None:
    independent = approximate_family_requirement(paired_discordance=0.2, intraclass_correlation=0)
    correlated = approximate_family_requirement(paired_discordance=0.2, intraclass_correlation=0.3)
    assert isinstance(correlated["approximate_families"], int)
    assert isinstance(independent["approximate_families"], int)
    assert correlated["approximate_families"] > independent["approximate_families"]
