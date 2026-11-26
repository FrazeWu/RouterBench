from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

import yaml

from routebench.defense.collect import PolicyChoice
from routebench.defense.corpus import load_corpus
from routebench.defense.development import load_development_tasks
from routebench.defense.ecpa import AgentReply, AgentReplyKind, ECPAEnvironment, TrustedReceipt
from routebench.defense.freeze import StudySpec
from routebench.defense.policies import PublicRulePolicy
from routebench.defense.study import FrozenStudy
from routebench.runtime.reference import ScenarioState
from routebench.submission.supplement import TransformedPolicy, paraphrase, schedule

ROOT = Path(__file__).parents[2]


def observed() -> Any:
    task = load_development_tasks(ROOT, ROOT / "configs/defense/development-contracts.yaml")[0]
    env = ECPAEnvironment(
        task.public, ScenarioState.from_fixture(task.bundle.root / "fixtures/state.json")
    )
    return asyncio.run(
        env.observe(AgentReply(kind=AgentReplyKind.PROPOSE, edge_id="query_paused_ids"))
    )


def test_fixed_supplement_counts_and_matched_seeds() -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    spec = StudySpec.model_validate(
        yaml.safe_load((ROOT / "configs/defense/study.yaml").read_text())
    )
    study = FrozenStudy("ecpa-test", "a" * 40, spec, tasks, "b" * 64)
    assert [
        len(schedule(study, "E4", split, "path_rule")) for split in ("tune", "calibration", "test")
    ] == [20, 16, 164]
    assert len(schedule(study, "E5", "test", "path_rule")) == 164
    robust = schedule(study, "E6", "test", "path_rule")
    assert len(robust) == 492
    assert {case.arm for case in robust} == {"compact_lora_seed_29", "path_rule", "public_search"}
    for key in {case.pair_key for case in robust}:
        assert len({case.episode_seed for case in robust if case.pair_key == key}) == 1


def test_all_wording_changes_preserve_every_machine_semantic_field() -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    wording = yaml.safe_load((ROOT / "configs/submission/wording-paraphrases.yaml").read_text())
    tested = [task for task in tasks if task.entry.split == "test"]
    assert set(wording["tasks"]) == {task.entry.task_id for task in tested}
    for task in tested:
        transformed = paraphrase(task, wording)
        original = task.public.model_dump(mode="json")
        revised = transformed.public.model_dump(mode="json")
        assert original.pop("prompt") != revised.pop("prompt")
        for left, right in zip(
            original["policy"]["forbidden_effects"],
            revised["policy"]["forbidden_effects"],
            strict=True,
        ):
            assert left.pop("description") != right.pop("description")
        assert original == revised
        assert task.verifier == transformed.verifier and task.authoring == transformed.authoring


def test_menu_display_transform_roundtrips_and_preserves_choice_costs() -> None:
    observation = observed()
    original = observation.model_dump(mode="json")

    class SelectFirst:
        def choose(self, supplied: Any, *, rng: random.Random) -> PolicyChoice:
            assert all(item.candidate_id.startswith("option_") for item in supplied.menu)
            return PolicyChoice(supplied.menu[0].candidate_id, 0.25, 7)

    policy = TransformedPolicy(SelectFirst(), "menu_permutation")
    choice = policy.choose(observation, rng=random.Random(4))
    assert choice.candidate_id in {item.candidate_id for item in observation.menu}
    assert choice.intervention_probability == 0.25 and choice.search_expansions == 7
    assert observation.model_dump(mode="json") == original
    again = policy.choose(observation, rng=random.Random(8))
    assert again == choice
    # Native completion policy's literal deny must also roundtrip.
    completed = observation.model_copy(update={"facts": observation.task.contract.goal_all})
    deny = TransformedPolicy(PublicRulePolicy(), "menu_permutation").choose(
        completed, rng=random.Random(4)
    )
    assert deny.candidate_id == "deny"


def test_receipt_ablation_only_changes_the_supplied_copy() -> None:
    observation = observed().model_copy(
        update={
            "receipts": (
                TrustedReceipt(
                    edge_id="past",
                    request_hash="r",
                    node="n",
                    facts=(),
                    labels=(),
                    approval_epoch=0,
                ),
            )
        }
    )

    class Inspect:
        def choose(self, supplied: Any, *, rng: random.Random) -> PolicyChoice:
            assert supplied.receipts == ()
            for field in type(supplied).model_fields:
                if field != "receipts":
                    assert getattr(supplied, field) == getattr(observation, field)
            return PolicyChoice(supplied.menu[0].candidate_id)

    policy = TransformedPolicy(Inspect(), "no_receipts")
    policy.choose(observation, rng=random.Random(4))
    assert len(observation.receipts) == 1
    assert policy.events[0]["supplied_receipts"] == 0
