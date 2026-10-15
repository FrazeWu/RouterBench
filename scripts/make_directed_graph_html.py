#!/usr/bin/env python3
"""Add an explicit directed-graph presentation to the complex sample."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "artifacts/private/show-me-large-v1-complex.html"
dst = ROOT / "artifacts/private/show-me-large-v1-directed.html"
text = src.read_text(encoding="utf-8")

# Keep the audited graph data unchanged; alter only the visual grammar.
text = text.replace(
    '<svg id="graph" role="img" aria-label="large-v1 完整复杂候选图"></svg>',
    '''<svg id="graph" role="img" aria-label="large-v1 完整复杂候选有向图">
<defs>
 <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#9aa6b8"/></marker>
 <marker id="arrow-safe" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#079669"/></marker>
 <marker id="arrow-attack" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#d33e5c"/></marker>
</defs></svg>'''
)
text = text.replace(
    "p.setAttribute('class','edge '+(safe.has(e.edge_id)?'safe':attack.has(e.edge_id)?'attack':''));p.setAttribute('data-id',e.edge_id);",
    "p.setAttribute('class','edge '+(safe.has(e.edge_id)?'safe':attack.has(e.edge_id)?'attack':''));p.setAttribute('marker-end',safe.has(e.edge_id)?'url(#arrow-safe)':attack.has(e.edge_id)?'url(#arrow-attack)':'url(#arrow)');p.setAttribute('data-id',e.edge_id);"
)
text = text.replace(
    ".edge{fill:none;stroke:#c2c9d5;stroke-width:1.3;opacity:.65}",
    ".edge{fill:none;stroke:#aeb8c7;stroke-width:1.5;opacity:.72;marker-end:url(#arrow)}"
)
text = text.replace(
    ".edge.safe{stroke:#079669;stroke-width:4;opacity:1}",
    ".edge.safe{stroke:#079669;stroke-width:4;opacity:1;marker-end:url(#arrow-safe)}"
)
text = text.replace(
    ".edge.attack{stroke:#d33e5c;stroke-width:3.5;stroke-dasharray:8 5;opacity:1}",
    ".edge.attack{stroke:#d33e5c;stroke-width:3.5;stroke-dasharray:8 5;opacity:1;marker-end:url(#arrow-attack)}"
)
text = text.replace(
    "<h1>large_v1：rblg_f7_003_signed_release_candidate</h1>",
    "<h1>large_v1：rblg_f7_003_signed_release_candidate · 有向图</h1>"
)
text = text.replace(
    "<div class=\"sub\">完整候选有向图 · 评测器审计通过 · 绿色为唯一最优路径，红色为禁止攻击路径</div>",
    "<div class=\"sub\">完整候选有向图 · 箭头表示执行方向 · 绿色为唯一最优路径 · 红色为禁止攻击路径</div>"
)
dst.write_text(text, encoding="utf-8")
print(dst)
