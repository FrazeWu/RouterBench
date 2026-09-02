"""Read-only host capability checks used by the CLI doctor command."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SandboxCapabilities:
    bubblewrap_path: str | None
    user_namespaces_enabled: bool
    cgroup_v2: bool
    systemd_run_path: str | None

    @property
    def ready(self) -> bool:
        return bool(
            self.bubblewrap_path
            and self.user_namespaces_enabled
            and self.cgroup_v2
            and self.systemd_run_path
        )


def probe_sandbox() -> SandboxCapabilities:
    userns_setting = Path("/proc/sys/kernel/unprivileged_userns_clone")
    userns_enabled = not userns_setting.exists() or userns_setting.read_text().strip() == "1"
    return SandboxCapabilities(
        bubblewrap_path=shutil.which("bwrap"),
        user_namespaces_enabled=userns_enabled,
        cgroup_v2=Path("/sys/fs/cgroup/cgroup.controllers").is_file(),
        systemd_run_path=shutil.which("systemd-run"),
    )
