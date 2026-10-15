#!/usr/bin/env python3
"""Create an organic, force-directed view of the audited directed graph."""
from pathlib import Path
import json
import re
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "artifacts/private/show-me-large-v1-directed.html"
dst = ROOT / "artifacts/private/show-me-large-v1-organic.html"
text = src.read_text(encoding="utf-8")
match = re.search(r"const DATA=(\{.*?\});\s*const safe=", text, re.S)
if not match:
    raise RuntimeError("DATA payload not found")
data = json.loads(match.group(1))

graph = nx.DiGraph()
graph.add_nodes_from(n["node_id"] for n in data["nodes"])
graph.add_edges_from((e["source"], e["target"]) for e in data["edges"])
# Seeded layout makes the figure organic but reproducible across runs.
positions = nx.spring_layout(graph, seed=23, k=1.15, iterations=260, weight=None)
xs = [float(p[0]) for p in positions.values()]
ys = [float(p[1]) for p in positions.values()]
lo_x, hi_x = min(xs), max(xs)
lo_y, hi_y = min(ys), max(ys)
def scale_x(v):
    return 110 + (v - lo_x) / max(hi_x - lo_x, 1e-9) * 1580
def scale_y(v):
    return 75 + (hi_y - v) / max(hi_y - lo_y, 1e-9) * 900

pos_literal = ",".join(
    f"['{node}',{{x:{scale_x(positions[node][0]):.1f},y:{scale_y(positions[node][1]):.1f}}}]"
    for node in graph.nodes
)
replacement = f"const pos=new Map([{pos_literal}]); const ns="
text, count = re.subn(
    r"const pos=new Map\(\);Object\.entries\(groups\)\.forEach\(\(\[d,arr\]\)=>arr\.forEach\(\(n,i\)=>pos\.set\(n\.node_id,\{x:55\+Number\(d\)\*190,y:35\+i\*52\}\)\)\); const ns=",
    replacement,
    text,
)
if count != 1:
    raise RuntimeError(f"position block replacement count={count}")
text = text.replace("const maxD=Math.max(...Object.keys(groups).map(Number)), maxRows=Math.max(...Object.values(groups).map(x=>x.length)); const W=(maxD+1)*190+100,H=Math.max(680,maxRows*52+80), svg=", "const W=1800,H=1050, svg=")
text = text.replace("<h1>large_v1：rblg_f7_003_signed_release_candidate · 有向图</h1>", "<h1>large_v1：rblg_f7_003_signed_release_candidate · 有向拓扑图</h1>")
text = text.replace("<div class=\"sub\">完整候选有向图 · 箭头表示执行方向 · 绿色为唯一最优路径 · 红色为禁止攻击路径</div>", "<div class=\"sub\">力导向候选有向图 · 节点位置表示拓扑关系，不代表执行顺序 · 箭头表示执行方向</div>")
dst.write_text(text, encoding="utf-8")
print(dst)
