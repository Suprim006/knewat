"""Figure 01: hero. Three Claude Code agents read and write one graph.

Data: ids / values / steps from the recorded run acme-claude-sonnet:
  knewat/demo_data/recordings/acme-claude-sonnet/meta.json  (inventory.total_nodes / total_edges, steps = tool calls)
  docs/VIDEO_SCRIPT.md "Recording ids" (v1 666d2f62, v2 41b8a3e6, api key 27ed13ad, jwt 608a66f1, decision d6cdfc22,
  style guide 06_api_style_guide_v2.md, security note 04_security_note.md, task t03-design-endpoints)
Layout table (centres, w x h; px at 1x on a 1200x630 card):
  planner 110,185 130x46 | api key 360,185 | jwt 360,315 | security note 190,450 | researcher 560,470
  v1 680,185 | v2 680,315 | decision 900,315 | style guide 900,450 | builder 1085,160 | task 1085,315
"""
import json
from pathlib import Path

from figlib import Fig, render

REPO = Path(__file__).resolve().parents[4]
meta = json.loads((REPO / "knewat/demo_data/recordings/acme-claude-sonnet/meta.json").read_text(encoding="utf-8"))
N, E, CALLS = meta["inventory"]["total_nodes"], meta["inventory"]["total_edges"], meta["steps"]

fig = Fig(1200, 630, "Three Claude Code agents read and write one graph",
          "Knewat: graph memory and coordination for agent teams, on FalkorDB")

# agents
fig.node("planner", 110, 185, 130, 46, "agent", "planner")
fig.node("researcher", 560, 470, 140, 46, "agent", "researcher")
fig.node("builder", 1085, 160, 130, 46, "agent", "builder")
# facts
fig.node("apikey", 360, 185, 160, 46, "fact", "auth: api key")
fig.node("jwt", 360, 315, 160, 46, "fact", "auth: jwt")
fig.node("v1", 680, 185, 160, 46, "fact", "api_version v1", ghost=True, strike=True, opacity=0.8)
fig.node("v2", 680, 315, 160, 46, "fact", "api_version v2")
# decision, sources, task
fig.node("dec", 900, 315, 150, 46, "decision", "Adopt API v2")
fig.node("sg", 900, 450, 160, 46, "source", "style guide v2")
fig.node("sec", 190, 450, 160, 46, "source", "security note")
fig.node("task", 1085, 315, 130, 46, "task", "t03 design")

# edges (drawn behind nodes)
fig.edge("apikey", "planner", "asserted")
fig.edge("jwt", "researcher", "asserted")
fig.edge("v2", "researcher", "asserted")
fig.edge("apikey", "jwt", "contradicts", "CONTRADICTS", lx=428, ly=254)
fig.edge("v2", "v1", "supersedes", "SUPERSEDES", lx=745, ly=254)
fig.edge("dec", "v2", "based", "BASED_ON", ly=296)
fig.edge("v2", "sg", "derived", "DERIVED_FROM", lx=840, ly=398)
fig.edge("jwt", "sec", "derived", "DERIVED_FROM", lx=240, ly=392)
fig.edge("planner", "v1", "read", "READ", curve=-80, ly=140)
fig.edge("builder", "v1", "read", "READ", lx=905, ly=192)
fig.edge("builder", "v2", "read", "READ", lx=870, ly=262)
fig.edge("builder", "task", "depends", "CLAIMED", lx=1128, ly=240)

# legend (outside the diagram) + stat strip
fig.legend_nodes(44, 538, ["agent", "fact", "decision", "source", "task"])
fig.legend_edges(44, 562, ["based", "derived", "asserted", "read", "supersedes", "contradicts"], gap=22)
x = 44
for txt in (f"{CALLS} tool calls", f"{N} nodes", f"{E} edges"):
    w = len(txt) * 9.6 + 28
    fig.raw(f'<rect x="{x}" y="582" width="{w:.0f}" height="30" rx="8" fill="#0f172a" stroke="#334155" stroke-width="1.2"/>')
    fig.text(x + w / 2, 602, txt, size=15, anchor="middle", weight=600)
    x += w + 14
fig.text(x + 6, 602, "recorded run: acme-claude-sonnet", size=13, cls="t-dim")

fig.write("01_hero", __doc__)
render("01_hero", 1200, 630)
