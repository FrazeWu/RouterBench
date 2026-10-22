from __future__ import annotations

from pathlib import Path

from routebench.defense.contracts import PublicRecoveryTask
from routebench.defense.corpus import load_corpus
from routebench.defense.overlap import overlap_screen, structure_fingerprint

ROOT = Path(__file__).parents[2]


def test_dependency_screen_survives_renaming_and_reports_cross_split_without_certifying() -> None:
    _, tasks = load_corpus(ROOT, ROOT / "configs/defense/independent-corpus.yaml")
    original = tasks[0].public
    data = original.model_dump(mode="json")
    node_ids = {node.node_id: f"node_{index}" for index, node in enumerate(original.graph.nodes)}
    edge_ids = {edge.edge_id: f"edge_{index}" for index, edge in enumerate(original.graph.edges)}
    facts = sorted(
        {
            fact
            for contract in original.contract.actions.values()
            for fact in (*contract.requires, *contract.adds, *contract.removes)
        }
    )
    fact_ids = {fact: f"fact_{index}" for index, fact in enumerate(facts)}
    data["prompt"] = "A new title, provider branding and entity IDs do not prove independence."
    data["contract"]["task_id"] = "renamed_task"
    data["contract"]["semantic_family"] = "nominally_new_family"
    data["graph"]["start_node"] = node_ids[data["graph"]["start_node"]]
    data["graph"]["terminal_nodes"] = [node_ids[node] for node in data["graph"]["terminal_nodes"]]
    for node in data["graph"]["nodes"]:
        node["node_id"] = node_ids[node["node_id"]]
    for edge in data["graph"]["edges"]:
        edge["edge_id"] = edge_ids[edge["edge_id"]]
        edge["source"], edge["target"] = node_ids[edge["source"]], node_ids[edge["target"]]
        edge["capability_binding"] = None
        for key, value in edge["action"]["arguments"].items():
            if isinstance(value, str):
                edge["action"]["arguments"][key] = "different_entity"
    data["contract"]["goal_all"] = [fact_ids[fact] for fact in data["contract"]["goal_all"]]
    data["contract"]["actions"] = {
        edge_ids[key]: value for key, value in data["contract"]["actions"].items()
    }
    for contract in data["contract"]["actions"].values():
        for key in ("requires", "adds", "removes"):
            contract[key] = [fact_ids[fact] for fact in contract[key]]
    for approval in data["contract"]["approvals"]:
        approval["edge_ids"] = [edge_ids[edge_id] for edge_id in approval["edge_ids"]]
    renamed = PublicRecoveryTask.model_validate(data)
    assert structure_fingerprint(original, include_tools=False) == structure_fingerprint(
        renamed, include_tools=False
    )
    assert structure_fingerprint(original, include_tools=True) == structure_fingerprint(
        renamed, include_tools=True
    )
    report = overlap_screen([("train", original), ("test", renamed)])
    assert report["independence_certified"] is False
    matches = report["matches"]
    assert isinstance(matches, list)
    assert any(row["cross_split"] for row in matches)
    # A changed fact-invalidation dependency must not silently hash as the same structure.
    edge_id = next(iter(renamed.contract.actions))
    contracts = dict(renamed.contract.actions)
    contracts[edge_id] = contracts[edge_id].model_copy(update={"removes": (facts[0],)})
    changed = renamed.model_copy(
        update={"contract": renamed.contract.model_copy(update={"actions": contracts})}
    )
    assert structure_fingerprint(changed, include_tools=False) != structure_fingerprint(
        renamed, include_tools=False
    )
