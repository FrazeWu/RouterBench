#!/usr/bin/env python3
"""Run the paired bootstrap over completed formal v13 family/scale baselines."""

from __future__ import annotations

import paired_model_comparison as base

ROOT = base.ROOT
base.OUTPUT = ROOT / "artifacts/private/formal-v13-multifamily-paired-bootstrap-20261005.md"
base.MODELS = (
    ("Qwen3-8B", ROOT / "artifacts/private/formal-v3-776-20260929/qwen3-8b-v13"),
    ("Qwen3-14B", ROOT / "artifacts/private/formal-v3-776-20260929/qwen3-14b-v13"),
    ("Qwen3-32B-AWQ", ROOT / "artifacts/private/formal-v3-776-20260929/qwen3-32b-awq-v13"),
    ("Qwen2.5-7B", ROOT / "artifacts/private/formal-v13-qwen25-7b-20261004"),
    ("Llama3.1-8B", ROOT / "artifacts/private/formal-v13-llama31-8b-20261004"),
)
base.COMPARISONS = (
    ("Qwen3-14B", "Qwen3-8B"),
    ("Qwen3-32B-AWQ", "Qwen3-8B"),
    ("Qwen2.5-7B", "Qwen3-8B"),
    ("Llama3.1-8B", "Qwen3-8B"),
    ("Qwen3-14B", "Qwen2.5-7B"),
    ("Qwen3-14B", "Llama3.1-8B"),
    ("Qwen2.5-7B", "Llama3.1-8B"),
)


if __name__ == "__main__":
    base.main()
