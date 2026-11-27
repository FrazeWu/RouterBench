"""Record exact model bytes and archive public model configuration, without weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def inspect(item: tuple[str, dict]) -> tuple[str, dict]:
    key, model = item
    root = Path(model["path"])
    files = {}
    for path in sorted(root.iterdir()):
        if path.is_file() and path.suffix in {".json", ".safetensors", ".jinja", ".txt"}:
            h = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    h.update(block)
            files[path.name] = {"bytes": path.stat().st_size, "sha256": h.hexdigest()}
    fingerprint = hashlib.sha256(
        json.dumps(
            {name: row["sha256"] for name, row in files.items()},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    if fingerprint != model["fingerprint"]:
        raise ValueError(f"frozen model changed: {key}")
    revisions = set()
    for path in (root / ".cache/huggingface/download").glob("*.metadata"):
        lines = path.read_text().splitlines()
        if lines:
            revisions.add(lines[0])
    repository = {
        "qwen3-14b": "Qwen/Qwen3-14B",
        "qwen3-1.7b": "Qwen/Qwen3-1.7B",
        "qwen2.5-7b": "Qwen/Qwen2.5-7B-Instruct",
    }[key]
    upstream = {}
    try:
        with urllib.request.urlopen(
            f"https://huggingface.co/api/models/{repository}?blobs=true", timeout=30
        ) as response:
            data = json.load(response)
        weights = {s["rfilename"]: s.get("lfs", {}).get("sha256") for s in data["siblings"]}
        matching = all(
            weights.get(name) == row["sha256"]
            for name, row in files.items()
            if name.endswith(".safetensors")
        )
        upstream = {"queried_revision": data["sha"], "all_local_weight_shards_match": matching}
        if matching and not revisions:
            revisions.add(data["sha"])
    except Exception as error:
        upstream = {"query_error": type(error).__name__}
    return key, {
        "original_path": str(root),
        "repository": repository,
        "candidate_revisions": sorted(revisions),
        "frozen_fingerprint": fingerprint,
        "files": files,
        "upstream_verification": upstream,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    protocol = json.loads(args.protocol.read_text())
    with ThreadPoolExecutor(max_workers=3) as pool:
        models = dict(pool.map(inspect, protocol["models"].items()))
    manifest = {
        "protocol_id": protocol["protocol_id"],
        "base_model_weights_included": False,
        "models": models,
    }
    (args.output / "model-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with tarfile.open(args.output / "model-configs.tar.gz", "w:gz") as tar:
        for key, model in models.items():
            for name in model["files"]:
                if not name.endswith(".safetensors"):
                    tar.add(
                        Path(model["original_path"]) / name, arcname=f"model-configs/{key}/{name}"
                    )
    print(
        json.dumps(
            {
                key: {
                    "fingerprint": row["frozen_fingerprint"],
                    "revisions": row["candidate_revisions"],
                }
                for key, row in models.items()
            }
        )
    )


if __name__ == "__main__":
    main()
