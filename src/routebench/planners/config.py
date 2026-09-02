"""Strict, local-only planner configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float = Field(ge=0, le=2)
    top_p: float = Field(gt=0, le=1)
    max_tokens: int = Field(gt=0)


class PlannerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=2)
    backend: Literal["ollama", "vllm"]
    model: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    api_key_env: str | None = Field(default=None, min_length=1)
    generation: GenerationConfig
    formal_run: bool
    disable_thinking: bool = False
    vllm_object_only_schema: bool = False
    anonymize_graph_labels: bool = False
    protocol_version: Literal["v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11", "v12"] = "v4"


def load_planner_config(path: str | Path) -> PlannerConfig:
    config_path = Path(path).expanduser().resolve(strict=True)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"planner config must contain a YAML mapping: {config_path}")
    return PlannerConfig.model_validate(raw)
