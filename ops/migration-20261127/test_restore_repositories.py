from __future__ import annotations

import json
import shutil
import subprocess

from restore_repositories import restore


def test_restore_keeps_exported_user_changes_and_original_git_identity(tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "codex/test", str(original)], check=True)
    (original / ".gitignore").write_text("artifacts/\n")
    (original / "source.py").write_text("value = 1\n")
    subprocess.run(["git", "add", ".gitignore", "source.py"], cwd=original, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "test: snapshot",
        ],
        cwd=original,
        check=True,
    )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=original, text=True).strip()
    bundle = tmp_path / "source.bundle"
    subprocess.run(["git", "bundle", "create", str(bundle), "--all"], cwd=original, check=True)
    workspace = tmp_path / "restored"
    workspace.mkdir()
    shutil.copy2(original / ".gitignore", workspace / ".gitignore")
    (workspace / "source.py").write_text("value = 2  # user change\n")
    mapping = tmp_path / "repositories.json"
    mapping.write_text(json.dumps([{"directory": ".", "head": head, "status": " M source.py\n"}]))
    restore(workspace, bundle, mapping)
    assert (workspace / "source.py").read_text() == "value = 2  # user change\n"
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip()
        == head
    )
    assert (
        subprocess.check_output(["git", "status", "--short"], cwd=workspace, text=True)
        == " M source.py\n"
    )
    restore(workspace, bundle, mapping)
    assert (workspace / "source.py").read_text() == "value = 2  # user change\n"
