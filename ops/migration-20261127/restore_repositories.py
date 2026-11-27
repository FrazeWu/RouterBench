"""Restore archived Git identities without overwriting exported working files."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def restore(workspace: Path, bundle: Path, mapping: Path) -> None:
    rows = json.loads(mapping.read_text())
    store = workspace / "artifacts/private/migration-object-store.git"
    if not store.exists():
        store.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", "--mirror", str(bundle), str(store)], check=True)
    for row in sorted(rows, key=lambda row: (row["directory"].count("/"), row["directory"])):
        root = workspace / row["directory"]
        if not root.is_dir():
            raise ValueError(f"archived checkout directory is missing: {row['directory']}")
        if (root / ".git").exists():
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            if head != row["head"]:
                raise ValueError("existing repository has a different HEAD; left unchanged")
            continue
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        alternate = root / ".git/objects/info/alternates"
        alternate.parent.mkdir(parents=True, exist_ok=True)
        alternate.write_text(str(store / "objects") + "\n")
        subprocess.run(
            ["git", "update-ref", "refs/heads/archived", row["head"]], cwd=root, check=True
        )
        subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/archived"], cwd=root, check=True)
        # Populate only the index. Never replace the exported source/user changes.
        subprocess.run(["git", "read-tree", "HEAD"], cwd=root, check=True)
        status = subprocess.check_output(["git", "status", "--short"], cwd=root, text=True)
        print(
            json.dumps(
                {
                    "directory": row["directory"],
                    "head": row["head"],
                    "status": status,
                    "original_status": row["status"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    args = parser.parse_args()
    restore(args.workspace.resolve(), args.bundle.resolve(), args.map.resolve())
