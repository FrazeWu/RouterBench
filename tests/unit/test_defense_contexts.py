from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from routebench.defense.contexts import audit_contexts
from routebench.defense.corpus import load_corpus

ROOT = Path(__file__).parents[2]


class InspectingTokenizer:
    def __init__(self) -> None:
        self.messages: list[list[dict[str, str]]] = []

    def apply_chat_template(self, messages: list[dict[str, str]], **kwargs: Any) -> list[int]:
        assert kwargs == {
            "tokenize": True,
            "return_dict": False,
            "add_generation_prompt": True,
            "enable_thinking": False,
        }
        text = json.dumps(messages)
        assert all(
            key not in text for key in ("safe_paths", "attack_path", "menu_probes", "verifier")
        )
        self.messages.append(messages)
        return [0] * (len(text) // 10)


def test_context_audit_uses_actual_messages_offers_and_detects_overflow_without_truncating() -> (
    None
):
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    agent, defender = InspectingTokenizer(), InspectingTokenizer()
    report = asyncio.run(audit_contexts(tasks[:1], agent, defender, context_tokens=1))
    assert report["sampled_inputs_fit"] is False
    assert report["formal_run_ready"] is False
    assert report["model_weight_loads"] == report["model_rollouts"] == 0
    assert agent.messages and defender.messages
    agent_inputs = [json.loads(messages[1]["content"]) for messages in agent.messages]
    assert any(view["offer"] is not None for view in agent_inputs)
    defender_inputs = [json.loads(messages[1]["content"]) for messages in defender.messages]
    assert all("tool_contents" not in view for view in defender_inputs)
    measurements = report["measurements"]
    assert isinstance(measurements, dict)
    assert measurements["agent_text_full_draft_reserve"]["planning_estimate"] is True
    assert all(row["overflow_samples"] == row["samples"] for row in measurements.values())


def test_context_audit_covers_registered_test_payloads_and_appended_draft_reserve() -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    selected = tuple(task for task in tasks if task.entry.split == "test")
    agent, defender = InspectingTokenizer(), InspectingTokenizer()
    report = asyncio.run(audit_contexts(selected, agent, defender))
    measurements = report["measurements"]
    assert isinstance(measurements, dict)
    assert measurements["agent_text_attack_full_draft_reserve"]["planning_estimate"] is True
    assert measurements["agent_text_attack_full_draft_reserve"]["samples"] > 0
    receiver_text = [messages[-1]["content"] for messages in agent.messages if len(messages) == 3]
    assert any("Continuation correction" in content for content in receiver_text)
    assert any('"tool_result"' in content for content in receiver_text)
