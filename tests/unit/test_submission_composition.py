"""Source matching, public-input isolation, and persistent history regression tests."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from routebench.submission.composition import audit_pair, load_pair, simulate_route
from routebench.submission.composition_inference import (
    local_question,
    measure_unit,
    public_projection,
)

ROOT = Path(__file__).parents[2]
PAIRS = sorted((ROOT / "scenarios/composition").glob("*/*/public.yaml"))


def pair_of(kind: str) -> Any:
    return next(load_pair(p.parent) for p in PAIRS if p.parent.name.endswith("_" + kind))


def test_fixed_allocation_has_both_matched_interventions_in_every_family() -> None:
    pairs = [load_pair(path.parent) for path in PAIRS]
    assert len(pairs) == 48
    assert Counter(pair.metadata["split"] for pair in pairs) == {"test": 40, "development": 8}
    families = {
        pair.metadata["semantic_family"] for pair in pairs if pair.metadata["split"] == "test"
    }
    assert len(families) == 20
    for pair in pairs:
        assert audit_pair(pair)["both_functional"]
    for family in families:
        assert {
            pair.metadata["kind"] for pair in pairs if pair.metadata["semantic_family"] == family
        } == {"dependency", "order"}


def test_ordering_violation_persists_after_final_audit_state_matches() -> None:
    pair = pair_of("order")
    good, bad = (simulate_route(pair, route) for route in pair.references)
    assert good["functional"] and bad["functional"]
    assert good["final_setting_version"] == bad["final_setting_version"] == 2
    assert good["final_audit_enabled"] == bad["final_audit_enabled"] is True
    assert not good["violation"] and bad["violation"]
    assert any(
        event["audited_change"] and not event["audit_enabled_before"] for event in bad["events"]
    )


def test_public_projection_contains_no_reference_or_private_value() -> None:
    for kind in ("dependency", "order"):
        pair = pair_of(kind)
        for presentation in (0, 1):
            view, mapping = public_projection(pair, presentation)
            encoded = json.dumps(view)
            assert "reference_routes" not in encoded and "SYNTHETIC_PRIVATE_VARIANT" not in encoded
            assert "fixture-" not in encoded and "public_digest" not in encoded
            assert set(view["task"]["contract"]["actions"]) == set(mapping)
            assert {e["edge_id"] for e in view["task"]["graph"]["edges"]} == set(mapping)
            truths = [
                local_question(pair, presentation, unit)[1]
                for unit in ("L_allow", "L_deny", "L_event_allow", "L_event_deny")
            ]
            assert truths == [True, False, True, False]


def test_recognition_counterbalances_both_labels_in_isolated_requests() -> None:
    pair = pair_of("dependency")
    calls = []

    class Gateway:
        async def complete(
            self, instruction: str, payload: dict[str, Any], schema: dict[str, Any], seed: int
        ) -> str:
            calls.append(payload)
            view, mapping = public_projection(pair, seed - 1701)
            del view
            response = {}
            for label, route in payload["routes_to_label"].items():
                original = tuple(mapping[edge] for edge in route)
                response[label] = (
                    "safe" if simulate_route(pair, original)["policy_compliant"] else "forbidden"
                )
            return json.dumps(response)

    for presentation in (0, 1):
        result = asyncio.run(measure_unit(pair, presentation, "R", Gateway()))
        assert result["correct"]
    assert calls[0]["routes_to_label"]["route_A"] != calls[1]["routes_to_label"]["route_A"]
