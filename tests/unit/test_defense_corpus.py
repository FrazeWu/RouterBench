from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from routebench.defense.compact import selector_messages
from routebench.defense.corpus import audit_task, load_corpus, readiness, replay_prefix
from routebench.defense.ecpa import AgentReply, AgentReplyKind

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "configs/defense/independent-corpus.yaml"
SPEC = importlib.util.spec_from_file_location(
    "validate_capability_universe", ROOT / "scripts/validate_capability_universe.py"
)
assert SPEC is not None and SPEC.loader is not None
UNIVERSE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UNIVERSE)


def test_independent_tasks_execute_safe_alternatives_and_reproduce_harm_only_in_reference() -> None:
    spec, tasks = load_corpus(ROOT, MANIFEST)
    catalog = UNIVERSE.load_catalog(ROOT / "catalog/capability_universe.yaml")

    async def run() -> None:
        coverage: set[str] = set()
        for task in tasks:

            def validate(binding: dict[str, object]) -> None:
                UNIVERSE.validate_binding_selection(catalog, binding)

            row = await audit_task(
                task,
                validate_binding=validate,
            )
            assert row["safe_paths_checked"] == 2
            assert isinstance(row["attack_prefix_actions"], int)
            assert row["attack_prefix_actions"] >= 2
            assert row["attack_target_and_violation_reproduced"]
            assert row["model_rollouts"] == row["training_labels"] == 0
            counts = row["menu_probe_counts"]
            assert isinstance(counts, dict)
            coverage.update(counts)
        assert coverage == {"allow", "constrain", "escalate", "deny"}

    asyncio.run(run())
    report = readiness(spec, tasks)
    assert report["formal_run_ready"] is False
    assert report["authored_families"] == {"train": 12, "tune": 4, "calibration": 4, "test": 2}
    assert report["task_counts"] == {"train": 12, "tune": 5, "calibration": 4, "test": 2}
    assert report["reviewed_families"] == {"train": 0, "tune": 0, "calibration": 0, "test": 0}


def _copy_sources(tmp_path: Path) -> Path:
    (tmp_path / "configs/defense").mkdir(parents=True)
    manifest = tmp_path / "configs/defense/independent-corpus.yaml"
    shutil.copy(MANIFEST, manifest)
    shutil.copytree(ROOT / "scenarios/defense", tmp_path / "scenarios/defense")
    return manifest


def test_family_review_count_requires_every_task_in_a_consolidated_family() -> None:
    spec, tasks = load_corpus(ROOT, MANIFEST)
    family = "two_scope_approved_change"
    members = [index for index, task in enumerate(tasks) if task.entry.semantic_family == family]
    assert len(members) == 2
    updated = list(tasks)
    for completed, index in enumerate(members, start=1):
        updated[index] = replace(
            updated[index],
            entry=updated[index].entry.model_copy(
                update={"independent_review": "accepted", "review_evidence": "reviewed-source.md"}
            ),
        )
        report = readiness(spec, tuple(updated))
        assert report["reviewed_families"] == {
            "train": 0,
            "tune": int(completed == len(members)),
            "calibration": 0,
            "test": 0,
        }
        assert report["formal_run_ready"] is False


def test_private_sources_change_identity_without_entering_model_input(tmp_path: Path) -> None:
    manifest = _copy_sources(tmp_path)
    _, before = load_corpus(tmp_path, manifest)
    path = before[0].directory / "authoring.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["semantic_rationale"] += " PRIVATE_REVIEW_SENTINEL"
    path.write_text(yaml.safe_dump(raw))
    _, after = load_corpus(tmp_path, manifest)
    assert before[0].digest != after[0].digest
    assert before[0].public.digest == after[0].public.digest

    async def run() -> None:
        env = await replay_prefix(after[0], ())
        obs = await env.observe(
            AgentReply(kind=AgentReplyKind.PROPOSE, edge_id=after[0].public.graph.edges[0].edge_id)
        )
        assert obs is not None
        messages = json.dumps(selector_messages(obs))
        assert "PRIVATE_REVIEW_SENTINEL" not in messages
        assert all(key not in messages for key in ("safe_paths", "attack_path", "verifier"))

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation", ["pilot", "family", "mechanism", "unregistered_mechanism", "review", "duplicate"]
)
def test_corpus_rejects_contamination_and_unsubstantiated_review(
    tmp_path: Path, mutation: str
) -> None:
    manifest = _copy_sources(tmp_path)
    raw = yaml.safe_load(manifest.read_text())
    first = raw["entries"][0]
    if mutation == "pilot":
        first["semantic_family"] = "inventory_dataflow"
    elif mutation == "family":
        first["semantic_family"] = "silently_renamed_family"
    elif mutation == "mechanism":
        raw["entries"][1]["split"] = "test"
    elif mutation == "unregistered_mechanism":
        first["attack_mechanism"] = "only_renamed_payload"
    elif mutation == "review":
        first["independent_review"] = "accepted"
    else:
        raw["entries"].append(first)
    manifest.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        load_corpus(tmp_path, manifest)


def test_safe_path_checks_fail_when_public_contract_claims_success_too_early() -> None:
    _, tasks = load_corpus(ROOT, MANIFEST)
    task = tasks[0]
    # A plausible graph terminal/public fact cannot replace the real verifier.
    graph = task.public.graph.model_copy(update={"terminal_nodes": ("observed", "harm")})
    contract = task.public.contract.model_copy(update={"goal_all": ("settlement_observed",)})
    public = task.public.model_copy(update={"graph": graph, "contract": contract})
    authoring = task.authoring.model_copy(
        update={"safe_paths": (("inspect_settlement",), ("inspect_settlement", "save_evidence"))}
    )

    async def run() -> None:
        with pytest.raises(ValueError, match="hidden evaluator"):
            await audit_task(
                replace(task, public=public, authoring=authoring), validate_binding=lambda _: None
            )

    asyncio.run(run())
