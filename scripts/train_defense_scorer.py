"""Fit an outcome scorer or offline TD scorer on actual private simulator traces."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
import time
from pathlib import Path

from routebench.defense.features import FeatureBuilder, FrozenTransformerEncoder
from routebench.defense.learning import (
    LearningEpisode,
    LearningObjective,
    TrainingSpec,
    prepare_data,
    save_scorer,
    train_scorer,
)


def train(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--short"], cwd=root, text=True))
    if dirty and not args.development_smoke:
        raise ValueError("non-development training requires a committed, clean source revision")
    if args.development_smoke and args.formal_protocol_id is not None:
        raise ValueError("development smoke fitting cannot claim a formal protocol identity")
    if not args.development_smoke and args.formal_protocol_id is None:
        raise ValueError("formal fitting requires --formal-protocol-id from the frozen protocol")
    episodes = []
    for path in sorted(Path(args.data).glob("*.private.json")):
        raw = json.loads(path.read_text())
        episodes.append(
            LearningEpisode(
                episode_id=path.stem,
                semantic_family=raw["semantic_family"],
                attack_mechanism=raw["attack_mechanism"],
                split=raw["split"],
                source_revision=raw["source_revision"],
                formal_protocol_id=raw.get("formal_protocol_id"),
                transitions=raw["transitions"],
            )
        )
    spec = TrainingSpec(
        objective=LearningObjective(args.objective),
        seed=args.seed,
        updates=args.updates,
        minimum_support=args.minimum_support,
    )
    started = time.perf_counter()
    encoder = FrozenTransformerEncoder(
        args.encoder,
        identity="intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52",
        device=args.device,
    )
    builder = FeatureBuilder(encoder)
    data = prepare_data(
        episodes,
        builder,
        spec,
        development_smoke=args.development_smoke,
        formal_protocol_id=args.formal_protocol_id,
    )
    encoded = time.perf_counter()
    result = train_scorer(data, spec, device=args.device)
    trained = time.perf_counter()
    save_scorer(
        Path(args.output),
        result,
        spec,
        data=data,
        encoder_identity=encoder.identity,
        source_episodes=episodes,
        development_smoke=args.development_smoke,
        formal_protocol_id=args.formal_protocol_id,
    )
    measurement = {
        "source_revision": revision,
        "dirty_development": dirty,
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("torch", "transformers", "numpy", "pydantic")
        },
        "purpose": "development_smoke" if args.development_smoke else "training",
        "formal_protocol_id": args.formal_protocol_id,
        "episodes": len(episodes),
        "transitions": len(data.features),
        "feature_dimension": data.features.shape[1],
        "encoder_load_and_features_seconds": encoded - started,
        "training_seconds": trained - encoded,
        "updates": spec.updates,
        "encoder_chunks": encoder.chunks_encoded,
        "encoder_tokens": encoder.tokens_encoded,
        "loss_first_last": result["loss_first_last"],
        "efficacy_evidence": False,
    }
    (Path(args.output) / "measurement.json").write_text(json.dumps(measurement, indent=2) + "\n")
    print(json.dumps(measurement), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--objective", choices=[item.value for item in LearningObjective], required=True
    )
    parser.add_argument("--encoder", default="/home/dasp/models/e5-small-v2")
    parser.add_argument("--device", default="cuda:1")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--updates", type=int, default=200)
    parser.add_argument("--minimum-support", type=int, default=1)
    parser.add_argument("--development-smoke", action="store_true")
    parser.add_argument("--formal-protocol-id")
    train(parser.parse_args())
