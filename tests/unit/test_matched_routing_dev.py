from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts/prepare_matched_routing_dev.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("prepare_matched_routing_dev", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _design(tmp_path: Path, edit: str) -> Path:
    design = yaml.safe_load(MODULE.DEFAULT_DESIGN.read_text())
    if edit == "null_alternatives":
        for row in design["additional_choices"]:
            if row["conditions"] == ["alternatives_expanded"]:
                row["conditions"] = []
    elif edit == "null_dependencies":
        design["dependency_probe"]["constrained_adapters"] = []
    elif edit == "heldout":
        design["source"] = "scenarios/formal_v1/test/rbv1_f1_001_multi_source_reconciliation"
    elif edit == "unregistered_binding":
        design["additional_choices"][0]["binding_id"] = (
            "unregistered::source_artifacts.checkout_api.product_api.development.us_east::read"
        )
    path = tmp_path / "design.yaml"
    path.write_text(yaml.safe_dump(design))
    return path


def test_development_design_is_effective_deterministic_and_answer_preserving(
    tmp_path: Path,
) -> None:
    first = MODULE.materialize(MODULE.DEFAULT_DESIGN, tmp_path / "first")
    second = MODULE.materialize(MODULE.DEFAULT_DESIGN, tmp_path / "second")
    assert first["conditions"] == second["conditions"]
    assert not first["model_inference_started"]
    assert first["source_split"] == "dev"
    base = first["conditions"]["base"]
    expanded = first["conditions"]["alternatives_expanded"]
    active = first["conditions"]["dependencies_active"]
    assert base["terminal_paths"] == 113
    assert expanded["terminal_paths"] == 366
    assert expanded["eligible_paths"] > base["eligible_paths"]
    assert expanded["common_path_outcomes_changed"] == 0
    assert active["terminal_paths"] == base["terminal_paths"]
    assert active["functional_paths_lost"] == 16
    for row in first["conditions"].values():
        assert row["optimal_paths"] == 1
        assert row["invariant_flags"]["exact_set_same"]
        assert row["invariant_flags"]["task_same"]
        assert row["invariant_flags"]["certificates_same"]
        assert row["unsafe_paths"] > 0
    with pytest.raises(ValueError, match="immutable"):
        MODULE.materialize(MODULE.DEFAULT_DESIGN, tmp_path / "first")


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        ("null_alternatives", "alternative count did not increase"),
        ("null_dependencies", "no actual feasibility effect"),
        ("heldout", "held-out test"),
        ("unregistered_binding", "unknown provider"),
    ],
)
def test_rejects_invalid_design(tmp_path: Path, edit: str, message: str) -> None:
    path = _design(tmp_path, edit)
    with pytest.raises(ValueError, match=message):
        MODULE.materialize(path, tmp_path / "material")
    assert not (tmp_path / "material/manifest.json").exists()


def test_rejects_output_inside_source_materials() -> None:
    with pytest.raises(ValueError, match="overlap benchmark source"):
        MODULE.materialize(MODULE.DEFAULT_DESIGN, ROOT / "scenarios/forbidden_materialization")
