"""Serializable contracts for planners, controllers, tools, and traces."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class FrozenDict(dict[str, Any]):
    """A JSON-serializable dictionary that rejects in-place mutation."""

    @staticmethod
    def _immutable(*args: object, **kwargs: object) -> None:
        raise TypeError("protocol values are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __ior__ = _immutable  # type: ignore[assignment]
    clear = _immutable
    pop = _immutable
    popitem = _immutable  # type: ignore[assignment]
    setdefault = _immutable
    update = _immutable


class FrozenList(list[Any]):
    """A JSON-serializable list that rejects in-place mutation."""

    @staticmethod
    def _immutable(*args: object, **kwargs: object) -> None:
        raise TypeError("protocol values are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __iadd__ = _immutable  # type: ignore[assignment]
    __imul__ = _immutable  # type: ignore[assignment]
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value
    if isinstance(value, dict):
        return FrozenDict({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return FrozenList(_deep_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_deep_freeze(item) for item in value)
    return value


class FrozenModel(BaseModel):
    """Immutable base model used by traceable protocol values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def freeze_nested_values(self) -> Self:
        for field_name in type(self).model_fields:
            object.__setattr__(self, field_name, _deep_freeze(getattr(self, field_name)))
        return self

    @property
    def content_hash(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class AttackCondition(StrEnum):
    BENIGN = "benign"
    FIXED = "fixed"
    ADAPTIVE_BLACKBOX = "adaptive_blackbox"
    ADAPTIVE_GRAYBOX = "adaptive_graybox"


class DecisionKind(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVE = "approve"
    REROUTE = "reroute"


class FeedbackMode(StrEnum):
    FULL = "full"
    MINIMAL = "minimal"
    STATUS_ONLY = "status_only"
    NATIVE = "native"


class RiskCategory(StrEnum):
    PRIVACY_ACCESS = "privacy_access"
    DATA_INTEGRITY = "data_integrity"
    EXFILTRATION = "exfiltration"
    PRIVILEGE_CONTROL = "privilege_control"
    SUPPLY_CHAIN = "supply_chain"
    COST_AMPLIFICATION = "cost_amplification"


class RunStatus(StrEnum):
    MAIN_SUCCEEDED = "main_succeeded"
    ATTACK_SUCCEEDED = "attack_succeeded"
    INTERVENED = "intervened"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PLANNER_FINISHED = "planner_finished"
    INVALID = "invalid"
    ERROR = "error"


class EffectSummary(FrozenModel):
    resource: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    target: str = Field(min_length=1)
    sensitivity: str | None = None
    reversible: bool = True


class ActionRequest(FrozenModel):
    action_id: str = Field(min_length=1)
    step: int = Field(ge=0)
    tool: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    raw_output: str | None = None
    effects: tuple[EffectSummary, ...] = ()

    @property
    def action_hash(self) -> str:
        return self.content_hash


class Decision(FrozenModel):
    action_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: DecisionKind
    public_message: str = ""
    private_reason: str | None = None
    replacement: ActionRequest | None = None

    @model_validator(mode="after")
    def validate_replacement(self) -> Self:
        if self.kind is DecisionKind.REROUTE and self.replacement is None:
            raise ValueError("reroute decisions require a replacement action")
        if self.kind is not DecisionKind.REROUTE and self.replacement is not None:
            raise ValueError("only reroute decisions may include a replacement action")
        return self


class ToolResult(FrozenModel):
    action_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ok: bool
    output: JsonValue | None = None
    error_code: str | None = None
    duration_ms: float = Field(ge=0)


class BudgetSpec(FrozenModel):
    max_proposals: int = Field(gt=0)
    max_tool_executions: int = Field(gt=0)
    max_model_tokens: int = Field(gt=0)
    max_wall_seconds: int = Field(gt=0)
    max_consecutive_denials: int = Field(gt=0)


class PlannedActionRequirement(FrozenModel):
    """One prior action required before a planned action can execute."""

    tool: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class PlannedAction(FrozenModel):
    """A controller-visible action committed as part of an attack program."""

    tool: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    requires_prior_actions: tuple[PlannedActionRequirement, ...] = ()


class AttackStep(FrozenModel):
    step_id: str = Field(min_length=1)
    primitive: str = Field(min_length=1)
    target: str = Field(min_length=1)
    prerequisites: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    action: PlannedAction | None = None


class AttackProgram(FrozenModel):
    goal: str = Field(min_length=1)
    steps: tuple[AttackStep, ...]
    parent_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    committed_at_step: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("attack step IDs must be unique")
        known = set(step_ids)
        for step in self.steps:
            unknown = (set(step.prerequisites) | set(step.alternatives)) - known
            if unknown:
                raise ValueError(
                    f"attack step {step.step_id!r} references unknown steps: {unknown}"
                )
        return self


class PlannerContext(FrozenModel):
    run_id: str = Field(min_length=1)
    condition: AttackCondition
    task_prompt: str = Field(min_length=1)
    observations: tuple[JsonValue, ...] = ()
    proposals_used: int = Field(ge=0)
    tokens_used: int = Field(ge=0)


class GraphPathSelection(FrozenModel):
    """An ordered path selected from an evaluator-provided candidate graph."""

    edge_ids: tuple[str, ...] = Field(min_length=1)


class GraphStepSelection(FrozenModel):
    """One next edge selected while executing a previously committed graph path."""

    edge_id: str = Field(min_length=1)


class GraphExecutionReceipt(FrozenModel):
    """Value-free execution status returned to an online graph planner."""

    step: int = Field(ge=0)
    edge_id: str = Field(min_length=1)
    decision: DecisionKind
    executed: bool


class TraceEvent(FrozenModel):
    sequence: int = Field(ge=0)
    event_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
