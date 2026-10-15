#!/usr/bin/env python3
"""Export a compact, publication-style vector figure for the complex graph."""
from pathlib import Path
from collections import defaultdict
import json, re
import networkx as nx
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "artifacts/private/show-me-large-v1-organic.html"
OUT = ROOT / "output/pdf/routebench-large-v1-complex-paper-figure.pdf"

def read_data():
    text = HTML.read_text(encoding="utf-8")
    m = re.search(r"const DATA=(\{.*?\});\s*const safe=", text, re.S)
    if not m:
        raise RuntimeError("DATA payload not found")
    return json.loads(m.group(1))

def main():
    data = read_data()
    nodes, edges = data["nodes"], data["edges"]
    safe, attack = set(data["safe"]), set(data["attack"])
    graph = nx.DiGraph()
    graph.add_nodes_from(n["node_id"] for n in nodes)
    graph.add_edges_from((e["source"], e["target"]) for e in edges)
    raw = nx.spring_layout(graph, seed=23, k=3.0, iterations=650, weight=None)
    xs, ys = zip(*raw.values())
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)

    # Larger landscape canvas keeps the 51-node topology legible in print.
    W, H = 1100, 700
    c = canvas.Canvas(str(OUT), pagesize=(W, H))
    c.setTitle("RouteBench large-v1 complex directed graph")
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    pdfmetrics.registerFont(TTFont("DVSans", font_path))
    c.setFont("DVSans", 8.5)
    c.setFillColor(colors.HexColor("#1b2433"))
    c.drawString(25, H - 24, "RouteBench large-v1: complex capability-routing graph")
    c.setFont("DVSans", 6.4)
    c.setFillColor(colors.HexColor("#5e6b7d"))
    c.drawString(25, H - 37, "51 nodes, 66 edges, 1,368 terminal paths; colored edges mark evaluator-defined routes")

    left, right, bottom, top = 52, W - 140, 76, H - 82
    def pos(node):
        x, y = raw[node]
        return left + (x - lo_x) / (hi_x - lo_x) * (right - left), bottom + (y - lo_y) / (hi_y - lo_y) * (top - bottom)

    node_w, node_h = 92, 28
    edge_by_id = {e["edge_id"]: e for e in edges}
    safe_targets = {edge_by_id[i]["target"] for i in safe}
    attack_targets = {edge_by_id[i]["target"] for i in attack}
    incoming_tool = {}
    for edge in edges:
        incoming_tool.setdefault(edge["target"], edge["action"]["tool"])

    # Draw all candidate edges first, then highlighted routes on top.
    for edge in edges:
        x1, y1 = pos(edge["source"]); x2, y2 = pos(edge["target"])
        highlighted = edge["edge_id"] in safe or edge["edge_id"] in attack
        if edge["edge_id"] in safe:
            stroke, width, dash = colors.HexColor("#087f5b"), 1.55, None
        elif edge["edge_id"] in attack:
            stroke, width, dash = colors.HexColor("#c23b56"), 1.35, (3, 2)
        else:
            stroke, width, dash = colors.HexColor("#b7c0cc"), 0.48, None
        c.setStrokeColor(stroke); c.setLineWidth(width)
        if dash: c.setDash(*dash)
        else: c.setDash()
        bow = ((sum(ord(ch) for ch in edge["edge_id"]) % 7) - 3) * 3.6
        p = c.beginPath(); p.moveTo(x1 + node_w, y1)
        p.curveTo(x1 + node_w + 18, y1 + bow, x2 - 18, y2 - bow, x2, y2)
        c.drawPath(p)
        # Compact arrowhead at the target side.
        c.setFillColor(stroke)
        c.saveState(); c.translate(x2, y2); c.rotate(0 if abs(x2 - x1) > abs(y2 - y1) else 90)
        arrow = c.beginPath(); arrow.moveTo(0, 0); arrow.lineTo(-3.3, 1.8); arrow.lineTo(-3.3, -1.8); arrow.close(); c.drawPath(arrow, fill=1, stroke=0)
        c.restoreState()
        if highlighted:
            c.setFont("DVSans", 4.8); c.setFillColor(stroke)
            tag = "exact" if edge["edge_id"] in safe else "forbidden"
            c.drawString((x1 + x2) / 2 - 8, (y1 + y2) / 2 + 3, tag)

    # Nodes and labels.
    for node in nodes:
        node_id = node["node_id"]; x, y = pos(node_id)
        if node_id in safe_targets: stroke = colors.HexColor("#087f5b")
        elif node_id in attack_targets: stroke = colors.HexColor("#c23b56")
        else: stroke = colors.HexColor("#9da9b8")
        c.setFillColor(colors.white); c.setStrokeColor(stroke); c.setLineWidth(1.15 if node_id in safe_targets or node_id in attack_targets else .55)
        c.roundRect(x, y - node_h / 2, node_w, node_h, 3, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#1b2433")); c.setFont("DVSans", 6.3)
        def node_label(name):
            if name == "start": return "START", "task begins"
            if name == "completed_safe": return "SUCCESS", "file.write"
            if name == "completed_attack": return "ATTACK", "network.send"
            if name == "completed_wrong": return "WRONG VALUE", "stale file.write"
            if name == "attack_ready": return "ATTACK PREP", "file.write"
            m0 = re.match(r"stage_(\d+)$", name)
            if m0: return f"M{m0.group(1)} exact", incoming_tool.get(name, "")
            stale = re.match(r"finish_wrong_relay_(\d+)", name)
            if stale: return f"stale relay-{stale.group(1)}", "file.write"
            m = re.match(r"stage_(\d+)_(.*)", name)
            if not m: return name.upper(), incoming_tool.get(name, "")
            i, kind = m.groups()
            if kind == "optimal": return f"M{i} exact", incoming_tool.get(name, "")
            if kind == "overprivileged": return f"M{i} broad", incoming_tool.get(name, "")
            if kind == "over_delay": return f"M{i} delayed", incoming_tool.get(name, "")
            if kind == "over_short": return f"M{i} broad-short", incoming_tool.get(name, "")
            if kind == "alternate": return f"M{i} alternate", incoming_tool.get(name, "")
            relay = re.search(r"relay_(\d+)", kind)
            if relay: return f"M{i} relay-{relay.group(1)}", incoming_tool.get(name, "")
            return f"M{i} {kind}", incoming_tool.get(name, "")
        line1, line2 = node_label(node_id)
        c.drawCentredString(x + node_w / 2, y + 4.2, line1)
        c.setFont("DVSans", 5.0); c.setFillColor(colors.HexColor("#5e6b7d"))
        c.drawCentredString(x + node_w / 2, y - 6.2, line2)

    # Legend and caption.
    y = 24; c.setFont("DVSans", 5.8); c.setFillColor(colors.HexColor("#39465a"))
    c.setStrokeColor(colors.HexColor("#087f5b")); c.setLineWidth(1.6); c.line(27, y, 44, y); c.drawString(48, y - 1.8, "evaluator optimum (10 actions)")
    c.setStrokeColor(colors.HexColor("#c23b56")); c.setDash(3, 2); c.line(170, y, 187, y); c.setDash(); c.drawString(191, y - 1.8, "forbidden-effect route")
    c.setStrokeColor(colors.HexColor("#b7c0cc")); c.setLineWidth(.6); c.line(315, y, 332, y); c.drawString(336, y - 1.8, "candidate edge")
    c.setFont("DVSans", 5.6); c.setFillColor(colors.HexColor("#5e6b7d")); c.drawString(25, 10, "M = dependency milestone; exact = least-authority branch; broad/alternate/delayed = decoy branches")
    c.save()
    print(OUT)

if __name__ == "__main__":
    main()
