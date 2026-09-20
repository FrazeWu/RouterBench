from __future__ import annotations

import hashlib
import json
from pathlib import Path

from routebench.scenarios import load_scenario

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_ROOT = ROOT / "scenarios" / "formal_v1" / "test"
FREEZE_PATH = ROOT / "configs" / "benchmark" / "formal-v2-freeze.json"
CATALOG_PATH = ROOT / "catalog" / "capability_universe.yaml"


def test_formal_v2_freeze_matches_all_scenario_and_catalog_digests() -> None:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    assert freeze["status"] == "valid"
    assert freeze["protocol_revision"] == 2
    assert freeze["scenario_count"] == 776
    assert freeze["catalog_sha256"] == hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()

    rows = sorted(
        (
            load_scenario(path)
            for path in SCENARIO_ROOT.iterdir()
            if (path / "scenario.yaml").is_file()
        ),
        key=lambda bundle: bundle.definition.metadata.scenario_id,
    )
    digests = {bundle.definition.metadata.scenario_id: bundle.digest for bundle in rows}
    assert digests == freeze["scenario_digests"]
    digest_input = "\n".join(f"{scenario_id}:{digest}" for scenario_id, digest in digests.items())
    assert freeze["scenario_set_digest"] == hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
