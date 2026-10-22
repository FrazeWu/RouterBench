"""Check new corpus sources without model calls or opening fresh-test outcomes."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

from routebench.defense.compact import write_json
from routebench.defense.corpus import audit_task, load_corpus, readiness
from routebench.defense.pilot import clean_revision
from scripts.validate_capability_universe import load_catalog, validate_binding_selection


async def audit(root: Path, manifest: Path) -> dict[str, object]:
    revision = clean_revision(root)
    spec, tasks = load_corpus(root, manifest)
    tracked = set(subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines())
    sources = [manifest.resolve(), root / "catalog/capability_universe.yaml"]
    for task in tasks:
        sources.extend(task.directory / name for name in (
            "public.yaml", "evaluator.yaml", "authoring.yaml", "state.fixture.json"
        ))
        if task.entry.review_evidence:
            sources.append(root / task.entry.review_evidence)
    if any(str(path.relative_to(root)) not in tracked for path in sources):
        raise ValueError("all corpus sources and manifest must be committed, not ignored inputs")
    universe = load_catalog(root / "catalog/capability_universe.yaml")
    rows = []
    for task in tasks:
        rows.append(
            await audit_task(
                task, validate_binding=lambda binding: validate_binding_selection(universe, binding)
            )
        )
    return {"source_revision": revision, **readiness(spec, tasks), "task_checks": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--manifest", type=Path, default=Path("configs/defense/independent-corpus.yaml")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(root / "artifacts/private"):
        parser.error("write runtime reports only under ignored artifacts/private")
    if output.exists():
        parser.error("retain prior audits; select a new output path")
    report = asyncio.run(audit(root, root / args.manifest))
    write_json(output, report)
    summary = {key: value for key, value in report.items() if key != "task_checks"}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
