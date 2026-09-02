"""Content-addressed micro-rootfs creation and bubblewrap command execution."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory


@dataclass(frozen=True, slots=True)
class MicroRootfs:
    path: Path
    digest: str


@dataclass(frozen=True, slots=True)
class SandboxedCommandResult:
    returncode: int
    stdout: str
    stderr: str


def create_micro_rootfs(output_root: str | Path, busybox_path: str | Path) -> MicroRootfs:
    """Copy one static BusyBox binary into a content-addressed, minimal root filesystem."""
    root = Path(output_root).resolve()
    busybox = Path(busybox_path).resolve(strict=True)
    if not busybox.is_file():
        raise ValueError(f"busybox path is not a file: {busybox}")
    root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=root, prefix=".rootfs-") as temporary:
        staging = Path(temporary)
        for directory in ("bin", "dev", "proc", "tmp", "workspace"):
            (staging / directory).mkdir()
        destination = staging / "bin/busybox"
        shutil.copyfile(busybox, destination)
        destination.chmod(0o755)
        digest = _tree_digest(staging)
        final = root / digest
        if final.exists():
            return MicroRootfs(path=final, digest=digest)
        staging.rename(final)
        return MicroRootfs(path=final, digest=digest)


def run_in_micro_rootfs(
    *,
    rootfs: MicroRootfs,
    workspace: str | Path,
    argv: tuple[str, ...],
    timeout_seconds: int,
    bwrap_path: str | Path = "bwrap",
) -> SandboxedCommandResult:
    """Run an argv-only command with no host root or network mount available."""
    if not argv:
        raise ValueError("sandbox command argv must not be empty")
    if timeout_seconds <= 0:
        raise ValueError("sandbox timeout_seconds must be positive")
    workspace_path = Path(workspace).resolve(strict=True)
    if not workspace_path.is_dir():
        raise ValueError(f"sandbox workspace is not a directory: {workspace_path}")
    rootfs_path = rootfs.path.resolve(strict=True)
    if _tree_digest(rootfs_path) != rootfs.digest:
        raise ValueError("micro-rootfs content digest does not match its declared digest")
    command = build_bwrap_command(rootfs_path, workspace_path, argv, bwrap_path)
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return SandboxedCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def build_bwrap_command(
    rootfs: Path, workspace: Path, argv: tuple[str, ...], bwrap_path: str | Path
) -> tuple[str, ...]:
    """Return a network-isolated bubblewrap invocation without broad host mounts."""
    return (
        str(bwrap_path),
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--ro-bind",
        str(rootfs),
        "/",
        "--bind",
        str(workspace),
        "/workspace",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--chdir",
        "/workspace",
        "--",
        *argv,
    )


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.as_posix(),
    )
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()
