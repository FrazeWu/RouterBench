"""Public dependency-structure screening; hash differences do not prove independence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from routebench.defense.contracts import PublicRecoveryTask, content_hash


def _shape(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _shape(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return sorted((_shape(item) for item in value), key=str)
    # Resource/entity IDs, values and provider names must not establish a new family.
    return type(value).__name__


def structure_fingerprint(task: PublicRecoveryTask, *, include_tools: bool) -> str:
    """Refine a public graph of states, actions, facts and approval dependencies.

    Node/edge/fact/resource names and concrete values are erased. Typed screening
    retains adapters and argument shapes; dependency-only screening also erases
    those. This is a conservative candidate finder, not an isomorphism proof or
    a semantic classifier. It neither reads nor invokes a hidden evaluator.
    """
    nodes: dict[str, object] = {}
    links: list[tuple[str, str, str]] = []
    for node in task.graph.nodes:
        nodes[f"state:{node.node_id}"] = {
            "kind": "state",
            "initial": node.node_id == task.graph.start_node,
            "terminal": node.node_id in task.graph.terminal_nodes,
        }
    fact_names = set(task.contract.initial_facts) | set(task.contract.goal_all)
    for contract in task.contract.actions.values():
        fact_names.update((*contract.requires, *contract.adds, *contract.removes))
    for name in fact_names:
        nodes[f"fact:{name}"] = {
            "kind": "fact",
            "initial": name in task.contract.initial_facts,
            "goal": name in task.contract.goal_all,
        }
    for edge in task.graph.edges:
        key = f"action:{edge.edge_id}"
        nodes[key] = {"kind": "action"}
        if include_tools:
            nodes[key] = {
                "kind": "action",
                "tool": edge.action.tool,
                "arguments": _shape(edge.action.arguments),
                "prerequisite_actions": len(edge.action.requires_prior_actions),
                "authority": sorted((atom.resource, atom.operation) for atom in edge.authority),
            }
        links.extend(
            ((f"state:{edge.source}", key, "outgoing"), (key, f"state:{edge.target}", "next"))
        )
        contract = task.contract.actions[edge.edge_id]
        for relation in ("requires", "adds", "removes"):
            for name in getattr(contract, relation):
                links.append((key, f"fact:{name}", relation))
    for index, approval in enumerate(task.contract.approvals):
        key = f"approval:{index}"
        nodes[key] = {"kind": "approval", "validity": approval.validity_decisions}
        for edge_id in approval.edge_ids:
            links.append((key, f"action:{edge_id}", "offers"))
    neighbors: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for source, target, relation in links:
        neighbors[source].append(("out", relation, target))
        neighbors[target].append(("in", relation, source))
    colors = {name: content_hash(value) for name, value in nodes.items()}
    for _ in range(len(nodes)):
        colors = {
            name: content_hash(
                [
                    colors[name],
                    sorted(
                        (direction, relation, colors[other])
                        for direction, relation, other in neighbors[name]
                    ),
                ]
            )
            for name in nodes
        }
    return content_hash(sorted(colors.values()))


def overlap_screen(tasks: Sequence[tuple[str, PublicRecoveryTask]]) -> dict[str, object]:
    records = []
    for split, task in tasks:
        records.append(
            {
                "task_id": task.contract.task_id,
                "split": split,
                "typed_structure": structure_fingerprint(task, include_tools=True),
                "dependency_structure": structure_fingerprint(task, include_tools=False),
            }
        )
    matches = []
    for kind in ("typed_structure", "dependency_structure"):
        groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in records:
            groups[row[kind]].append({"task_id": row["task_id"], "split": row["split"]})
        for fingerprint, members in sorted(groups.items()):
            if len(members) < 2:
                continue
            matches.append(
                {
                    "screen": kind,
                    "fingerprint": fingerprint,
                    "members": members,
                    "cross_split": len({row["split"] for row in members}) > 1,
                    "disposition": "requires_semantic_review",
                }
            )
    return {
        "schema": "ecpa-public-structure-screen-1",
        "task_count": len(tasks),
        "matches": matches,
        "independence_certified": False,
        "limitations": [
            "Matching abstractions can hide different obligations; inspect source semantics.",
            "Different abstractions can repeat an obligation; absence is not acceptance.",
            "Family labels and provider/entity names do not establish independence.",
        ],
    }
