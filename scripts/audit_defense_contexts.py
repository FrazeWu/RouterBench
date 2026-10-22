"""Measure public chat inputs with local tokenizers, without loading model weights."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from routebench.defense.contexts import audit_contexts
from routebench.defense.corpus import load_corpus
from routebench.defense.lora import file_digest
from scripts.audit_defense_corpus import audit


def tokenizer_identity(directory: Path) -> dict[str, str]:
    files = sorted(
        path
        for path in directory.iterdir()
        if path.is_file()
        and (
            path.name.startswith(("tokenizer", "special_tokens", "added_tokens", "chat_template"))
            or path.suffix == ".jinja"
        )
    )
    if not files:
        raise ValueError("local tokenizer snapshot is missing")
    return {path.name: file_digest(path) for path in files}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--manifest", type=Path, default=Path("configs/defense/independent-corpus.yaml")
    )
    parser.add_argument("--agent-tokenizer", type=Path, required=True)
    parser.add_argument("--defender-tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if not output.is_relative_to(root / "artifacts/private") or output.exists():
        parser.error("select a new output under ignored artifacts/private; preserve prior audits")
    source_audit = asyncio.run(audit(root, root / args.manifest))
    from transformers import AutoTokenizer  # type: ignore[import-not-found]

    identities = {
        name: tokenizer_identity(path)
        for name, path in (("agent", args.agent_tokenizer), ("defender", args.defender_tokenizer))
    }
    tokenizers = [
        AutoTokenizer.from_pretrained(str(path), local_files_only=True)
        for path in (args.agent_tokenizer, args.defender_tokenizer)
    ]
    _, tasks = load_corpus(root, root / args.manifest)
    report = asyncio.run(audit_contexts(tasks, *tokenizers))
    report.update(
        source_revision=source_audit["source_revision"],
        tokenizer_files=identities,
        corpus_digests={task.entry.task_id: task.digest for task in tasks},
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"corpus_digests", "tokenizer_files"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
