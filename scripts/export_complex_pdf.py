#!/usr/bin/env python3
"""Export the large-v1 interactive graph to a static, reviewable PDF."""
from __future__ import annotations

import json
import re
from pathlib import Path
from collections import defaultdict, deque

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "artifacts/private/show-me-large-v1-complex.html"
OUT = ROOT / "output/pdf/show-me-large-v1-complex.pdf"


def load_data() -> dict:
    text = HTML.read_text(encoding="utf-8")
    match = re.search(r"const DATA=(\{.*?\});\s*const safe=", text, re.S)
    if not match:
        raise RuntimeError("DATA payload not found in HTML")
    return json.loads(match.group(1))


def main() -> None:
    data = load_data()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if Path(font).exists():
        pdfmetrics.registerFont(TTFont("NotoCJK", font))
        face = "NotoCJK"
    else:
        face = "Helvetica"

    nodes = data["nodes"]
    edges = data["edges"]
    safe = set(data["safe"])
    attack = set(data["attack"])
    audit = data["audit"]
    by_id = {n["node_id"]: n for n in nodes}
    outgoing = defaultdict(list)
    for e in edges:
        outgoing[e["source"]].append(e)

    depth = {"start": 0}
    queue = deque(["start"])
    while queue:
        cur = queue.popleft()
        for edge in outgoing[cur]:
            if edge["target"] not in depth:
                depth[edge["target"]] = depth[cur] + 1
                queue.append(edge["target"])
    for n in nodes:
        depth.setdefault(n["node_id"], 0)
    groups = defaultdict(list)
    for n in nodes:
        groups[depth[n["node_id"]]].append(n["node_id"])

    c = canvas.Canvas(str(OUT), pagesize=landscape(A3))
    page_w, page_h = landscape(A3)
    margin = 28
    c.setTitle("RouteBench large-v1 complex execution graph")

    # Page 1: complete graph overview.
    c.setFont(face, 20)
    c.setFillColor(colors.HexColor("#182235"))
    c.drawString(margin, page_h - 34, "RouteBench large_v1 complex execution graph")
    c.setFont(face, 10)
    c.setFillColor(colors.HexColor("#647089"))
    c.drawString(margin, page_h - 51, "rblg_f7_003_signed_release_candidate | green = evaluator optimum | red dashed = forbidden effect")

    graph_x, graph_y = margin, 60
    graph_w, graph_h = page_w - 2 * margin, page_h - 130
    max_depth = max(depth.values())
    max_rows = max(len(v) for v in groups.values())
    x_gap = graph_w / max(1, max_depth)
    y_gap = graph_h / max(1, max_rows)
    pos = {}
    for d, ids in groups.items():
        for i, node_id in enumerate(ids):
            pos[node_id] = (graph_x + (d / max(1, max_depth)) * (graph_w - 100), graph_y + graph_h - (i + 1) * y_gap)

    safe_targets = {next(e["target"] for e in edges if e["edge_id"] == edge_id) for edge_id in safe}
    attack_targets = {next(e["target"] for e in edges if e["edge_id"] == edge_id) for edge_id in attack}
    node_w, node_h = 115, 25

    for edge in edges:
        x1, y1 = pos[edge["source"]]
        x2, y2 = pos[edge["target"]]
        if edge["edge_id"] in safe:
            col, width, dash = colors.HexColor("#079669"), 2.4, None
        elif edge["edge_id"] in attack:
            col, width, dash = colors.HexColor("#d33e5c"), 1.8, (5, 3)
        else:
            col, width, dash = colors.HexColor("#c2c9d5"), 0.55, None
        p = c.beginPath()
        # Use a real spline: the vertical bow separates parallel branches and
        # makes the diagram read as a graph rather than a set of straight links.
        bow = ((sum(ord(ch) for ch in edge["edge_id"]) % 9) - 4) * 9
        p.moveTo(x1 + node_w, y1 + node_h / 2)
        p.curveTo(
            x1 + node_w + 24, y1 + node_h / 2 + bow,
            x2 - 24, y2 + node_h / 2 - bow,
            x2, y2 + node_h / 2,
        )
        c.setStrokeColor(col)
        c.setLineWidth(width)
        if dash:
            c.setDash(*dash)
        else:
            c.setDash()
        c.drawPath(p)

    for node_id, (x, y) in pos.items():
        if node_id in safe_targets:
            stroke = colors.HexColor("#079669")
            sw = 1.7
        elif node_id in attack_targets:
            stroke = colors.HexColor("#d33e5c")
            sw = 1.5
        else:
            stroke = colors.HexColor("#aab4c4")
            sw = 0.7
        c.setFillColor(colors.white)
        c.setStrokeColor(stroke)
        c.setLineWidth(sw)
        c.roundRect(x, y, node_w, node_h, 4, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#182235"))
        c.setFont(face, 6.2)
        label = node_id if len(node_id) <= 19 else node_id[:18] + "…"
        c.drawCentredString(x + node_w / 2, y + 9, label)

    # Legend and audit counts.
    ly = 30
    c.setFont(face, 8)
    c.setFillColor(colors.HexColor("#182235"))
    c.setStrokeColor(colors.HexColor("#079669")); c.setLineWidth(2.4); c.line(margin, ly + 3, margin + 22, ly + 3)
    c.setFillColor(colors.HexColor("#182235")); c.drawString(margin + 28, ly, "Optimal route (10 actions)")
    c.setStrokeColor(colors.HexColor("#d33e5c")); c.setDash(5, 3); c.line(margin + 170, ly + 3, margin + 192, ly + 3); c.setDash()
    c.setFillColor(colors.HexColor("#182235")); c.drawString(margin + 198, ly, "Forbidden-effect route")
    c.drawRightString(page_w - margin, ly, f"{len(nodes)} nodes | {len(edges)} edges | {audit['total_terminal_paths']} terminal paths | {audit['attack_paths']} attack paths")
    c.showPage()

    # Page 2: what makes it complex and the evaluator-owned route.
    c.setFont(face, 20); c.setFillColor(colors.HexColor("#182235")); c.drawString(margin, page_h - 38, "Complexity and evaluator-owned optimum")
    c.setFont(face, 10); c.setFillColor(colors.HexColor("#647089")); c.drawString(margin, page_h - 57, "The model must choose the exact-authority branch at every dependency milestone.")
    y = page_h - 92
    c.setFont(face, 11); c.setFillColor(colors.HexColor("#182235")); c.drawString(margin, y, "Audit summary")
    y -= 22
    metrics = [
        ("Terminal paths", audit["total_terminal_paths"]),
        ("Optimal actions", audit["optimal_action_count"]),
        ("Optimal branch points", audit["optimal_branch_points"]),
        ("Attack paths", audit["attack_paths"]),
        ("Functional but overprivileged", audit["functional_overprivileged_paths"]),
        ("Non-functional paths", audit["nonfunctional_paths"]),
        ("Shared-prefix decoys", audit["shared_prefix_decoys"]),
    ]
    for label, value in metrics:
        c.setFillColor(colors.HexColor("#f5f7fb")); c.roundRect(margin, y - 3, 255, 20, 4, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#182235")); c.setFont(face, 9); c.drawString(margin + 8, y + 3, label)
        c.setFont(face, 10); c.drawRightString(margin + 245, y + 3, str(value)); y -= 27

    c.setFont(face, 11); c.setFillColor(colors.HexColor("#182235")); c.drawString(335, page_h - 92, "Evaluator optimum")
    y2 = page_h - 120
    for i, edge_id in enumerate(data["safe"], 1):
        edge = next(e for e in edges if e["edge_id"] == edge_id)
        text = f"{i:02d}. {edge['source']} -> {edge['target']}    {edge['action']['tool']}"
        c.setFont(face, 8.7); c.setFillColor(colors.HexColor("#182235")); c.drawString(335, y2, text[:110]); y2 -= 22

    c.setFont(face, 11); c.setFillColor(colors.HexColor("#182235")); c.drawString(335, y2 - 10, "Why this is harder than a simple chain")
    notes = [
        "Each milestone has exact, broader, alternate-provider, delayed, and forbidden-effect choices.",
        "Many decoys rejoin the safe state, so local success does not imply minimum authority.",
        "The graph contains 1,368 terminal paths but only one public exact optimum.",
        "A valid completion must satisfy both dependency order and the authority boundary.",
    ]
    y2 -= 35
    for note in notes:
        c.setFont(face, 9); c.setFillColor(colors.HexColor("#182235")); c.drawString(350, y2, "• " + note); y2 -= 25
    c.setFont(face, 8); c.setFillColor(colors.HexColor("#647089")); c.drawString(margin, 28, "Static export of the interactive graph; no model evaluation results are implied by this diagram.")
    c.save()
    print(OUT)


if __name__ == "__main__":
    main()
