from __future__ import annotations

import shutil
from pathlib import Path

from routebench.contracts import AttackCondition, RiskCategory
from routebench.scenarios import ScenarioSplit, load_scenario

PROJECT_ROOT = Path(__file__).parents[2]
SAMPLE_SCENARIO = PROJECT_ROOT / "scenarios/data_integrity/dev/delete_customer_records"


def test_loads_sample_scenario() -> None:
    bundle = load_scenario(SAMPLE_SCENARIO)

    assert bundle.definition.metadata.risk_category is RiskCategory.DATA_INTEGRITY
    assert bundle.definition.metadata.split is ScenarioSplit.DEV
    assert AttackCondition.BENIGN in bundle.definition.metadata.supported_conditions
    assert len(bundle.digest) == 64


def test_fixture_change_changes_scenario_digest(tmp_path: Path) -> None:
    scenario_copy = tmp_path / "scenario"
    shutil.copytree(SAMPLE_SCENARIO, scenario_copy)
    before = load_scenario(scenario_copy).digest

    fixture = scenario_copy / "fixtures/state.json"
    fixture.write_text(fixture.read_text() + "\n", encoding="utf-8")

    assert load_scenario(scenario_copy).digest != before
