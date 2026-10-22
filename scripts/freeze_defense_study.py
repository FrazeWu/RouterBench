"""Freeze a reviewed committed ECPA plan; never run a model or accept a review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from routebench.defense.corpus import load_corpus, source_path
from routebench.defense.freeze import StudySpec, freeze_study, write_frozen_study


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--authoring-audit", type=Path, required=True)
    parser.add_argument("--context-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    config = source_path(root, str(args.config))
    spec = StudySpec.model_validate(yaml.safe_load(config.read_text()))
    corpus, tasks = load_corpus(root, root / spec.corpus_manifest)
    output = (root / args.output).resolve()
    if output.exists():
        parser.error("preserve prior freezes; choose a new output path")
    payload = freeze_study(
        root,
        spec,
        corpus,
        tasks,
        config_path=config,
        authoring_audit=json.loads((root / args.authoring_audit).read_text()),
        context_audit=json.loads((root / args.context_audit).read_text()),
    )
    write_frozen_study(root, output, payload)
    print(json.dumps({key: payload[key] for key in ("protocol_id", "source_revision")}))


if __name__ == "__main__":
    main()
