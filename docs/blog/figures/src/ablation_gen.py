"""Figure 04: ablation. Remove the edges and the memory can no longer say why.

ONE generator draws the same 14-node layout twice (draw_panel); the right panel only differs by `ablated=True`, which
turns the four stripped edge types into faint ghost lines with a red cross and outlines the nodes that lost them.

Graph = the Crucible ablation seed (knewat/src/knewat/crucible/ablation.py seed()): agent builder; tasks T1..T5 with
T2->T1, T3->T2, T4->T3 (DEPENDS_ON); sources acme-spec, team-wiki; facts version v1 (f1), database (f2),
digest (f3, derived from f1+f2), owner (f4), version v2 (f1b, SUPERSEDES f1); decision d1 BASED_ON f1+f2;
DERIVED_FROM f1,f2 -> acme-spec, f4 -> team-wiki, f3 -> f1,f2. READ is drawn once (builder -> f1): the JSON counts 8 READ
edges, the exact Step->Fact endpoints are not drawn.
Numbers (nothing typed): knewat/src/knewat/crucible/results/latest-all.json
  layers.ablation.summary.{capabilities_needing_edges, broken_by_ablation, controls, controls_unaffected}
  layers.ablation.edges_before / edges_deleted               (DEPENDS_ON 3, BASED_ON 2, DERIVED_FROM 5, READ 8)
  layers.ablation.l1_rerun.{P,P-abl}.C4.violations_total.started_before_deps_done   (0 vs 181)
  layers.ablation.l1_rerun.{P,P-abl}.C8.violations_total.derived_facts_still_returned (0 vs 60)
  (same figures quoted in docs/BASELINE.md lines 151-154)
Layout (1400x600): panel A origin (56,148), panel B origin (736,148); local rows y: sources 20, facts 115, decision 210, tasks 292.
"""
import json
from pathlib import Path

from figlib import Fig, render, PANEL, EDGES

REPO = Path(__file__).resolve().parents[4]
J = json.loads((REPO / "knewat/src/knewat/crucible/results/latest-all.json").read_text(encoding="utf-8"))
ab = J["layers"]["ablation"]
S = ab["summary"]
rr = ab["l1_rerun"]
early_i = rr["P"]["C4"]["violations_total"]["started_before_deps_done"]
early_a = rr["P-abl"]["C4"]["violations_total"]["started_before_deps_done"]
forg_i = rr["P"]["C8"]["violations_total"]["derived_facts_still_returned"]
forg_a = rr["P-abl"]["C8"]["violations_total"]["derived_facts_still_returned"]
n_edges = sum(ab["edges_before"].values())
n_left = sum(ab["edges_before"].values()) - sum(ab["edges_deleted"].values())
print("plotted:", dict(cap=S["capabilities_needing_edges"], broken=S["broken_by_ablation"], intact_pass=S["intact_all_pass"],
                       controls=S["controls"], controls_ok=S["controls_unaffected"], early=(early_i, early_a),
                       forgotten=(forg_i, forg_a), edges=(n_edges, n_left), by_type=ab["edges_before"]))

W, H = 1400, 600
fig = Fig(W, H, "Remove the edges and the memory can no longer say why",
          "Same graph, same nodes; the right copy has DEPENDS_ON, BASED_ON, DERIVED_FROM and READ deleted")

NW, NH = 92, 34
LAYOUT = {  # id: (kind, label, local x, local y)
    "builder": ("agent", "builder", 52, 22),
    "src1": ("source", "acme-spec", 315, 20), "src2": ("source", "team-wiki", 565, 20),
    "f1": ("fact", "version v1", 165, 115), "f3": ("fact", "digest", 315, 115),
    "f2": ("fact", "database", 455, 115), "f4": ("fact", "owner", 565, 115),
    "f1b": ("fact", "version v2", 165, 210), "d1": ("decision", "decision", 315, 210),
    "T1": ("task", "T1 research", 55, 292), "T2": ("task", "T2 design", 180, 292), "T3": ("task", "T3 build", 305, 292),
    "T4": ("task", "T4 test", 430, 292), "T5": ("task", "T5 readme", 555, 292),
}
EDGE_LIST = [  # (from, to, type)
    ("T2", "T1", "depends"), ("T3", "T2", "depends"), ("T4", "T3", "depends"),
    ("d1", "f1", "based"), ("d1", "f2", "based"),
    ("f1", "src1", "derived"), ("f2", "src1", "derived"), ("f4", "src2", "derived"), ("f3", "f1", "derived"), ("f3", "f2", "derived"),
    ("builder", "f1", "read"),
    ("f1b", "f1", "supersedes"),
]
DROPPED = {"depends", "based", "derived", "read"}
ORPHANED = {"f1", "f2", "f3", "f4", "d1", "T2", "T3", "T4"}   # nodes that lost an edge they depended on


def draw_panel(ox, oy, ablated, p):
    n = lambda i: f"{p}{i}"  # noqa: E731
    for i, (kind, label, x, y) in LAYOUT.items():
        out = "#f87171" if (ablated and i in ORPHANED) else None
        fig.node(n(i), ox + x, oy + y, NW, NH, kind, label, outline=out, size=13)
    for a, b, t in EDGE_LIST:
        ghost = ablated and t in DROPPED
        lbl = None
        if t == "supersedes":
            lbl = "SUPERSEDES"
        if t == "read" and not ablated:
            lbl = "READ x8"
        lpos = {"supersedes": (ox + 195, oy + 170), "read": (ox + 142, oy + 66)}.get(t, (None, None))
        p0, p1 = fig.edge(n(a), n(b), t, lbl, ghost=ghost, lx=lpos[0], ly=lpos[1])
        if ghost:
            fig.cross((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, r=5.5)


# panel backgrounds + headers
for ox, tint, head, sub in ((56, "#1e293b", "WITH EDGES", f"{n_edges} edges of the four types"),
                            (736, "#4c1d24", "EDGES CUT", f"{n_left} edges of the four types left")):
    fig.raw(f'<rect x="{ox-22}" y="116" width="650" height="368" rx="12" fill="rgba(15,23,42,0.55)" stroke="{tint}" stroke-width="1.6"/>', "under")
    fig.text(ox - 4, 142, head, size=14, weight=700, fill="#f8fafc" if ox < 700 else "#fca5a5")
    fig.text(ox + 586, 142, sub, size=13, anchor="end", cls="t-muted")
# draw edges for both panels first (done inside draw_panel via fig.under), nodes via fig.over
draw_panel(56, 168, False, "L_")
draw_panel(736, 168, True, "R_")

# metric lines
cap, brk, ctl, ctl_ok = S["capabilities_needing_edges"], S["broken_by_ablation"], S["controls"], S["controls_unaffected"]
ok_color, bad_color = "#86efac", "#fca5a5"
L = [f"{cap if S['intact_all_pass'] else '?'} of {cap} edge-dependent capabilities work", f"{early_i} tasks start early",
     f"{forg_i} forgotten facts still returned"]
R = [f"{brk} of {cap} edge-dependent capabilities break", f"{early_a} tasks start before their dependencies",
     f"{forg_a} forgotten facts still returned"]
for i, (a, b) in enumerate(zip(L, R)):
    fig.text(56 - 4, 506 + i * 21, a, size=14, weight=600 if i == 0 else 400, fill=ok_color if i == 0 else None)
    fig.text(736 - 4, 506 + i * 21, b, size=14, weight=600 if i == 0 else 400, fill=bad_color)
fig.text(736 + 586, 506, f"{ctl_ok} of {ctl} controls unaffected", size=13, anchor="end", cls="t-muted")

# legend
fig.footer_y = 594
x = fig.legend_nodes(44, 572, ["agent", "fact", "decision", "source", "task"])
fig.raw(f'<rect x="{x}" y="564" width="18" height="16" rx="4" fill="none" stroke="#f87171" stroke-width="2.2" stroke-dasharray="3 3"/>')
fig.text(x + 26, 577, "lost its edges", size=13, cls="t-muted")
fig.legend_edges(x + 170, 572, ["depends", "based", "derived", "read", "supersedes"], gap=14)

fig.write("04_ablation", __doc__, title_y=60, sub_y=90)
render("04_ablation", W, H)
