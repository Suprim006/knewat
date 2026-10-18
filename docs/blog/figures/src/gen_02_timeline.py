"""Figure 02: validity timeline. A fact is never overwritten; it is closed and superseded.

Data (all read from the recorded run, nothing typed from memory):
  plexus/demo_data/recordings/acme-claude-sonnet/transcripts/*.jsonl : every assert_fact tool_use -> (step, agent, predicate, value)
  fact id prefixes: docs/VIDEO_SCRIPT.md "Recording ids"; this script asserts each prefix occurs in the transcripts.
  steps = recording meta.json "steps" (83). v1 asserted at step 8, v2 at step 27 (v1 valid_to = 27), jwt step 44, api key step 50.
  cursors at step 17 / 38: VIDEO_SCRIPT beat 5 (what did the builder know at step 17 -> v1, at step 38 -> v2).
Layout: x(step) = X0 + step * (X1 - X0) / STEPS, X0=170, X1=1100.  Lane 1 bars y 190-236, lane 2 jwt 290-326, api key 356-392, axis y 432.
"""
import glob
import json
from pathlib import Path

from figlib import Fig, render, NODES, PANEL

REPO = Path(__file__).resolve().parents[4]
REC = REPO / "plexus/demo_data/recordings/acme-claude-sonnet"
meta = json.loads((REC / "meta.json").read_text(encoding="utf-8"))
STEPS = meta["steps"]

asserts, text_all = {}, ""
for fn in sorted(glob.glob(str(REC / "transcripts/*.jsonl"))):
    raw = Path(fn).read_text(encoding="utf-8")
    text_all += raw
    for line in raw.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "assistant":
            continue
        for c in e["message"].get("content", []):
            if c.get("type") == "tool_use" and c["name"].endswith("assert_fact"):
                i = c["input"]
                asserts[(i["predicate"], i["value"])] = (i["step"], i["agent_id"])

def find(pred, startswith):
    for (p, v), (s, a) in asserts.items():
        if p == pred and v.startswith(startswith):
            return s, a, v
    raise KeyError((pred, startswith))

s_v1, a_v1, _ = find("api_version", "v1")
s_v2, a_v2, _ = find("api_version", "v2")
s_jwt, a_jwt, _ = find("auth_method", "JWT")
s_key, a_key, _ = find("auth_method", "Long-lived API key")
IDS = {"v1": "666d2f62", "v2": "41b8a3e6", "key": "27ed13ad", "jwt": "608a66f1"}   # VIDEO_SCRIPT.md
missing = [k for k, v in IDS.items() if v not in text_all]
print("steps", dict(v1=s_v1, v2=s_v2, jwt=s_jwt, key=s_key), "id prefixes missing from transcripts:", missing)
CUR1, CUR2 = 17, 38   # VIDEO_SCRIPT beat 5

X0, X1 = 170, 1100
def x(step): return X0 + step * (X1 - X0) / STEPS

fig = Fig(1200, 500, "A fact is never overwritten; it is closed and superseded",
          "api_version v1 stays in the graph with valid_to set; as_of(T) reads whichever fact was valid at T")
FILL, STROKE = NODES["fact"][0], NODES["fact"][1]
AFILL, ASTROKE = NODES["agent"][0], NODES["agent"][1]

def bar(x0, x1, y0, y1, label, sub=None, open_end=False, fill=FILL, stroke=STROKE, dash=False, op=1.0, end_text=False):
    r = 7
    d = f'M{x0},{y0+r} Q{x0},{y0} {x0+r},{y0} L{x1},{y0} '
    if open_end:
        d += f'L{x1+22},{(y0+y1)/2} L{x1},{y1} '
    else:
        d += f'L{x1},{y1} '
    d += f'L{x0+r},{y1} Q{x0},{y1} {x0},{y1-r} Z'
    da = ' stroke-dasharray="5 4"' if dash else ""
    fig.raw(f'<g opacity="{op}"><path d="{d}" fill="{PANEL}"/><path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{da}/></g>', "over")
    cx = (x0 + x1) / 2
    anc = "middle"
    if end_text:
        cx, anc = x1 - 12, "end"
    ym = (y0 + y1) / 2
    if sub:
        fig.text(cx, ym - 2, label, size=14, anchor=anc, weight=600, layer="over")
        fig.text(cx, ym + 15, sub, size=13, anchor=anc, cls="t-muted", layer="over")
    else:
        fig.text(cx, ym + 5, label, size=14, anchor="middle", weight=600, layer="over")

# ---- lane 1: api_version -----------------------------------------------------------------------------------------------
fig.text(44, 218, "api_version", size=16, weight=700)
fig.text(44, 238, "researcher", size=13, cls="t-muted")
y0, y1 = 190, 236
bar(x(s_v1), x(s_v2), y0, y1, f"v1  {IDS['v1']}", f"step {s_v1} to {s_v2}", dash=True, op=0.85, end_text=True)
bar(x(s_v2), X1, y0, y1, f"v2  {IDS['v2']}", f"valid_from step {s_v2}, still active", open_end=True)
# v1 strike-through of the 'was' value is the dashed/closed bar; show the close boundary
fig.raw(f'<line x1="{x(s_v2):.1f}" y1="{y0-6}" x2="{x(s_v2):.1f}" y2="{y1+6}" stroke="#fde68a" stroke-width="1.6" stroke-dasharray="3 3"/>', "labels")
fig.text(x(s_v2), y1 + 26, f"valid_to(v1) = valid_from(v2) = step {s_v2}", size=13, anchor="middle", cls="t-muted")
# SUPERSEDES: dashed arrow above the lane, from v2 start back to v1
ax0, ax1 = x(s_v2) + 22, x(s_v2 - 4)
fig.raw(f'<path d="M{ax0:.1f},{y0-4} Q{(ax0+ax1)/2:.1f},{y0-52} {ax1:.1f},{y0-8}" class="e-supersedes" marker-end="url(#m-supersedes)"/>', "under")
fig.text((ax0 + ax1) / 2, y0 - 40, "SUPERSEDES", size=13, anchor="middle", weight=600, fill="#fde68a", layer="labels")

# as_of cursors
for step, ret, col in ((CUR1, "v1", "#60a5fa"), (CUR2, "v2", "#60a5fa")):
    cx = x(step)
    fig.raw(f'<line x1="{cx:.1f}" y1="{y0-44}" x2="{cx:.1f}" y2="{y1+12}" stroke="{col}" stroke-width="2" stroke-dasharray="6 4"/>', "labels")
    fig.raw(f'<circle cx="{cx:.1f}" cy="{(y0+y1)/2}" r="5.5" fill="{col}" stroke="{PANEL}" stroke-width="2"/>', "labels")
    lab = f"as_of(step {step}) returns {ret}"
    w = len(lab) * 7.9 + 20
    lx = cx - w + 14 if step == CUR1 else cx - 14
    fig.raw(f'<rect x="{lx:.1f}" y="{y0-76}" width="{w:.0f}" height="26" rx="6" fill="{PANEL}" stroke="{col}" stroke-width="1.4"/>', "labels")
    fig.text(lx + w / 2, y0 - 58, lab, size=13, anchor="middle", weight=600, layer="labels")
    fig.raw(f'<line x1="{cx:.1f}" y1="{y0-50}" x2="{cx:.1f}" y2="{y0-44}" stroke="{col}" stroke-width="2"/>', "labels")

# ---- lane 2: auth_method ------------------------------------------------------------------------------------------------
fig.text(44, 330, "auth_method", size=16, weight=700)
fig.text(44, 350, "two agents", size=13, cls="t-muted")
jy0, jy1 = 288, 324
ky0, ky1 = 358, 394
# overlap shading behind the bars
fig.raw(f'<rect x="{x(s_key):.1f}" y="{jy0-10}" width="{X1-x(s_key)+22:.1f}" height="{ky1-jy0+20}" rx="8" fill="rgba(248,113,111,0.10)" stroke="#f87171" stroke-width="1.2" stroke-dasharray="4 4"/>', "under")
bar(x(s_jwt), X1, jy0, jy1, f"jwt  {IDS['jwt']}", None, open_end=True)
bar(x(s_key), X1, ky0, ky1, f"api key  {IDS['key']}", None, open_end=True)
fig.text(x(s_jwt) - 10, (jy0 + jy1) / 2 + 5, f"{a_jwt}, step {s_jwt}", size=13, anchor="end", cls="t-muted")
fig.text(x(s_key) - 10, (ky0 + ky1) / 2 + 5, f"{a_key}, step {s_key}", size=13, anchor="end", cls="t-muted")
# CONTRADICTS marker between the two bars, at the step the second one was written
cx = x(s_key) + 40
fig.raw(f'<path d="M{cx:.1f},{jy1+3} L{cx:.1f},{ky0-3}" class="e-contradicts" marker-start="url(#m-contradicts)" marker-end="url(#m-contradicts)"/>', "labels")
fig.text(cx + 16, (jy1 + ky0) / 2 + 5, "CONTRADICTS, flagged when written", size=13, weight=600, fill="#f87171", layer="labels")
fig.text(x(s_key) - 14, (jy1 + ky0) / 2 + 5, "both stay active until someone decides", size=13, anchor="end", cls="t-muted")

# ---- axis -------------------------------------------------------------------------------------------------------------------
ay = 440
fig.raw(f'<line x1="{X0}" y1="{ay}" x2="{X1}" y2="{ay}" stroke="#475569" stroke-width="1.5"/>', "under")
for t in range(0, STEPS - 9, 10):
    fig.raw(f'<line x1="{x(t):.1f}" y1="{ay}" x2="{x(t):.1f}" y2="{ay+6}" stroke="#475569" stroke-width="1.5"/>', "under")
    fig.text(x(t), ay + 22, str(t), size=13, anchor="middle", cls="t-muted")
fig.text(x(STEPS), ay + 22, str(STEPS), size=13, anchor="middle", cls="t-muted")
fig.raw(f'<line x1="{x(STEPS):.1f}" y1="{ay}" x2="{x(STEPS):.1f}" y2="{ay+6}" stroke="#475569" stroke-width="1.5"/>', "under")
fig.text(44, ay + 5, "global step", size=13, cls="t-muted")
fig.text(44, ay + 22, "1 per call", size=13, cls="t-dim")
fig.legend_edges(430, 482, ["supersedes", "contradicts"], gap=22)

fig.write("02_validity_timeline", __doc__, title_y=60, sub_y=90)
render("02_validity_timeline", 1200, 500)
