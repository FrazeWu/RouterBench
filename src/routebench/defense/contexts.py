"""Tokenizer-only checks of sampled public inputs; never an outcome experiment."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from routebench.defense.agent import agent_messages
from routebench.defense.compact import prompt_ids
from routebench.defense.corpus import CorpusTask, replay_prefix
from routebench.defense.ecpa import AgentReply, AgentReplyKind, DefenseDecisionKind
from routebench.defense.relay import RelayCampaign, RelayStage, StagedResponseRelay


def message_tokens(tokenizer: Any, messages: list[dict[str, str]]) -> int:
    return len(
        tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            return_dict=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    )


async def audit_contexts(
    tasks: Sequence[CorpusTask],
    agent_tokenizer: Any,
    defender_tokenizer: Any,
    *,
    context_tokens: int = 8192,
    agent_completion_tokens: int = 768,
    defender_completion_tokens: int = 96,
) -> dict[str, object]:
    """Replay authoring prefixes but send only real public views to tokenizers.

    Benign drafts here are representative registered proposals, not generated
    model outputs. A separate full-draft reserve is a planning sensitivity, not
    an upper bound on every possible future continuation or tool response.
    """
    if min(context_tokens, agent_completion_tokens, defender_completion_tokens) <= 0:
        raise ValueError("context and completion budgets must be positive")
    counts: dict[str, list[int]] = defaultdict(list)
    for task in tasks:
        prefixes = {
            path[:length] for path in task.authoring.safe_paths for length in range(len(path) + 1)
        }
        prefixes.update(probe.prefix for probe in task.authoring.menu_probes)
        for prefix in sorted(prefixes):
            original = await replay_prefix(task, prefix)
            view = original.agent_view()
            counts["agent_proposal"].append(message_tokens(agent_tokenizer, agent_messages(view)))
            # Empty wrapper + a full draft budget is explicitly an estimate.
            counts["agent_text_full_draft_reserve"].append(
                message_tokens(agent_tokenizer, agent_messages(view, "")) + agent_completion_tokens
            )
            for edge in task.public.graph.edges:
                if edge.source != original.node:
                    continue
                proposal = AgentReply(kind=AgentReplyKind.PROPOSE, edge_id=edge.edge_id)
                counts["agent_text_representative_benign"].append(
                    message_tokens(
                        agent_tokenizer, agent_messages(view, proposal.model_dump_json())
                    )
                )
                campaign = RelayCampaign(
                    task_id=task.entry.task_id,
                    stages=(RelayStage(node=edge.source, edge_id=edge.edge_id),),
                )
                relay = StagedResponseRelay(campaign, mode="text", attacked=True)
                draft = relay.transform(proposal.model_dump_json(), view)
                counts["agent_text_fixed_attack"].append(
                    message_tokens(agent_tokenizer, agent_messages(view, draft))
                )
                env = original.clone_for_collection()
                observation = await env.observe(proposal)
                if observation is None:
                    raise ValueError("sampled authoring state exhausted the common budget")
                counts["defender_selector"].append(len(prompt_ids(defender_tokenizer, observation)))
                for candidate in observation.menu:
                    if candidate.kind is DefenseDecisionKind.CONSTRAIN:
                        counts["agent_acceptance"].append(
                            message_tokens(
                                agent_tokenizer, agent_messages(env.agent_view(candidate))
                            )
                        )
    rows = {}
    for kind, values in sorted(counts.items()):
        completion = (
            defender_completion_tokens if kind == "defender_selector" else agent_completion_tokens
        )
        rows[kind] = {
            "samples": len(values),
            "minimum_prompt_tokens": min(values),
            "maximum_prompt_tokens": max(values),
            "completion_reserve": completion,
            "minimum_headroom_tokens": context_tokens - max(values) - completion,
            "overflow_samples": sum(value + completion > context_tokens for value in values),
            "planning_estimate": kind == "agent_text_full_draft_reserve",
        }
    return {
        "purpose": "sampled_public_context_preparation",
        "context_tokens": context_tokens,
        "task_count": len(tasks),
        "measurements": rows,
        "sampled_inputs_fit": all(row["overflow_samples"] == 0 for row in rows.values()),
        "formal_run_ready": False,
        "model_weight_loads": 0,
        "model_rollouts": 0,
        "limitations": [
            "Authoring prefixes are sampled states, not exhaustive future trajectories.",
            "Benign drafts are representative proposals, not actual generated drafts.",
            "Full-draft reserve is an estimate; token-boundary differences remain unbounded.",
            "Later feedback, tool contents and repetitive denials can increase context length.",
            "No truncation is used; passing these checks does not establish semantic validity.",
        ],
    }
