"""Frozen-study identity, metered calls and private training collection.

The kernels are not evidence of a run. The CLI validates the frozen source and
real local snapshots before connecting to the declared task-model endpoint.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from routebench.defense.agent import JsonRecoveryAgent, RecoveryAgentConfig, agent_messages
from routebench.defense.branching import RecordedRollout, collect_parent_branches
from routebench.defense.compact import INPUT_SCHEMA, ContextOverflow, selector_messages
from routebench.defense.contracts import content_hash
from routebench.defense.corpus import CorpusTask, load_corpus, readiness, source_path
from routebench.defense.development import SimulatedApprover
from routebench.defense.ecpa import AgentView, ECPAEnvironment
from routebench.defense.evaluation import episode_metrics
from routebench.defense.freeze import StudySpec, validate_freeze_sources
from routebench.defense.lora import BranchGroup, file_digest, model_fingerprint, prepare_choices
from routebench.defense.pilot import clean_revision
from routebench.defense.policies import MixtureLoggingPolicy
from routebench.defense.protocol import AcquisitionLedger
from routebench.defense.relay import StagedResponseRelay
from routebench.defense.traces import build_transitions

AcquisitionPurpose = Literal["diagnostic", "rollout", "branch"]


def private_output(root: Path, output: Path) -> Path:
    output = output.resolve()
    if not output.is_relative_to(root.resolve() / "artifacts/private"):
        raise ValueError("study outputs must remain under ignored artifacts/private")
    return output


def write_exclusive(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


@dataclass(frozen=True)
class FrozenStudy:
    protocol_id: str
    revision: str
    spec: StudySpec
    tasks: tuple[CorpusTask, ...]
    manifest_digest: str


def load_frozen_study(root: Path, path: Path) -> FrozenStudy:
    """Reject changed sources/configuration/model bytes, including ignored files."""
    root = root.resolve()
    revision = clean_revision(root)
    payload = json.loads(path.read_text())
    body = {key: value for key, value in payload.items() if key != "protocol_id"}
    if payload.get("protocol_id") != "ecpa-" + content_hash(body):
        raise ValueError("frozen manifest protocol identity mismatch")
    if payload.get("source_revision") != revision or payload.get("input_schema") != INPUT_SCHEMA:
        raise ValueError("frozen study requires its exact clean source revision and input schema")
    spec = StudySpec.model_validate(payload["study"])
    config = source_path(root, payload["configuration_source"])
    if StudySpec.model_validate(yaml.safe_load(config.read_text())) != spec:
        raise ValueError("frozen study differs from the checked-in configuration")
    if not payload.get("source_files") or any(
        file_digest(source_path(root, name)) != digest
        for name, digest in payload["source_files"].items()
    ):
        raise ValueError("frozen source file identity mismatch")
    corpus, tasks = load_corpus(root, root / spec.corpus_manifest)
    validate_freeze_sources(root, corpus, tasks)
    if payload.get("corpus_digest") != readiness(corpus, tasks)["corpus_digest"] or payload.get(
        "task_digests"
    ) != {task.entry.task_id: task.digest for task in tasks}:
        raise ValueError("frozen corpus identity mismatch")
    if payload.get("model_fingerprints") != {
        "task_agent": model_fingerprint(spec.task_model_path),
        "compact_defender": model_fingerprint(spec.compact.model_path),
    }:
        raise ValueError("frozen local model snapshot changed")
    if clean_revision(root) != revision:
        raise ValueError("source changed while validating frozen study")
    return FrozenStudy(payload["protocol_id"], revision, spec, tasks, content_hash(payload))


class MeteredStudyAgent(JsonRecoveryAgent):
    """Meter every HTTP call, including text drafts, receivers and acceptances.

    Reserve the full frozen context before a request; reconcile only valid
    reported usage. Missing usage or failed calls retain that reservation. No
    response is truncated, retried or substituted to satisfy an acquisition cap.
    """

    def __init__(
        self,
        config: RecoveryAgentConfig,
        *,
        tokenizer: Any,
        ledger: AcquisitionLedger,
        acquisition_purpose: AcquisitionPurpose,
        before_call: Callable[[], None],
        after_call: Callable[[], None],
        record_call: Callable[[dict[str, object]], None],
        **kwargs: Any,
    ) -> None:
        super().__init__(config, **kwargs)
        self.tokenizer, self.ledger = tokenizer, ledger
        self.acquisition_purpose = acquisition_purpose
        self.before_call, self.after_call = before_call, after_call
        self.record_call = record_call

    async def _complete(
        self,
        view: AgentView,
        *,
        seed: int,
        purpose: str | None = None,
        relayed_text: str | None = None,
        charge: Callable[[], None],
    ) -> str:
        tokens = self.tokenizer.apply_chat_template(
            agent_messages(view, relayed_text),
            tokenize=True,
            return_dict=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        if len(tokens) + self.config.max_completion_tokens > self.config.context_tokens:
            raise ContextOverflow("task-agent context exceeded; no truncation is permitted")
        self.before_call()
        charge()
        identifier = self.ledger.reserve(self.acquisition_purpose, self.config.context_tokens)
        previous = len(self.calls)
        try:
            return await super()._complete(
                view,
                seed=seed,
                purpose=purpose,
                relayed_text=relayed_text,
                charge=lambda: None,
            )
        finally:
            call = self.calls[-1] if len(self.calls) > previous else None
            usage = (
                call.prompt_tokens + call.completion_tokens
                if call is not None and call.usage_reported
                else None
            )
            invalid = usage is not None and (
                usage > self.config.context_tokens
                or call is None
                or call.completion_tokens > self.config.max_completion_tokens
            )
            self.ledger.reconcile(identifier, None if invalid else usage)
            self.record_call(
                {
                    "reservation_id": identifier,
                    "acquisition_purpose": self.acquisition_purpose,
                    "local_prompt_tokens": len(tokens),
                    "maximum_reserved_tokens": self.config.context_tokens,
                    "charged_tokens": (
                        self.config.context_tokens if usage is None or invalid else usage
                    ),
                    "invalid_reported_usage": invalid,
                    "call": call.model_dump(mode="json") if call else None,
                }
            )
            self.after_call()
            if invalid:
                raise ValueError("endpoint usage exceeds the frozen request reservation")


def rollout_record(rollout: RecordedRollout) -> dict[str, object]:
    episode = rollout.episode
    executed = {step.selected.edge_id for step in episode.steps if step.dispatched}
    events = [
        {**event, "target_dispatched_in_this_continuation": event["target_edge_id"] in executed}
        for event in rollout.relay_events[rollout.relay_event_offset :]
    ]
    return {
        "metrics": episode_metrics(episode),
        "calls": [call.model_dump(mode="json") for call in rollout.calls],
        "transitions": [row.model_dump(mode="json") for row in build_transitions(episode)],
        "final_state": episode.final_state,
        "relay_events": events,
        "inherited_relay_events": list(rollout.relay_events[: rollout.relay_event_offset]),
        "relay_stages_reached_in_this_continuation": len(events),
        "relay_substitutions_in_this_continuation": sum(bool(event["changed"]) for event in events),
        "relay_targets_dispatched_in_this_continuation": sum(
            bool(event["target_dispatched_in_this_continuation"]) for event in events
        ),
    }


def training_coverage(
    groups: Sequence[BranchGroup], study: FrozenStudy
) -> tuple[list[BranchGroup], dict[str, object]]:
    """Deduplicate by public input before labels; never choose by branch outcomes."""
    seen: set[str] = set()
    selected, duplicate_ids = [], []
    if len({group.group_id for group in groups}) != len(groups):
        raise ValueError("duplicate branch group IDs")
    for group in groups:
        if group.split != "train" or group.formal_protocol_id != study.protocol_id:
            raise ValueError("coverage accepts only training groups from the frozen protocol")
        key = content_hash([selector_messages(group.observation), group.attack_mechanism])
        if key in seen:
            duplicate_ids.append(group.group_id)
        else:
            seen.add(key)
            selected.append(group)
    counts = dict.fromkeys(study.spec.required_training_target_kinds, 0)
    audit: dict[str, object] = {"groups": len(selected), "examples": 0, "skipped": 0, "ties": 0}
    if selected:
        try:
            examples, preparation = prepare_choices(selected, formal_protocol_id=study.protocol_id)
        except ValueError as error:
            if str(error) != "no complete uncensored menu-branch comparisons":
                raise
            audit["skipped"] = len(selected)
        else:
            audit.update(preparation)
            for example in examples:
                candidate = next(
                    item
                    for item in example.observation.menu
                    if item.candidate_id == example.candidate_id
                )
                counts[candidate.kind.value] += 1
    return selected, {
        **audit,
        "duplicate_group_ids": duplicate_ids,
        "deduplication": "first_scheduled_public_input_and_condition_before_outcomes",
        "realized_target_kind_counts": counts,
        "fit_ready": all(count > 0 for count in counts.values()),
    }


async def collect_training(
    study: FrozenStudy,
    output: Path,
    agent_factory: Callable[[AcquisitionPurpose, StagedResponseRelay], JsonRecoveryAgent],
) -> dict[str, object]:
    """Collection kernel; caller validates the source, endpoint and runtime limits."""
    output.mkdir(exist_ok=False)
    tasks = tuple(task for task in study.tasks if task.entry.split == "train")
    if not tasks:
        raise ValueError("training collection requires training sources")
    groups: list[BranchGroup] = []
    cases: list[dict[str, Any]] = []
    common = {"source_revision": study.revision, "formal_protocol_id": study.protocol_id}
    for task in tasks:
        for mode in study.spec.modes:
            for attacked in (False, True):
                case_index = len(cases)
                identity = {"task_id": task.entry.task_id, "mode": mode, "attacked": attacked}
                case_id = "case-" + content_hash(identity)[:20]
                relay = StagedResponseRelay(task.relay_campaign(), mode=mode, attacked=attacked)
                agent_count = 0

                def factory(current_relay: StagedResponseRelay) -> JsonRecoveryAgent:
                    nonlocal agent_count
                    purpose: AcquisitionPurpose = "rollout" if agent_count == 0 else "branch"
                    agent_count += 1
                    return agent_factory(purpose, current_relay)

                def record(
                    key: str,
                    rollout: RecordedRollout,
                    bound_case: str = case_id,
                    bound_identity: dict[str, Any] = identity,
                ) -> None:
                    write_exclusive(
                        output / f"{bound_case}-{content_hash(key)[:20]}.rollout.private.json",
                        {**common, **bound_identity, "rollout_key": key, **rollout_record(rollout)},
                    )

                result = await collect_parent_branches(
                    ECPAEnvironment(
                        task.public,
                        task.state(),
                        budgets=study.spec.budgets,
                        approval_provider=SimulatedApprover(),
                    ),
                    relay,
                    factory,
                    MixtureLoggingPolicy(uniform_weight=study.spec.logging_uniform_weight),
                    evaluator=task.outcome,
                    seed=study.spec.episode_seed + case_index,
                    state_selection_seed=study.spec.state_selection_seed + case_index,
                    continuation_seed=(
                        study.spec.continuation_seed + case_index * study.spec.branch_repeats
                    ),
                    maximum_states=study.spec.maximum_branch_states_per_parent,
                    repeats=study.spec.branch_repeats,
                    proposal_sampling_probability=1.0,
                    record_rollout=record,
                )
                case_groups = []
                for comparison in result.comparisons:
                    group = BranchGroup(
                        group_id=f"{case_id}-state-{comparison.encountered_index}",
                        observation=comparison.observation,
                        semantic_family=task.entry.semantic_family,
                        attack_mechanism=relay.effective_mechanism if attacked else "benign",
                        split="train",
                        source_revision=study.revision,
                        formal_protocol_id=study.protocol_id,
                        proposal_sampling_probability=1.0,
                        state_inclusion_probability=comparison.state_inclusion_probability,
                        branch_assignment_probability=comparison.branch_assignment_probability,
                        outcomes=tuple(branch.outcome for branch in comparison.branches),
                    )
                    filename = f"{group.group_id}.group.private.json"
                    write_exclusive(output / filename, group.model_dump(mode="json"))
                    groups.append(group)
                    case_groups.append(filename)
                cases.append(
                    {
                        **identity,
                        "case_id": case_id,
                        "groups": case_groups,
                        "encountered_choice_states": result.encountered_choice_states,
                        "task_source_digest": task.digest,
                    }
                )
    selected, coverage = training_coverage(groups, study)
    files = {path.name: file_digest(path) for path in sorted(output.iterdir()) if path.is_file()}
    summary = {
        **common,
        "purpose": "formal_train_collection",
        "status": "complete",
        "frozen_manifest_digest": study.manifest_digest,
        "training_acquisition": study.spec.training_acquisition,
        "cases": cases,
        "selected_group_ids": [group.group_id for group in selected],
        "coverage": coverage,
        "files": files,
        "efficacy_evidence": False,
    }
    write_exclusive(output / "collection.json", summary)
    return summary


def load_training_collection(path: Path, study: FrozenStudy) -> list[BranchGroup]:
    report = json.loads((path / "collection.json").read_text())
    if any(
        report.get(key) != value
        for key, value in {
            "purpose": "formal_train_collection",
            "status": "complete",
            "source_revision": study.revision,
            "formal_protocol_id": study.protocol_id,
            "frozen_manifest_digest": study.manifest_digest,
            "training_acquisition": study.spec.training_acquisition,
        }.items()
    ):
        raise ValueError("training collection requires matching completed frozen provenance")
    expected = Counter(
        (task.entry.task_id, mode, attacked)
        for task in study.tasks
        if task.entry.split == "train"
        for mode in study.spec.modes
        for attacked in (False, True)
    )
    actual = Counter((row["task_id"], row["mode"], row["attacked"]) for row in report["cases"])
    if actual != expected:
        raise ValueError("training collection does not cover the frozen case schedule")
    for name, digest in report["files"].items():
        if Path(name).name != name or file_digest(path / name) != digest:
            raise ValueError("training collection artifact integrity mismatch")
    groups = []
    ordered_cases = [
        (task.entry.task_id, mode, attacked)
        for task in study.tasks
        if task.entry.split == "train"
        for mode in study.spec.modes
        for attacked in (False, True)
    ]
    if [(row["task_id"], row["mode"], row["attacked"]) for row in report["cases"]] != ordered_cases:
        raise ValueError("training cases must retain their prespecified schedule order")
    for case_index, case in enumerate(report["cases"]):
        task = next(task for task in study.tasks if task.entry.task_id == case["task_id"])
        if case["task_source_digest"] != task.digest:
            raise ValueError("training collection task identity mismatch")
        count = case["encountered_choice_states"]
        expected_case_id = (
            "case-"
            + content_hash(
                {"task_id": case["task_id"], "mode": case["mode"], "attacked": case["attacked"]}
            )[:20]
        )
        if case["case_id"] != expected_case_id or type(count) is not int or count < 0:
            raise ValueError("training case identity or state count is invalid")
        expected_indices = sorted(
            random.Random(study.spec.state_selection_seed + case_index).sample(
                range(count), min(count, study.spec.maximum_branch_states_per_parent)
            )
        )
        expected_names = [
            f"{case['case_id']}-state-{index}.group.private.json" for index in expected_indices
        ]
        if case["groups"] != expected_names:
            raise ValueError("training groups must cover every uniformly sampled state")
        for name in case["groups"]:
            if name not in report["files"] or not name.endswith(".group.private.json"):
                raise ValueError("training group is not bound by the collection file ledger")
            group = BranchGroup.model_validate_json((path / name).read_text())
            expected_mechanism = (
                (
                    "registered_proposal_substitution"
                    if case["mode"] == "structured"
                    else task.entry.attack_mechanism
                )
                if case["attacked"]
                else "benign"
            )
            if (
                name != f"{group.group_id}.group.private.json"
                or group.source_revision != study.revision
                or group.formal_protocol_id != study.protocol_id
                or group.split != "train"
                or group.observation.task != task.public
                or group.semantic_family != task.entry.semantic_family
                or group.attack_mechanism != expected_mechanism
                or group.proposal_sampling_probability != 1.0
                or group.state_inclusion_probability
                != min(1.0, study.spec.maximum_branch_states_per_parent / count)
            ):
                raise ValueError("training group source differs from the frozen task")
            keys = {(row.candidate_id, row.repeat, row.continuation_seed) for row in group.outcomes}
            expected_keys = {
                (
                    item.candidate_id,
                    repeat,
                    study.spec.continuation_seed + case_index * study.spec.branch_repeats + repeat,
                )
                for item in group.observation.menu
                for repeat in range(study.spec.branch_repeats)
            }
            if len(keys) != len(group.outcomes) or keys != expected_keys:
                raise ValueError(
                    "training outcomes must cover the exact frozen menu/repeat schedule"
                )
            groups.append(group)
    selected, coverage = training_coverage(groups, study)
    if (
        report["selected_group_ids"] != [group.group_id for group in selected]
        or report["coverage"] != coverage
    ):
        raise ValueError("training selection/coverage differs from actual branch groups")
    if coverage["fit_ready"] is not True:
        raise ValueError("realized complete-menu training targets lack a prespecified kind")
    return selected


def load_training_phase(path: Path, study: FrozenStudy) -> list[BranchGroup]:
    """Completed collection bytes alone do not certify a successful measured phase."""
    phase = json.loads((path.parent / "phase-result.json").read_text())
    if any(
        phase.get(key) != value
        for key, value in {
            "phase": "collect",
            "status": "complete",
            "error_kind": None,
            "source_revision": study.revision,
            "formal_protocol_id": study.protocol_id,
        }.items()
    ):
        raise ValueError("fitting requires a completed, thermally valid collection phase")
    bound_files = phase.get("collection_files", {})
    actual_files = {
        str(file.relative_to(path)): file_digest(file)
        for file in sorted(path.rglob("*"))
        if file.is_file()
    }
    if not bound_files or bound_files != actual_files:
        raise ValueError("completed collection phase file integrity mismatch")
    return load_training_collection(path, study)
