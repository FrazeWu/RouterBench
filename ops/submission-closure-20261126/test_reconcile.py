from __future__ import annotations

import hashlib

import pytest
from reconcile import canonical_inventory, validate_records


def test_registered_id_is_loaded_from_source_and_never_guessed_from_directory(tmp_path):
    directory = tmp_path / "display-directory"
    directory.mkdir()
    scenario = directory / "scenario.yaml"
    scenario.write_text("scenario_id: canonical_id_with_different_spelling\n")
    protocol = {
        "source_files": {
            "display-directory/scenario.yaml": hashlib.sha256(scenario.read_bytes()).hexdigest()
        }
    }
    assert canonical_inventory(tmp_path, protocol, ["display-directory"]) == {
        "display-directory": "canonical_id_with_different_spelling"
    }
    scenario.write_text("scenario_id: changed\n")
    with pytest.raises(ValueError, match="source changed"):
        canonical_inventory(tmp_path, protocol, ["display-directory"])


def test_exact_canonical_matrix_retains_backend_failure_and_rejects_missing_or_duplicate():
    protocol = {"protocol_id": "p", "source_revision": "r", "models": {"m": {"fingerprint": "f"}}}
    metadata = {
        "protocol_id": "p",
        "source_revision": "r",
        "model_fingerprint": "f",
        "variant": "A",
    }
    rows = [
        {
            "scenario_id": "canonical",
            "seed": seed,
            "status": "backend_failure" if seed == 1 else "valid",
            "metadata": metadata,
            "scenario_digest": "d",
        }
        for seed in range(5)
    ]
    audits = {"canonical": {"scenario_digest": "d"}}
    validate_records(rows, {"canonical"}, list(range(5)), "A", protocol, "m", audits)
    assert len(rows) == 5 and rows[1]["status"] == "backend_failure"
    for invalid in (rows[:-1], [*rows, rows[0]]):
        with pytest.raises(ValueError, match="exact canonical"):
            validate_records(invalid, {"canonical"}, list(range(5)), "A", protocol, "m", audits)
    with pytest.raises(ValueError, match="exact canonical"):
        validate_records(rows, {"directory-alias"}, list(range(5)), "A", protocol, "m", audits)
