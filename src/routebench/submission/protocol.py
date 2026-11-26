"""Source, model, schedule, and parent-study identities for the finite closure."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from routebench.defense.contracts import content_hash
from routebench.defense.lora import file_digest, model_fingerprint
from routebench.defense.pilot import clean_revision
from routebench.submission.common import read_json


def load_protocol(path: Path, *, model_key: str | None = None) -> dict[str, Any]:
    protocol: dict[str, Any] = read_json(path)
    body = {key: value for key, value in protocol.items() if key != "protocol_id"}
    if protocol["protocol_id"] != "submission-closure-" + content_hash(body):
        raise ValueError("submission protocol digest mismatch")
    root = Path(__file__).resolve().parents[3]
    if str(root) != protocol["source_root"] or clean_revision(root) != protocol["source_revision"]:
        raise ValueError("the submission requires its recorded committed clean source")
    for name, expected in protocol["source_files"].items():
        if file_digest(root / name) != expected:
            raise ValueError(f"frozen source changed: {name}")
    if model_key is not None:
        model = protocol["models"][model_key]
        if model_fingerprint(model["path"]) != model["fingerprint"]:
            raise ValueError("frozen inference snapshot changed")
    parent = protocol["ecpa_parent"]
    for key in (
        "test_result",
        "test_validation_receipt",
        "frozen_study",
        "fit_result",
        "tune_result",
        "calibration_result",
        "tuning_decision",
    ):
        if file_digest(Path(parent[key]["path"])) != parent[key]["sha256"]:
            raise ValueError(f"frozen ECPA prerequisite changed: {key}")
    return protocol
