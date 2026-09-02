"""Load a scenario directory without executing scenario-provided code."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from routebench.scenarios.schema import ScenarioDefinition

_REQUIRED_FILES = ("scenario.yaml", "task.yaml", "policy.yaml", "verifier.yaml", "routes.yaml")
_OPTIONAL_FILES = ("graph.yaml",)


@dataclass(frozen=True, slots=True)
class ScenarioBundle:
    root: Path
    definition: ScenarioDefinition
    digest: str


def _read_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return value


def _scenario_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = [
        root / name for name in (*_REQUIRED_FILES, *_OPTIONAL_FILES) if (root / name).is_file()
    ]
    fixture_root = root / "fixtures"
    if fixture_root.exists():
        files.extend(path for path in fixture_root.rglob("*") if path.is_file())
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def load_scenario(path: str | Path) -> ScenarioBundle:
    root = Path(path).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"scenario path is not a directory: {root}")

    missing = [name for name in _REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        raise ValueError(f"scenario is missing required files: {', '.join(missing)}")

    payload: dict[str, Any] = {
        "metadata": _read_mapping(root / "scenario.yaml"),
        "task": _read_mapping(root / "task.yaml"),
        "policy": _read_mapping(root / "policy.yaml"),
        "verifier": _read_mapping(root / "verifier.yaml"),
        "routes": _read_mapping(root / "routes.yaml"),
    }
    graph_path = root / "graph.yaml"
    if graph_path.is_file():
        payload["graph"] = _read_mapping(graph_path)
    definition = ScenarioDefinition.model_validate(payload)
    return ScenarioBundle(root=root, definition=definition, digest=_scenario_digest(root))
