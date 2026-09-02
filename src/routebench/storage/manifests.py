"""Reproducibility metadata for private development manifests."""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_private_run_metadata(
    *,
    workspace_root: str | Path,
    scenario_digest: str,
    planner_config: str | Path,
    controller_config: str | Path,
    controller: str,
    feedback_mode: str,
    model: str,
    formal_run: bool,
    model_weight_hash: str | None = None,
    rootfs_hash: str | None = None,
    rootfs_required: bool = True,
) -> dict[str, Any]:
    """Describe a local run and make every formal-manifest gap machine-visible."""
    root = Path(workspace_root).resolve(strict=True)
    planner_path = Path(planner_config).resolve(strict=True)
    controller_path = Path(controller_config).resolve(strict=True)
    lock_path = root / "uv.lock"
    _validate_optional_sha256("model_weight_hash", model_weight_hash)
    _validate_optional_sha256("rootfs_hash", rootfs_hash)
    missing_formal_fields: list[str] = []
    if model_weight_hash is None:
        missing_formal_fields.append("model_weight_hash")
    if rootfs_required and rootfs_hash is None:
        missing_formal_fields.append("rootfs_hash")
    git = _git_metadata(root)
    if git["commit"] is None:
        missing_formal_fields.append("git_commit")
    if git["dirty"] is not False:
        missing_formal_fields.append("git_worktree_clean")
    if not lock_path.is_file():
        missing_formal_fields.append("dependency_lock_hash")
    if not formal_run:
        missing_formal_fields.append("formal_run_required")
    publishable = not missing_formal_fields
    return {
        "controller": controller,
        "feedback_mode": feedback_mode,
        "planner": {
            "model": model,
            "config_path": str(planner_path),
            "config_hash": file_sha256(planner_path),
            "formal_run": formal_run,
        },
        "controller_config": {
            "path": str(controller_path),
            "hash": file_sha256(controller_path),
        },
        "scenario_digest": scenario_digest,
        "dependency_lock_hash": file_sha256(lock_path) if lock_path.is_file() else None,
        "git": git,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "executable": sys.executable,
        },
        "model_weight_hash": model_weight_hash,
        "rootfs_hash": rootfs_hash,
        "rootfs_required": rootfs_required,
        "rootfs_status": (
            "available"
            if rootfs_hash is not None
            else "required_missing"
            if rootfs_required
            else "not_applicable"
        ),
        "publishable": publishable,
        "missing_formal_fields": sorted(missing_formal_fields),
    }


def _validate_optional_sha256(field: str, value: str | None) -> None:
    if value is None:
        return
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _git_metadata(workspace_root: Path) -> dict[str, str | bool | None]:
    commit = _git_output(workspace_root, "rev-parse", "HEAD")
    status = _git_output(workspace_root, "status", "--porcelain")
    return {"commit": commit, "dirty": bool(status) if status is not None else None}


def _git_output(workspace_root: Path, *arguments: str) -> str | None:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=workspace_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()
