"""Same-backbone outcome supervision and supported multi-step offline Q learning.

Only actual rollout labels train these models. This is an implementation, not a
claim of a novel RL algorithm, adequate training data, or demonstrated efficacy.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import Field

from routebench.defense.collect import PolicyChoice
from routebench.defense.contracts import content_hash
from routebench.defense.ecpa import DefenseObservation
from routebench.defense.features import FeatureBuilder, FloatArray, candidate_support_key
from routebench.defense.policies import PublicRulePolicy
from routebench.defense.traces import ECPATransition
from routebench.scenarios.schema import StrictModel


class LearningObjective(StrEnum):
    SUPERVISED = "supervised"
    OFFLINE_TD = "offline_td"


class TrainingSpec(StrictModel):
    objective: LearningObjective
    seed: int
    updates: int = Field(default=2000, gt=0)
    batch_size: int = Field(default=256, gt=0)
    learning_rate: float = Field(default=3e-4, gt=0)
    n_steps: int = Field(default=3, gt=0)
    minimum_support: int = Field(default=10, gt=0)
    target_tau: float = Field(default=0.005, gt=0, le=1)
    conservative_weight: float = Field(default=0.1, ge=0)


class LearningEpisode(StrictModel):
    episode_id: str
    semantic_family: str
    attack_mechanism: str
    split: str
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    # Development records deliberately carry no formal identity. A formal fit
    # may consume only records explicitly bound to the same frozen protocol.
    formal_protocol_id: str | None = Field(default=None, pattern=r"^ecpa-[a-z0-9][a-z0-9._-]*$")
    transitions: tuple[ECPATransition, ...]
    branch_parent_state: str | None = None
    branch_assignment_probability: float | None = Field(default=None, gt=0, le=1)


@dataclass(frozen=True)
class PreparedData:
    features: FloatArray
    labels: FloatArray  # success, cost, violation, full Monte Carlo return
    n_step_returns: FloatArray
    bootstrap_features: tuple[FloatArray | None, ...]
    menus: tuple[FloatArray, ...]
    support: dict[str, int]


def prepare_data(
    episodes: Sequence[LearningEpisode],
    builder: FeatureBuilder,
    spec: TrainingSpec,
    *,
    development_smoke: bool = False,
    formal_protocol_id: str | None = None,
) -> PreparedData:
    if development_smoke:
        if formal_protocol_id is not None:
            raise ValueError("development smoke data cannot claim a formal protocol identity")
        if not episodes or any(
            episode.split != "development" or episode.formal_protocol_id is not None
            for episode in episodes
        ):
            raise ValueError("development smoke fits may consume only unbound development data")
    else:
        if formal_protocol_id is None:
            raise ValueError("formal training requires a frozen formal protocol identity")
        if not episodes or any(
            episode.split != "train" or episode.formal_protocol_id != formal_protocol_id
            for episode in episodes
        ):
            raise ValueError(
                "formal fits may consume only training records "
                "bound to the matching frozen protocol"
            )
    ids = [episode.episode_id for episode in episodes]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate episode IDs are not independent collection records")
    support: Counter[str] = Counter()
    for episode in episodes:
        for row in episode.transitions:
            candidate = next(
                item for item in row.state.menu if item.candidate_id == row.candidate_id
            )
            support[candidate_support_key(candidate)] += 1
    features, labels, returns, menus = [], [], [], []
    bootstraps: list[FloatArray | None] = []
    for episode in episodes:
        rows = episode.transitions
        for index, row in enumerate(rows):
            if not row.bootstrap_available or row.remaining_safe_success is None:
                # Censored outcomes cannot be silently converted to failure labels.
                continue
            if row.remaining_cost is None or row.eventual_violation is None:
                raise ValueError("completed outcome/cost/violation labels are required")
            candidate = next(
                item for item in row.state.menu if item.candidate_id == row.candidate_id
            )
            features.append(builder.encode(row.state, [candidate])[0])
            menus.append(builder.encode(row.state, row.state.menu))
            labels.append(
                [
                    row.remaining_safe_success,
                    row.remaining_cost,
                    row.eventual_violation,
                    sum(item.reward for item in rows[index:]),
                ]
            )
            segment = rows[index : index + spec.n_steps]
            returns.append(sum(item.reward for item in segment))
            last = segment[-1]
            following = last.next_state
            if last.terminal or following is None:
                bootstraps.append(None)
            else:
                supported = [
                    item
                    for item in following.menu
                    if (support[candidate_support_key(item)] >= spec.minimum_support)
                ]
                if not supported:
                    # Use the observed full return instead of extrapolating the
                    # target network on an unsupported action.
                    returns[-1] = sum(item.reward for item in rows[index:])
                    bootstraps.append(None)
                else:
                    bootstraps.append(builder.encode(following, supported))
    if not features:
        raise ValueError("no completed actual rollout transitions are available")
    return PreparedData(
        np.asarray(features, dtype=np.float32),
        np.asarray(labels, dtype=np.float32),
        np.asarray(returns, dtype=np.float32),
        tuple(bootstraps),
        tuple(menus),
        dict(support),
    )


def train_scorer(data: PreparedData, spec: TrainingSpec, *, device: str = "cpu") -> dict[str, Any]:
    import copy

    import torch  # type: ignore[import-not-found]
    from torch import nn

    torch.manual_seed(spec.seed)
    rng = np.random.default_rng(spec.seed)
    net = nn.Sequential(
        nn.Linear(data.features.shape[1], 128),
        nn.ReLU(),
        nn.Linear(128, 64),
        nn.ReLU(),
        nn.Linear(64, 4),
    ).to(device)
    target = copy.deepcopy(net).eval()
    optimizer = torch.optim.Adam(net.parameters(), lr=spec.learning_rate)
    features = torch.as_tensor(data.features, device=device)
    labels = torch.as_tensor(data.labels, device=device)
    nstep = torch.as_tensor(data.n_step_returns, device=device)
    losses = []
    for update in range(spec.updates):
        indices = rng.integers(len(data.features), size=min(spec.batch_size, len(data.features)))
        selected = features[indices]
        prediction = net(selected)
        truth = labels[indices]
        loss = (
            nn.functional.binary_cross_entropy_with_logits(prediction[:, 0], truth[:, 0])
            + nn.functional.smooth_l1_loss(nn.functional.softplus(prediction[:, 1]), truth[:, 1])
            + nn.functional.binary_cross_entropy_with_logits(prediction[:, 2], truth[:, 2])
        )
        q_target = truth[:, 3].clone()
        if spec.objective is LearningObjective.OFFLINE_TD:
            with torch.no_grad():
                q_target = nstep[indices].clone()
                for i, index in enumerate(indices):
                    next_features = data.bootstrap_features[index]
                    if next_features is not None:
                        q_target[i] += target(torch.as_tensor(next_features, device=device))[
                            :, 3
                        ].max()
            if spec.conservative_weight:
                # Discrete finite-menu support regularizer; no claim that CQL is
                # necessary or that this penalty constitutes a safety certificate.
                penalties = []
                for i, index in enumerate(indices):
                    values = net(torch.as_tensor(data.menus[index], device=device))[:, 3]
                    penalties.append(torch.logsumexp(values, dim=0) - prediction[i, 3])
                loss = loss + spec.conservative_weight * torch.stack(penalties).mean()
        loss = loss + nn.functional.smooth_l1_loss(prediction[:, 3], q_target)
        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(net.parameters(), 5.0)
        optimizer.step()
        with torch.no_grad():
            for destination, source in zip(target.parameters(), net.parameters(), strict=True):
                destination.lerp_(source, spec.target_tau)
        if update == 0 or update + 1 == spec.updates:
            losses.append(float(loss.detach().cpu()))
    weights = {name: tensor.detach().cpu().numpy() for name, tensor in net.state_dict().items()}
    return {"weights": weights, "loss_first_last": losses}


class CandidateScorerPolicy:
    """Ensemble inference over the identical concrete menu; no grant authority."""

    def __init__(
        self,
        builder: FeatureBuilder,
        weights: Sequence[dict[str, FloatArray]],
        *,
        objective: LearningObjective,
        support: dict[str, int],
        minimum_support: int,
        cost_weight: float = 1.0,
        risk_weight: float = 10.0,
        uncertainty_limit: float = 1.0,
    ) -> None:
        if not weights or minimum_support <= 0:
            raise ValueError("a trained ensemble and positive support threshold are required")
        self.builder, self.weights = builder, weights
        self.objective, self.support, self.minimum_support = objective, support, minimum_support
        self.cost_weight, self.risk_weight = cost_weight, risk_weight
        self.uncertainty_limit = uncertainty_limit

    @staticmethod
    def forward(features: FloatArray, weights: dict[str, FloatArray]) -> FloatArray:
        hidden = np.maximum(features @ weights["0.weight"].T + weights["0.bias"], 0)
        hidden = np.maximum(hidden @ weights["2.weight"].T + weights["2.bias"], 0)
        return np.asarray(hidden @ weights["4.weight"].T + weights["4.bias"], dtype=np.float32)

    def choose(self, observation: DefenseObservation, *, rng: random.Random) -> PolicyChoice:
        candidates = [
            item
            for item in observation.menu
            if (self.support.get(candidate_support_key(item), 0) >= self.minimum_support)
        ]
        if not candidates:
            return PublicRulePolicy().choose(observation, rng=rng)
        features = self.builder.encode(observation, candidates)
        predictions = np.stack([self.forward(features, member) for member in self.weights])
        scores: FloatArray
        if self.objective is LearningObjective.SUPERVISED:
            success = 1 / (1 + np.exp(-np.clip(predictions[:, :, 0], -30, 30)))
            cost = np.logaddexp(0, predictions[:, :, 1])
            risk = 1 / (1 + np.exp(-np.clip(predictions[:, :, 2], -30, 30)))
            scores = np.asarray(
                success - self.cost_weight * cost - self.risk_weight * risk, dtype=np.float32
            )
        else:
            scores = predictions[:, :, 3]
        mean, disagreement = scores.mean(0), scores.std(0)
        admissible = np.flatnonzero(disagreement <= self.uncertainty_limit)
        if not len(admissible):
            return PublicRulePolicy().choose(observation, rng=rng)
        index = int(admissible[np.argmax((mean - disagreement)[admissible])])
        return PolicyChoice(candidates[index].candidate_id)


def save_scorer(
    directory: Path,
    result: dict[str, Any],
    spec: TrainingSpec,
    *,
    data: PreparedData,
    encoder_identity: str,
    source_episodes: Sequence[LearningEpisode],
    development_smoke: bool,
    formal_protocol_id: str | None,
) -> None:
    if development_smoke and formal_protocol_id is not None:
        raise ValueError("a development scorer cannot have a formal protocol identity")
    if not development_smoke and formal_protocol_id is None:
        raise ValueError("a formal scorer requires a frozen formal protocol identity")
    if any(episode.formal_protocol_id != formal_protocol_id for episode in source_episodes):
        raise ValueError("scorer provenance must match every source episode")
    directory.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(directory / "weights.npz", **result["weights"])
    manifest = {
        "spec": spec.model_dump(mode="json"),
        "encoder_identity": encoder_identity,
        "support": data.support,
        "feature_dimension": data.features.shape[1],
        "training_transitions": len(data.features),
        "development_smoke": development_smoke,
        "formal_protocol_id": formal_protocol_id,
        "episode_ids": [episode.episode_id for episode in source_episodes],
        "episode_fingerprints": [
            content_hash(episode.model_dump(mode="json")) for episode in source_episodes
        ],
        "source_revisions": sorted({episode.source_revision for episode in source_episodes}),
        "loss_first_last": result["loss_first_last"],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def load_scorer_ensemble(
    directories: Sequence[Path],
    builder: FeatureBuilder,
    *,
    cost_weight: float = 1.0,
    risk_weight: float = 10.0,
    uncertainty_limit: float = 1.0,
    allow_development_smoke: bool = False,
    expected_formal_protocol_id: str | None = None,
) -> CandidateScorerPolicy:
    if not directories:
        raise ValueError("at least one trained scorer is required")
    manifests = [json.loads((directory / "manifest.json").read_text()) for directory in directories]
    first = manifests[0]
    for manifest in manifests:
        if manifest["encoder_identity"] != builder.encoder.identity:
            raise ValueError("scorer must use the exact frozen training encoder")
        if manifest["development_smoke"] and not allow_development_smoke:
            raise ValueError("a development smoke scorer cannot enter formal evaluation")
        if not manifest["development_smoke"]:
            if expected_formal_protocol_id is None:
                raise ValueError("formal scorer use requires an expected frozen protocol identity")
            if manifest.get("formal_protocol_id") != expected_formal_protocol_id:
                raise ValueError("scorer protocol identity does not match the formal evaluation")
        elif expected_formal_protocol_id is not None:
            raise ValueError("development smoke scorers cannot satisfy a formal protocol identity")
        if (
            any(
                manifest.get(key) != first.get(key)
                for key in (
                    "encoder_identity",
                    "support",
                    "episode_fingerprints",
                    "feature_dimension",
                    "formal_protocol_id",
                )
            )
            or manifest["spec"]["objective"] != first["spec"]["objective"]
        ):
            raise ValueError("ensemble members must use the same data, encoder and objective")
    weights = []
    for directory in directories:
        with np.load(directory / "weights.npz", allow_pickle=False) as archive:
            weights.append(
                {name: np.asarray(archive[name], dtype=np.float32) for name in archive.files}
            )
    return CandidateScorerPolicy(
        builder,
        weights,
        objective=LearningObjective(first["spec"]["objective"]),
        support=first["support"],
        minimum_support=first["spec"]["minimum_support"],
        cost_weight=cost_weight,
        risk_weight=risk_weight,
        uncertainty_limit=uncertainty_limit,
    )
