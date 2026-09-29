"""Strict, local-only planner configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float = Field(ge=0, le=2)
    top_p: float = Field(gt=0, le=1)
    max_tokens: int = Field(gt=0)
    context_window: int | None = Field(default=None, ge=4096)


class PlannerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=2)
    backend: Literal["ollama", "vllm", "responses"]
    model: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    api_key_env: str | None = Field(default=None, min_length=1)
    generation: GenerationConfig
    formal_run: bool
    disable_thinking: bool = False
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    service_tier: Literal["auto", "default", "flex", "priority", "fast"] | None = None
    vllm_object_only_schema: bool = False
    anonymize_graph_labels: bool = False
    graph_presentation_seeded_permutation: bool = False
    graph_difficulty_contract: Literal["base_v4", "v2", "v3-dev"] | None = None
    graph_selection_interface: Literal["full_path", "incremental_edge"] = "full_path"
    graph_incremental_static_prefix: bool = False
    protocol_version: Literal[
        "v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11", "v12", "v13"
    ] = "v4"

    @model_validator(mode="after")
    def validate_reasoning_controls(self) -> PlannerConfig:
        if self.reasoning_effort is not None and self.backend == "vllm":
            raise ValueError("reasoning_effort is supported only by Ollama and Responses API")
        if (
            self.reasoning_effort is not None
            and self.backend == "ollama"
            and not self.disable_thinking
        ):
            raise ValueError("reasoning_effort requires disable_thinking for compatibility")
        if self.service_tier is not None and self.backend != "responses":
            raise ValueError("service_tier is supported only by the Responses API backend")
        if (
            self.graph_incremental_static_prefix
            and self.graph_selection_interface != "incremental_edge"
        ):
            raise ValueError("graph_incremental_static_prefix requires incremental_edge selection")
        return self


def load_planner_config(path: str | Path) -> PlannerConfig:
    config_path = Path(path).expanduser().resolve(strict=True)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"planner config must contain a YAML mapping: {config_path}")
    return PlannerConfig.model_validate(raw)
