"""Frozen pretrained text features plus actual public state/candidate features.

The encoder is optional infrastructure, not part of the trusted execution boundary.
No text is silently truncated: long components are pooled over deterministic chunks.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from routebench.defense.contracts import canonical_json, content_hash
from routebench.defense.ecpa import BudgetLimits, DefenseCandidate, DefenseObservation

FloatArray = NDArray[np.float32]


class TextEncoder(Protocol):
    identity: str

    def encode(self, texts: Sequence[str]) -> FloatArray: ...


class FrozenTransformerEncoder:
    """Pinned local E5 encoder. Transformer weights never receive gradients."""

    def __init__(
        self, model_path: str, *, identity: str, device: str = "cpu", chunk_tokens: int = 480
    ) -> None:
        import torch  # type: ignore[import-not-found]
        from transformers import AutoModel, AutoTokenizer  # type: ignore[import-not-found]

        if not 16 <= chunk_tokens <= 480:
            raise ValueError("E5 chunk size must leave room for special tokens")
        self.identity = identity
        self.torch = torch
        self.device = device
        self.chunk_tokens = chunk_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        self.model = AutoModel.from_pretrained(model_path, local_files_only=True).to(device).eval()
        self.model.requires_grad_(False)
        self.cache: dict[str, FloatArray] = {}
        self.chunks_encoded = 0
        self.tokens_encoded = 0

    def _one(self, text: str) -> FloatArray:
        key = content_hash(text)
        if key in self.cache:
            return self.cache[key]
        tokens = self.tokenizer.encode("passage: " + text, add_special_tokens=False, verbose=False)
        chunks = [
            tokens[i : i + self.chunk_tokens] for i in range(0, len(tokens), self.chunk_tokens)
        ]
        chunks = chunks or [[]]
        vectors = []
        for start in range(0, len(chunks), 32):
            group = chunks[start : start + 32]
            rows = [
                [self.tokenizer.cls_token_id, *chunk, self.tokenizer.sep_token_id]
                for chunk in group
            ]
            batch: Any = self.tokenizer.pad(
                {"input_ids": rows}, padding=True, return_tensors="pt"
            ).to(self.device)
            with self.torch.inference_mode():
                hidden = self.model(**batch).last_hidden_state
                mask = batch["attention_mask"].unsqueeze(-1)
                pooled = (hidden * mask).sum(1) / mask.sum(1).clamp_min(1)
                vectors.extend(pooled.float().cpu().numpy())
        vector = np.average(np.stack(vectors), axis=0, weights=[max(1, len(c)) for c in chunks])
        vector = np.asarray(vector / max(np.linalg.norm(vector), 1e-12), dtype=np.float32)
        self.cache[key] = vector
        self.chunks_encoded += len(chunks)
        self.tokens_encoded += len(tokens)
        return vector

    def encode(self, texts: Sequence[str]) -> FloatArray:
        return np.stack([self._one(text) for text in texts]).astype(np.float32)


def candidate_support_key(candidate: DefenseCandidate) -> str:
    return canonical_json(
        [
            candidate.kind.value,
            candidate.action.tool if candidate.action else None,
        ]
    )


class FeatureBuilder:
    def __init__(self, encoder: TextEncoder) -> None:
        self.encoder = encoder

    def encode(
        self, observation: DefenseObservation, candidates: Sequence[DefenseCandidate]
    ) -> FloatArray:
        shared = self.encoder.encode(
            [
                observation.task.model_dump_json(),
                canonical_json(
                    {
                        "node": observation.node,
                        "facts": observation.facts,
                        "grants": [grant.model_dump(mode="json") for grant in observation.grants],
                        "proposal": observation.proposal.model_dump(mode="json"),
                        "approval_epoch": observation.approval_epoch,
                    }
                ),
                canonical_json(
                    {
                        "receipts": [item.model_dump(mode="json") for item in observation.receipts],
                        "tool_contents": [
                            item.model_dump(mode="json") for item in observation.tool_contents
                        ],
                        "feedback": observation.feedback,
                    }
                ),
            ]
        ).reshape(-1)
        concrete = self.encoder.encode([item.model_dump_json() for item in candidates])
        # Counts, never hashes, are numerical features. Bounded scaling is fixed,
        # independent of test data; the full text contains the exact typed values.
        numeric = [np.log1p(observation.remaining[name]) / 10 for name in BudgetLimits.model_fields]
        numeric += [np.log1p(observation.step) / 10, np.log1p(len(observation.receipts)) / 10]
        rows = []
        for candidate, vector in zip(candidates, concrete, strict=True):
            kinds = [
                float(candidate.kind.value == kind)
                for kind in ("allow", "constrain", "escalate", "deny")
            ]
            flags = [
                float(candidate.witness == status)
                for status in ("feasible", "infeasible", "unknown")
            ]
            rows.append(np.concatenate([shared, vector, numeric, kinds, flags]))
        return np.asarray(rows, dtype=np.float32)
