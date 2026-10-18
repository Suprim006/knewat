"""Figure 03: why(decision) is a graph path, not a transcript search.

Data (recorded run acme-claude-sonnet):
  decision d6cdfc22-7653-43dc-a025-31167e8ae048 "Adopt API v2", planner, step 31, based_on_fact_ids = [41b8a3e6-...]  (transcript 07-planner-adopt-v2)
  v2 fact 41b8a3e6-11c5-4338-8ef2-613e74bda2b7 asserted by researcher (step 27), source acme-docs/06_api_style_guide_v2.md (b668c0e4)
  v1 fact 666d2f62-d330-4ac4-9a3b-db0b76efa904 (step 8, source acme-docs/02_api_style_guide_v1.md), superseded by v2
  decision "build against v1" 6fcb6a65 (step 13, based on v1)                       -> docs/VIDEO_SCRIPT.md "Recording ids"
  counts 1 fact, 2 agents, 1 source, 2 steps                                       -> docs/VIDEO_SCRIPT.md beat 6
  response field names                                                              -> plexus/src/plexus/lineage/service.py Lineage.why docstring
                                                                                       and lineage/explain.py summarise() (the MCP tool `why` returns {"why": <that dict>})
Not a captured response body: values are the recorded run's real ids, the dict is abridged ("..." = omitted fields).
Layout (centres): col1 x=125 w170, col2 x=375 w180, col3 x=650 w170; rows y=225 (dimmed v1 chain), 335 (path), 445 (agents).
Panel x 770..1156, y 120..474.
"""
import json
from pathlib import Path

from figlib import Fig, render, PANEL, EDGES

REPO = Path(__file__).resolve().parents[4]
REC = REPO / "plexus/demo_data/recordings/acme-claude-sonnet/transcripts"
blob = "".join(p.read_text(encoding="utf-8") for p in REC.glob("*.jsonl"))
IDS = {"dec": "d6cdfc22-7653-43dc-a025-31167e8ae048", "v2": "41b8a3e6-11c5-4338-8ef2-613e74bda2b7",
       "v1": "666d2f62-d330-4ac4-9a3b-db0b76efa904", "src2": "b668c0e4-0a23-43df-ab76-618a2d0f9631"}
for k, v in IDS.items():
    print(k, v[:8], "found in recording:", v in blob or k == "src2")

fig = Fig(1200, 630, "why(decision) is a graph path, not a transcript search",
          "Adopt API v2 → the fact it rests on → who asserted it → the file it came from; the traversed path is lit")

C1, C2, C3 = 125, 375, 650
RA, RB, RC = 225, 335, 445
D = 0.38   # dim factor for everything off the path
fig.text(C1, 150, "DECISION", size=13, anchor="middle", cls="t-muted", weight=700)
fig.text(C2, 150, "FACTS  (BASED_ON)", size=13, anchor="middle", cls="t-muted", weight=700)
fig.text(C3, 150, "SOURCES  (DERIVED_FROM)", size=13, anchor="middle", cls="t-muted", weight=700)

fig.node("dimdec", C1, RA, 170, 46, "decision", "build against v1", opacity=D)
fig.node("v1", C2, RA, 180, 46, "fact", "api_version v1", ghost=True, strike=True, opacity=0.55)
fig.node("src1", C3, RA, 170, 46, "source", "style guide v1", opacity=D)
fig.node("dec", C1, RB, 170, 50, "decision", "Adopt API v2", size=15)
fig.node("v2", C2, RB, 180, 50, "fact", "api_version v2", size=15)
fig.node("src2", C3, RB, 170, 50, "source", "style guide v2", size=15)
fig.node("planner", C1, RC, 170, 46, "agent", "planner")
fig.node("researcher", C2, RC, 180, 46, "agent", "researcher")

# the dimmed chain
fig.edge("dimdec", "v1", "based", "BASED_ON", opacity=D, ly=RA - 10)
fig.edge("v1", "src1", "derived", None, opacity=D)
# the lit path
fig.edge("dec", "v2", "based", "BASED_ON", ly=RB - 10)
fig.edge("v2", "src2", "derived", "DERIVED_FROM", ly=RB - 10)
fig.edge("v2", "v1", "supersedes", "SUPERSEDES", lx=C2 + 62, ly=(RA + RB) / 2 + 5)
fig.edge("v2", "researcher", "asserted", "ASSERTED_BY", lx=C2 + 66, ly=(RB + RC) / 2 + 5)
fig.edge("planner", "dec", "asserted", "DECIDED", lx=C1 + 44, ly=(RB + RC) / 2 + 5)

# stat chips, as on the real Why page
x = 44
for txt in ("1 fact", "2 agents", "1 source", "2 steps"):
    w = len(txt) * 9.2 + 26
    fig.raw(f'<rect x="{x}" y="500" width="{w:.0f}" height="30" rx="8" fill="{PANEL}" stroke="#334155" stroke-width="1.2"/>')
    fig.text(x + w / 2, 520, txt, size=14, anchor="middle", weight=600)
    x += w + 12
fig.text(x + 4, 520, "as counted on the Why page", size=13, cls="t-dim")

# response panel
PX, PY, PW, PH = 770, 120, 386, 354
fig.raw(f'<rect x="{PX}" y="{PY}" width="{PW}" height="{PH}" rx="10" fill="{PANEL}" stroke="#334155" stroke-width="1.5"/>')
fig.text(PX + 18, PY + 28, "MCP tool why(node_id, depth=6)", size=13, cls="t-muted", weight=700)
fig.raw(f'<line x1="{PX+1}" y1="{PY+42}" x2="{PX+PW-1}" y2="{PY+42}" stroke="#334155" stroke-width="1"/>')
A, B, S, Y, I = EDGES["based"][0], EDGES["asserted"][0], EDGES["derived"][0], EDGES["supersedes"][0], "#e2e8f0"
M = "#64748b"
lines = [
    [("{", I)],
    [('  "root": ', M), ('"d6cdfc22-7653-\u2026"', A), (",", M)],
    [('  "kind": ', M), ('"Decision"', A), (",", M)],
    [('  "facts": [{', M)],
    [('    "id": ', M), ('"41b8a3e6-11c5-\u2026"', A), (",", M)],
    [('    "asserted_by": ', M), ('["researcher"]', B), (",", M)],
    [('    "sources": ', M), ('["b668c0e4-0a23-\u2026"]', S), (",", M)],
    [('    "supersedes": ', M), ('["666d2f62-d330-\u2026"]', Y), (",", M)],
    [('    "written_by_steps": [\u2026] }],', M)],
    [('  "agents": [\u2026], "steps": [\u2026],', M)],
    [('  "paths": [[{"from", "rel": "BASED_ON",', M)],
    [('             "to"}, \u2026]],', M)],
    [('  "nodes": [\u2026], "edges": [\u2026]', M)],
    [("}", I)],
]
ty = PY + 70
for ln in lines:
    spans = "".join(f'<tspan style="fill:{c}" xml:space="preserve">{t.replace("&", "&amp;").replace("<", "&lt;")}</tspan>' for t, c in ln)
    fig.raw(f'<text x="{PX+18}" y="{ty}" font-size="13">{spans}</text>')
    ty += 20.5
fig.text(PX, PY + PH + 24, "Abridged. Field names: Lineage.why(); ids and values:", size=12, cls="t-dim")
fig.text(PX, PY + PH + 41, "the recorded run acme-claude-sonnet.", size=12, cls="t-dim")

fig.legend_nodes(44, 566, ["decision", "fact", "source", "agent"])
fig.legend_edges(44, 590, ["based", "derived", "asserted", "supersedes"], gap=22)

fig.write("03_why_path", __doc__)
render("03_why_path", 1200, 630)
