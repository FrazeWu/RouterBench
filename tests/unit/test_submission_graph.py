"""Regression checks for the prospectively frozen repaired graph interface."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from routebench.planners.local_json import PlannerResponseError, _anonymize_candidate_graph
from routebench.runtime.graph import enumerate_terminal_paths
from routebench.scenarios.loader import load_scenario
from routebench.submission.common import durable_json
from routebench.submission.graph import RepairGraphPlanner, candidate_menu, local_graph_view
from routebench.submission.optimality import smt_paths

ROOT = Path(__file__).parents[2]
CASE = ROOT / "scenarios/formal_v1/test/rbv1-f3-047-audit-evidence-export"


def test_explicit_interface_can_continue_through_a_terminal_and_stop_later() -> None:
    bundle = load_scenario(CASE)
    graph = bundle.definition.graph
    route = bundle.definition.routes.certificates.safe.edge_ids
    edges = {edge.edge_id: edge for edge in graph.edges}
    intermediate = edges[route[0]].target
    graph = graph.model_copy(update={"terminal_nodes": (*graph.terminal_nodes, intermediate)})
    _, mapping = _anonymize_candidate_graph(graph, 1701)
    labels = {original: public for public, original in mapping.items()}
    seen = []

    class Gateway:
        async def complete(
            self, instruction: str, payload: dict[str, Any], schema: dict[str, Any], seed: int
        ) -> str:
            seen.append(payload)
            step = len(payload["selected_edge_ids"])
            if step == len(route):
                assert payload["stop_allowed"]
                return json.dumps({"decision": "stop", "edge_id": None})
            if step == 1:
                assert (
                    payload["stop_allowed"]
                    and "continue" in schema["properties"]["decision"]["enum"]
                )
            return json.dumps({"decision": "continue", "edge_id": labels[route[step]]})

    planner = RepairGraphPlanner(Gateway(), bundle.definition.policy)
    result = asyncio.run(planner.select_graph_path(bundle.definition.task, graph, 1701))
    assert result.edge_ids == route and len(seen) == len(route) + 1
    text = json.dumps(seen)
    for hidden in ("minimum_authority", "certificates", "verifier", "route_costs"):
        assert hidden not in text
    assert (
        seen[0]["preference_contract"]["tie_policy"]
        == "all_equal_lexicographic_optima_receive_primary_credit"
    )


def test_invalid_decision_is_retained_as_a_failure_without_retry() -> None:
    bundle = load_scenario(CASE)
    calls = []

    class Gateway:
        async def complete(self, *args: Any) -> str:
            calls.append(True)
            return '{"decision":"stop","edge_id":null}'

    planner = RepairGraphPlanner(Gateway(), bundle.definition.policy)
    with pytest.raises(PlannerResponseError, match="invalid explicit"):
        asyncio.run(
            planner.select_graph_path(bundle.definition.task, bundle.definition.graph, 1701)
        )
    assert len(calls) == 1


def test_public_dynamic_selector_and_local_view_preserve_condition_pairing() -> None:
    graph = load_scenario(CASE).definition.graph
    for node in graph.nodes:
        left, _ = candidate_menu(graph, node.node_id, (), "D", 1701)
        right, _ = candidate_menu(graph, node.node_id, (), "E", 1701)
        assert left == right
        assert set(left) <= {edge.edge_id for edge in graph.edges if edge.source == node.node_id}
    view = local_graph_view(graph, graph.start_node, ())
    assert view["view_radius"] == 2
    assert len(view["edges"]) < len(graph.edges)


def test_smt_enumerator_includes_paths_that_cross_terminal_nodes() -> None:
    bundle = load_scenario(CASE)
    graph = bundle.definition.graph
    first = bundle.definition.routes.certificates.safe.edge_ids[0]
    intermediate = next(edge.target for edge in graph.edges if edge.edge_id == first)
    graph = graph.model_copy(update={"terminal_nodes": (*graph.terminal_nodes, intermediate)})
    assert smt_paths(graph) == tuple(sorted(enumerate_terminal_paths(graph)))
    assert any(
        len(path) < len(other) and other[: len(path)] == path
        for path in smt_paths(graph)
        for other in enumerate_terminal_paths(graph)
    )


def test_durable_publication_preserves_previous_results(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    durable_json(path, {"complete": True})
    with pytest.raises(FileExistsError):
        durable_json(path, {"complete": False})
    assert json.loads(path.read_text()) == {"complete": True}
    assert list(tmp_path.iterdir()) == [path]


def test_usage_overrun_is_charged_and_durably_recorded_before_abort(tmp_path: Path) -> None:
    from types import SimpleNamespace

    import httpx

    from routebench.planners.config import PlannerConfig
    from routebench.submission.common import MeasuredGateway

    config = PlannerConfig.model_validate(
        {
            "schema_version": 2,
            "backend": "vllm",
            "model": "TEST",
            "endpoint": "http://127.0.0.1:8011/v1",
            "generation": {"temperature": 0, "top_p": 1, "max_tokens": 64, "context_window": 4096},
            "formal_run": True,
        }
    )

    async def exercise() -> None:
        gateway = MeasuredGateway(
            config,
            tmp_path,
            SimpleNamespace(before=lambda _: None, after=lambda: None),
            call_limit=2,
        )
        await gateway.client.aclose()
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": "{}"}}],
                        "usage": {"prompt_tokens": 4096, "completion_tokens": 64},
                    },
                )
            ),
            event_hooks={"response": [gateway.capture_usage]},
        )
        gateway.client = gateway.planner.client = client
        try:
            with pytest.raises(ValueError, match="exceeds the frozen context"):
                await gateway.complete("synthetic request", {}, {"type": "object"}, 1701)
            assert gateway.ledger.tokens == {"rollout": 4096}
            recorded = json.loads((tmp_path / "calls/call-00000000.json").read_text())
            assert recorded["status"] == "invalid_reported_usage"
            assert recorded["charged_tokens"] == 4096
        finally:
            await gateway.aclose()

    asyncio.run(exercise())
