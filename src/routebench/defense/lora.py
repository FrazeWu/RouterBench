"""Outcome-derived menu-choice supervision, answer-only LoRA, and provenance."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import random
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import Field

from routebench.defense.compact import (
    INPUT_SCHEMA,
    CompactConfig,
    answer_training_ids,
    selector_messages,
    write_json,
)
from routebench.defense.contracts import content_hash
from routebench.defense.ecpa import DefenseObservation
from routebench.defense.policies import PublicRulePolicy
from routebench.scenarios.schema import StrictModel


class BranchOutcome(StrictModel):
    candidate_id: str
    repeat: int = Field(ge=0)
    continuation_seed: int
    terminated: bool
    truncated: bool
    safe_completion: bool | None
    violation: bool | None
    cost: float | None = Field(ge=0)
    termination_reason: str | None


class BranchGroup(StrictModel):
    group_id: str
    observation: DefenseObservation
    semantic_family: str
    attack_mechanism: str
    split: Literal["development", "train", "tune", "calibration", "test"]
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    formal_protocol_id: str | None = Field(default=None, pattern=r"^ecpa-[a-z0-9][a-z0-9._-]*$")
    branch_assignment_probability: float = Field(default=1.0, ge=1, le=1)
    proposal_sampling_probability: float = Field(gt=0, le=1)
    outcomes: tuple[BranchOutcome, ...]


class ChoiceExample(StrictModel):
    group_id: str
    observation: DefenseObservation
    candidate_id: str


class LoraSpec(StrictModel):
    seed: int = 29
    updates: int = Field(default=8, gt=0)
    gradient_accumulation: int = Field(default=1, gt=0)
    learning_rate: float = Field(default=1e-4, gt=0)
    rank: int = Field(default=8, gt=0)
    alpha: int = Field(default=16, gt=0)
    dropout: float = Field(default=0.0, ge=0, lt=1)
    target_modules: tuple[str, ...] = ("q_proj", "v_proj")


def prepare_choices(
    groups: Sequence[BranchGroup],
    *,
    development_smoke: bool = False,
    formal_protocol_id: str | None = None,
) -> tuple[list[ChoiceExample], dict[str, int]]:
    if not groups:
        raise ValueError("no actual branch groups supplied")
    if development_smoke:
        if formal_protocol_id is not None or any(
            item.split != "development" or item.formal_protocol_id is not None for item in groups
        ):
            raise ValueError("development fitting requires only unbound development branches")
    elif formal_protocol_id is None or any(
        item.split != "train" or item.formal_protocol_id != formal_protocol_id for item in groups
    ):
        raise ValueError("formal fitting requires training branches bound to the matching protocol")
    if len({item.group_id for item in groups}) != len(groups):
        raise ValueError("duplicate branch group IDs")
    # A differently named copy of one observed decision is not independent data.
    state_keys = [
        (content_hash(selector_messages(item.observation)), item.attack_mechanism)
        for item in groups
    ]
    if len(set(state_keys)) != len(state_keys):
        raise ValueError("duplicate observed public states")
    examples = []
    skipped = 0
    ties = 0
    for group in groups:
        if group.semantic_family != group.observation.task.contract.semantic_family:
            raise ValueError("branch family does not match its public task")
        menu = {item.candidate_id for item in group.observation.menu}
        by_candidate: dict[str, list[BranchOutcome]] = defaultdict(list)
        keys = [(item.candidate_id, item.repeat) for item in group.outcomes]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate candidate/repeat branch")
        if any(item.candidate_id not in menu for item in group.outcomes):
            raise ValueError("branch outcome is outside the legal menu")
        for row in group.outcomes:
            by_candidate[row.candidate_id].append(row)
        repeats = {row.repeat for row in group.outcomes}
        complete = (
            bool(repeats)
            and set(by_candidate) == menu
            and all({row.repeat for row in values} == repeats for values in by_candidate.values())
        )
        for repeat in repeats:
            if len({row.continuation_seed for row in group.outcomes if row.repeat == repeat}) != 1:
                raise ValueError("candidate branches must share a continuation seed per repeat")
        if not complete or any(
            row.truncated
            or not row.terminated
            or row.safe_completion is None
            or row.violation is None
            or row.cost is None
            for row in group.outcomes
        ):
            # Never compare a completed subset against a censored/absent action.
            skipped += 1
            continue
        if any(row.safe_completion and row.violation for row in group.outcomes):
            raise ValueError("safe completion cannot coexist with an episode violation")
        ranks = {
            candidate: (
                sum(bool(row.violation) for row in values) / len(values),
                -sum(bool(row.safe_completion) for row in values) / len(values),
                sum(float(row.cost) for row in values if row.cost is not None) / len(values),
            )
            for candidate, values in by_candidate.items()
        }
        winners = sorted(
            candidate for candidate, rank in ranks.items() if rank == min(ranks.values())
        )
        ties += int(len(winners) > 1)
        rule = PublicRulePolicy().choose(group.observation, rng=random.Random(0)).candidate_id
        target = rule if rule in winners else winners[0]
        examples.append(
            ChoiceExample(
                group_id=group.group_id, observation=group.observation, candidate_id=target
            )
        )
    if not examples:
        raise ValueError("no complete uncensored menu-branch comparisons")
    return examples, {
        "groups": len(groups),
        "examples": len(examples),
        "skipped": skipped,
        "ties": ties,
    }


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def model_fingerprint(model_path: str) -> str:
    root = Path(model_path)
    files = sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix in {".json", ".safetensors", ".jinja", ".txt"}
    )
    if not any(path.suffix == ".safetensors" for path in files):
        raise ValueError("a complete local safetensors model snapshot is required")
    return content_hash({path.name: file_digest(path) for path in files})


def validate_adapter(
    adapter: Path,
    config: CompactConfig,
    *,
    allow_development: bool = False,
    expected_protocol_id: str | None = None,
) -> dict[str, object]:
    manifest = json.loads((adapter / "manifest.json").read_text())
    if manifest["development_smoke"]:
        if (
            not allow_development
            or expected_protocol_id is not None
            or manifest["formal_protocol_id"]
        ):
            raise ValueError("development adapter is forbidden in formal evaluation")
    elif expected_protocol_id is None or manifest["formal_protocol_id"] != expected_protocol_id:
        raise ValueError("adapter requires the matching frozen formal protocol identity")
    if manifest["input_schema"] != INPUT_SCHEMA:
        raise ValueError("adapter input schema mismatch")
    recorded = CompactConfig.model_validate(manifest["config"])
    if (recorded.context_tokens, recorded.max_new_tokens) != (
        config.context_tokens,
        config.max_new_tokens,
    ):
        raise ValueError("adapter context/decoding configuration mismatch")
    if manifest["base_fingerprint"] != model_fingerprint(config.model_path):
        raise ValueError("adapter base model snapshot mismatch")
    hashes = manifest["adapter_files"]
    if set(hashes) != {"adapter_config.json", "adapter_model.safetensors"}:
        raise ValueError("adapter manifest lacks its required integrity hashes")
    if any(file_digest(adapter / name) != digest for name, digest in hashes.items()):
        raise ValueError("adapter artifact integrity check failed")
    return dict(manifest)


def train_lora(
    groups: Sequence[BranchGroup],
    config: CompactConfig,
    spec: LoraSpec,
    output: Path,
    *,
    source_revision: str,
    development_smoke: bool = False,
    formal_protocol_id: str | None = None,
    check: Callable[[], None] | None = None,
    after_update: Callable[[], None] | None = None,
) -> dict[str, object]:
    import torch  # type: ignore[import-not-found]
    from peft import LoraConfig, get_peft_model  # type: ignore[import-not-found]
    from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore[import-not-found]

    examples, audit = prepare_choices(
        groups, development_smoke=development_smoke, formal_protocol_id=formal_protocol_id
    )
    started = time.perf_counter()
    base_fingerprint = model_fingerprint(config.model_path)
    tokenizer = AutoTokenizer.from_pretrained(config.model_path, local_files_only=True)
    encoded = [
        answer_training_ids(
            tokenizer, item.observation, item.candidate_id, context_tokens=config.context_tokens
        )
        for item in examples
    ]
    # Check all inputs before allocating the model or creating a partial artifact.
    output.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(spec.seed)
    if config.device.startswith("cuda"):
        torch.cuda.init()
        torch.cuda.reset_peak_memory_stats(config.device)
    base = AutoModelForCausalLM.from_pretrained(
        config.model_path,
        local_files_only=True,
        torch_dtype=torch.bfloat16 if config.device.startswith("cuda") else torch.float32,
        attn_implementation="sdpa",
    ).to(config.device)
    model = get_peft_model(
        base,
        LoraConfig(
            task_type="CAUSAL_LM",
            r=spec.rank,
            lora_alpha=spec.alpha,
            lora_dropout=spec.dropout,
            target_modules=list(spec.target_modules),
        ),
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model.train()
    trainable = [(name, value) for name, value in model.named_parameters() if value.requires_grad]
    if not trainable or any("lora_" not in name for name, _ in trainable):
        raise ValueError("only LoRA parameters may be trainable")
    initial = {name: value.detach().cpu().clone() for name, value in trainable}
    optimizer = torch.optim.AdamW([value for _, value in trainable], lr=spec.learning_rate)
    rng = random.Random(spec.seed)
    losses: list[float] = []
    fit_started = time.perf_counter()
    processed_tokens = answer_tokens = 0
    for _ in range(spec.updates):
        optimizer.zero_grad(set_to_none=True)
        step_loss = 0.0
        for _ in range(spec.gradient_accumulation):
            if check is not None:
                check()
            ids, labels = rng.choice(encoded)
            processed_tokens += len(ids)
            answer_tokens += sum(token != -100 for token in labels)
            inputs = torch.tensor([ids], device=config.device)
            result = model(
                input_ids=inputs,
                attention_mask=torch.ones_like(inputs),
                labels=torch.tensor([labels], device=config.device),
                use_cache=False,
            )
            loss = result.loss / spec.gradient_accumulation
            if not torch.isfinite(loss):
                raise ValueError("non-finite training loss")
            loss.backward()
            step_loss += float(loss.detach().cpu())
        torch.nn.utils.clip_grad_norm_([value for _, value in trainable], 1.0)
        optimizer.step()
        if after_update is not None:
            after_update()
        losses.append(step_loss)
    if not any(not torch.equal(initial[name], value.detach().cpu()) for name, value in trainable):
        raise ValueError("adapter parameters did not change")
    model.save_pretrained(output, safe_serialization=True)
    measurement: dict[str, object] = {
        "fit_seconds": time.perf_counter() - fit_started,
        "total_seconds": time.perf_counter() - started,
        "peak_allocated_bytes": (
            torch.cuda.max_memory_allocated(config.device)
            if config.device.startswith("cuda")
            else 0
        ),
        "peak_reserved_bytes": (
            torch.cuda.max_memory_reserved(config.device) if config.device.startswith("cuda") else 0
        ),
        "trainable_parameters": sum(value.numel() for _, value in trainable),
        "input_tokens_min_max": [
            min(len(ids) for ids, _ in encoded),
            max(len(ids) for ids, _ in encoded),
        ],
        "updates": spec.updates,
        "input_tokens_processed": processed_tokens,
        "answer_tokens_with_loss": answer_tokens,
        "losses": losses,
        "efficacy_evidence": False,
    }
    manifest = {
        "source_revision": source_revision,
        "development_smoke": development_smoke,
        "formal_protocol_id": formal_protocol_id,
        "input_schema": INPUT_SCHEMA,
        "config": config.model_dump(mode="json"),
        "spec": spec.model_dump(mode="json"),
        "base_fingerprint": base_fingerprint,
        "source_group_hashes": {
            item.group_id: content_hash(item.model_dump(mode="json")) for item in groups
        },
        "data_source_revisions": sorted({item.source_revision for item in groups}),
        "data_audit": audit,
        "packages": {
            name: importlib.metadata.version(name) for name in ("torch", "transformers", "peft")
        },
        "adapter_files": {
            name: file_digest(output / name)
            for name in ("adapter_config.json", "adapter_model.safetensors")
        },
    }
    write_json(output / "manifest.json", manifest)
    write_json(output / "measurement.json", measurement)
    return measurement
