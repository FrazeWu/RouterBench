from pathlib import Path

from routebench.sandbox import (
    SandboxCapabilities,
    create_micro_rootfs,
    probe_sandbox,
    run_in_micro_rootfs,
)


def test_probe_sandbox_returns_typed_capabilities() -> None:
    capabilities = probe_sandbox()

    assert isinstance(capabilities, SandboxCapabilities)
    assert capabilities.ready is bool(capabilities.ready)


def test_micro_rootfs_is_content_addressed_and_isolates_host_root(tmp_path: Path) -> None:
    rootfs = create_micro_rootfs(tmp_path / "rootfs", "/usr/bin/busybox")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_in_micro_rootfs(
        rootfs=rootfs,
        workspace=workspace,
        argv=("/bin/busybox", "sh", "-c", "test ! -e /home && echo isolated > result.txt"),
        timeout_seconds=10,
    )

    assert result.returncode == 0, result.stderr
    assert (workspace / "result.txt").read_text(encoding="utf-8") == "isolated\n"
    assert rootfs.path.name == rootfs.digest
