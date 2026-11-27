from __future__ import annotations

import io
import json
import subprocess
import tarfile

from export_archive import PATTERNS, export


def test_export_preserves_logs_adapter_and_internal_links_but_removes_credentials(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    token = b"sk-proj-" + b"A" * 60
    (root / "run.log").write_bytes(b"request failed " + token + b"\n")
    (root / ".env").write_text("DO_NOT_EXPORT=yes\n")
    (root / ".venv").mkdir()
    (root / ".venv/library.py").write_text("environment code\n")
    (root / "base.safetensors").write_bytes(b"base weights")
    (root / "adapter_model.safetensors").write_bytes(b"fitted adapter")
    (root / "links").mkdir()
    (root / "links/log").symlink_to(root / "run.log")
    destination = tmp_path / "handoff/export"
    export(root, destination)
    expanded = subprocess.check_output(["zstd", "-dc", str(destination / "workspace.tar.zst")])
    with tarfile.open(fileobj=io.BytesIO(expanded)) as tar:
        names = set(tar.getnames())
        assert "workspace/adapter_model.safetensors" in names
        assert "workspace/base.safetensors" not in names
        assert "workspace/.env" not in names
        assert "workspace/.venv/library.py" not in names
        assert tar.getmember("workspace/links/log").linkname == "../run.log"
        assert token not in tar.extractfile("workspace/run.log").read()
        assert b"REDACTED_CREDENTIAL" in tar.extractfile("workspace/run.log").read()
    receipt = json.loads((destination / "export-receipt.json").read_text())
    assert receipt["redacted_matches"] == 1


def test_key_pattern_does_not_treat_long_task_names_as_api_credentials():
    text = b"task-example-long-string-that-is-not-an-authentication-key-with-many-hyphens"
    assert all(not pattern.search(text) for _, pattern in PATTERNS)
