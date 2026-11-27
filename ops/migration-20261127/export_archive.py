"""Export code/log snapshots without environments, base weights, or credentials."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import time
from pathlib import Path

PATTERNS = [
    (
        "github_token",
        re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,255}|github_pat_[A-Za-z0-9_]{50,255})"),
    ),
    ("api_secret", re.compile(rb"(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{40,255}")),
    ("aws_access_key", re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}")),
    (
        "private_key",
        re.compile(
            rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----.*?"
            rb"-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
            re.S,
        ),
    ),
    ("url_credentials", re.compile(rb"https?://[^\s/:@]+:[^\s/@]+@")),
]
SKIP_DIRS = {
    ".git",
    ".venv",
    "runtime-env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "node_modules",
}
TEXT_SUFFIXES = {
    ".py",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".txt",
    ".log",
    ".md",
    ".tex",
    ".bib",
    ".csv",
    ".html",
    ".sh",
    ".toml",
    ".service",
    ".xml",
    ".svg",
    ".ipynb",
    ".patch",
    ".diff",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def export(root: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "workspace.tar.zst"
    excluded, redactions, repositories = [], [], []
    manifest = output / "file-manifest.jsonl"
    started, files, total = time.time(), 0, 0
    with archive.open("xb") as compressed, manifest.open("x") as ledger:
        process = subprocess.Popen(
            ["zstd", "-T4", "-6", "-q", "-c"], stdin=subprocess.PIPE, stdout=compressed
        )
        try:
            with tarfile.open(fileobj=process.stdin, mode="w|") as tar:

                def preserve_link(path: Path) -> bool:
                    resolved = path.resolve()
                    if not resolved.is_relative_to(root):
                        return False
                    info = tar.gettarinfo(
                        str(path), arcname="workspace/" + str(path.relative_to(root))
                    )
                    info.linkname = os.path.relpath(resolved, path.parent)
                    tar.addfile(info)
                    ledger.write(
                        json.dumps(
                            {
                                "path": str(path.relative_to(root)),
                                "kind": "symlink",
                                "original_target": os.readlink(path),
                                "exported_target": info.linkname,
                            }
                        )
                        + "\n"
                    )
                    return True

                for current, dirs, names in os.walk(root, followlinks=False):
                    directory = Path(current)
                    if ".git" in dirs or ".git" in names:
                        try:
                            head = subprocess.check_output(
                                ["git", "rev-parse", "HEAD"],
                                cwd=directory,
                                text=True,
                                stderr=subprocess.DEVNULL,
                            ).strip()
                            status = subprocess.check_output(
                                ["git", "status", "--short"],
                                cwd=directory,
                                text=True,
                                stderr=subprocess.DEVNULL,
                            )
                            repositories.append(
                                {
                                    "directory": str(directory.relative_to(root)) or ".",
                                    "head": head,
                                    "status": status,
                                }
                            )
                        except subprocess.CalledProcessError:
                            excluded.append(
                                {
                                    "path": str(directory.relative_to(root)),
                                    "reason": "unreadable_git_metadata; files_still_exported",
                                }
                            )
                    retained = []
                    for name in sorted(dirs):
                        path = directory / name
                        relative = path.relative_to(root)
                        reason = None
                        if path == output.parent or path.is_relative_to(output.parent):
                            reason = "export_output_and_isolated_handoff_checkout"
                        elif name in SKIP_DIRS or (path / "pyvenv.cfg").exists():
                            reason = "git_metadata_or_reinstallable_environment_cache"
                        elif relative.parts[:2] == ("data", "external"):
                            reason = "external_dataset_download"
                        elif path.is_symlink():
                            if preserve_link(path):
                                continue
                            reason = "external_directory_symlink"
                        if reason:
                            excluded.append({"path": str(relative), "reason": reason})
                        else:
                            retained.append(name)
                    dirs[:] = retained
                    for name in sorted(names):
                        path = directory / name
                        relative = path.relative_to(root)
                        if name == ".git" or name.endswith((".pyc", ".pyo")) or name == ".coverage":
                            continue
                        if (
                            name == ".env"
                            or (name.startswith(".env.") and name != ".env.example")
                            or name in {"id_rsa", "id_ed25519", "credentials.json", ".netrc"}
                        ):
                            excluded.append({"path": str(relative), "reason": "credential_file"})
                            continue
                        if path.is_symlink():
                            if preserve_link(path):
                                continue
                            excluded.append(
                                {
                                    "path": str(relative),
                                    "reason": "file_symlink",
                                    "target": os.readlink(path),
                                }
                            )
                            continue
                        if not path.is_file():
                            continue
                        if path.suffix == ".safetensors" and name != "adapter_model.safetensors":
                            excluded.append({"path": str(relative), "reason": "base_model_weights"})
                            continue
                        size = path.stat().st_size
                        if size > 100 * 1024**2 and path.suffix in {".bin", ".pt", ".pth", ".onnx"}:
                            excluded.append(
                                {
                                    "path": str(relative),
                                    "reason": "large_downloaded_model_or_binary_cache",
                                }
                            )
                            continue
                        exported = None
                        if path.suffix in TEXT_SUFFIXES or size < 1024 * 1024:
                            data = path.read_bytes()
                            original_digest = hashlib.sha256(data).hexdigest()
                            if b"\0" not in data[:8192]:
                                for kind, pattern in PATTERNS:
                                    data, count = pattern.subn(b"[REDACTED_CREDENTIAL]", data)
                                    if count:
                                        redactions.append(
                                            {
                                                "path": str(relative),
                                                "kind": kind,
                                                "matches": count,
                                                "original_sha256": original_digest,
                                            }
                                        )
                            exported = data
                            exported_digest = hashlib.sha256(data).hexdigest()
                        else:
                            original_digest = exported_digest = sha(path)
                        info = tar.gettarinfo(str(path), arcname="workspace/" + str(relative))
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        if exported is not None and info.isreg():
                            info.size = len(exported)
                            tar.addfile(info, io.BytesIO(exported))
                        elif info.isreg():
                            with path.open("rb") as stream:
                                tar.addfile(info, stream)
                        else:
                            tar.addfile(info)
                        ledger.write(
                            json.dumps(
                                {
                                    "path": str(relative),
                                    "bytes": size,
                                    "original_sha256": original_digest,
                                    "exported_sha256": exported_digest,
                                }
                            )
                            + "\n"
                        )
                        files += 1
                        total += size
                        if files % 10000 == 0:
                            print(
                                json.dumps(
                                    {
                                        "files": files,
                                        "source_gib": round(total / 1024**3, 3),
                                        "elapsed_seconds": round(time.time() - started),
                                    }
                                ),
                                flush=True,
                            )
                ledger.flush()
                for filename, value in (
                    ("exclusions.json", excluded),
                    ("credential-redactions.json", redactions),
                    ("repositories.json", repositories),
                ):
                    path = output / filename
                    path.write_text(json.dumps(value, indent=2) + "\n")
                    tar.add(path, arcname=filename, recursive=False)
                tar.add(manifest, arcname=manifest.name, recursive=False)
        finally:
            process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("archive compression failed")
    receipt = {
        "status": "complete",
        "files": files,
        "source_bytes": total,
        "archive": archive.name,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": sha(archive),
        "file_manifest_sha256": sha(manifest),
        "redacted_matches": sum(r["matches"] for r in redactions),
        "excluded_entries": len(excluded),
        "git_repositories": len(repositories),
        "elapsed_seconds": time.time() - started,
    }
    (output / "export-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.root.resolve(), args.output.resolve())
