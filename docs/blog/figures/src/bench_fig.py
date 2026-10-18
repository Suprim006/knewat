"""Figure 05: benchmark. Reads the real Crucible results, draws three panels, prints every plotted number.

Inputs (nothing typed from memory, except the arm display names the spec asks for):
  knewat/src/knewat/crucible/results/latest-all.json
      layers.L2.arms.<arm>.accuracy {correct,total,pct}                 (43 questions)
      layers.L2_scale.arms.<arm>.accuracy {correct,total,pct,wilson95_pct} (36 questions, one run each)
      layers.L2.summary.tokens_per_question
      layers.L2_scale.history.artifact_chars_over_budget               (context multiples)
      layers.L4.claim_sweep[arm, workers].claim.p50_ms                  (median claim latency; arms B1 = SQLite, P = Knewat)
  knewat/demo_data/crucible/b1h/latest.json  layers.L2.arm / layers.L2_scale.arm   (hand-written SQL arm; falls back to
      layers.B1h in latest-all.json, same numbers; BASELINE.md line ~553 quotes 43/43 and 36/36)
  colours: tokens.css (written by figlib.py)
Canvas: 12 x 6.75 in at 200 dpi = 2400 x 1350 px (= 1200 x 675 at 2x). No bbox_inches='tight', so the size is exact.
"""
import json
import re
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

SRC = Path(__file__).resolve().parent
OUT = SRC.parent
REPO = SRC.parents[3]
RES = REPO / "knewat/src/knewat/crucible/results/latest-all.json"
B1H = REPO / "knewat/demo_data/crucible/b1h/latest.json"

# ---- tokens ----------------------------------------------------------------------------------------------------------
css = (SRC / "tokens.css").read_text(encoding="utf-8")
tok = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", css))
CARD, PANEL, INK, MUTED, DIM, GRIDC = tok["card"], tok["panel"], tok["ink"], tok["muted"], tok["dim"], tok["grid"]
C_KNEWAT = tok["node-fact-stroke"]      # emerald
C_SQL = tok["node-toolcall-stroke"]     # amber: everything SQLite
C_LLM = tok["node-step-stroke"]         # slate: LLM readers over files / CSV / vectors

J = json.loads(RES.read_text(encoding="utf-8"))
L = J["layers"]
commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
run_id = J["run"]["id"]

# ---- data --------------------------------------------------------------------------------------------------------------
if B1H.exists():
    b1h = json.loads(B1H.read_text(encoding="utf-8"))["layers"]
    b1h_src = "knewat/demo_data/crucible/b1h/latest.json"
else:
    b1h = L["B1h"]["layers"]
    b1h_src = "latest-all.json layers.B1h"
arms = [  # key, label, colour, L2 accuracy dict, L2-scale accuracy dict
    ("B0", "files + Claude", C_LLM, L["L2"]["arms"]["B0"]["accuracy"], L["L2_scale"]["arms"]["B0"]["accuracy"]),
    ("B1", "SQLite CSV + Claude", C_LLM, L["L2"]["arms"]["B1"]["accuracy"], L["L2_scale"]["arms"]["B1"]["accuracy"]),
    ("B2", "vector + Claude", C_LLM, L["L2"]["arms"]["B2"]["accuracy"], L["L2_scale"]["arms"]["B2"]["accuracy"]),
    ("B1h", "hand-written SQL", C_SQL, b1h["L2"]["arm"]["accuracy"], b1h["L2_scale"]["arm"]["accuracy"]),
    ("P", "Knewat (Cypher)", C_KNEWAT, L["L2"]["arms"]["P"]["accuracy"], L["L2_scale"]["arms"]["P"]["accuracy"]),
]
sweep = {(r["arm"], r["workers"]): r["claim"]["p50_ms"] for r in L["L4"]["claim_sweep"]}
workers = sorted({w for (_, w) in sweep})
lat = {a: [sweep[(a, w)] for w in workers] for a in ("B1", "P")}
tokens = L["L2"]["summary"]["tokens_per_question"]
over = L["L2_scale"]["history"]["artifact_chars_over_budget"]
def differ(set_name, p_qs, h_qs):
    hp = {q["id"]: q["correct"] for q in h_qs}
    return sum(1 for q in p_qs if hp.get(q["id"]) != q["correct"])
d_l2 = differ("L2", L["L2"]["arms"]["P"]["questions"], b1h["L2"]["arm"]["questions"])
d_l2s = differ("L2_scale", L["L2_scale"]["arms"]["P"]["questions"], b1h["L2_scale"]["arm"]["questions"])

print("== plotted numbers ==")
for k, lab, _, a2, a36 in arms:
    w = a36.get("wilson95_pct")
    print(f"correctness {lab:22s} L2 {a2['correct']}/{a2['total']} ({a2['pct']}%)   L2-scale {a36['correct']}/{a36['total']} ({a36['pct']}%) wilson95={w}")
print("median claim latency p50 ms, workers", workers)
for a, nm in (("B1", "SQLite"), ("P", "Knewat")):
    print(f"  {nm:7s}", lat[a])
print("L2 tokens/question", {k: tokens[k] for k in ("B0", "B1", "B2", "P")}, " B1h tokens/question", b1h["L2"]["arm"]["usage"]["tokens_per_question"])
print("context over budget (L2-scale artifact chars / 32k budget)", over)
print("questions where Knewat and hand SQL differ: L2", d_l2, "L2-scale", d_l2s)
print("B1h source:", b1h_src, "| results file:", RES.name, "| run", run_id, "| commit", commit)

# ---- figure ------------------------------------------------------------------------------------------------------------
plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans"], "text.color": INK, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": INK, "axes.edgecolor": "#334155", "font.size": 10})
fig = plt.figure(figsize=(12, 6.75), dpi=200, facecolor=CARD)
fig.text(0.037, 0.945, "Hand-written SQL ties Knewat on correctness; both beat LLM readers at 10-17x context;",
         fontsize=17, fontweight="bold", color="#f8fafc", va="center")
fig.text(0.037, 0.893, "SQLite wins the median claim", fontsize=17, fontweight="bold", color="#f8fafc", va="center")
gs = fig.add_gridspec(1, 3, left=0.175, right=0.985, top=0.775, bottom=0.215, width_ratios=[1.5, 1.05, 0.9], wspace=0.34)

def style(ax):
    ax.set_facecolor(PANEL)
    for s in ax.spines.values():
        s.set_color("#334155")
    ax.tick_params(length=3, labelsize=10)

# (a) correctness
ax = fig.add_subplot(gs[0, 0]); style(ax)
ys = list(range(len(arms)))[::-1]
bh = 0.34
for y, (k, lab, col, a2, a36) in zip(ys, arms):
    ax.barh(y + bh / 2 + 0.02, a2["pct"], height=bh, color=col, alpha=0.42, edgecolor=col, linewidth=0.8)
    ax.barh(y - bh / 2 - 0.02, a36["pct"], height=bh, color=col, alpha=1.0)
    lo, hi = a36["wilson95_pct"]
    ax.errorbar(a36["pct"], y - bh / 2 - 0.02, xerr=[[a36["pct"] - lo], [hi - a36["pct"]]], fmt="none", ecolor="#f8fafc",
                elinewidth=1.4, capsize=3, capthick=1.4)
    ax.text(a2["pct"] + 1.5, y + bh / 2 + 0.02, f"{a2['correct']}/{a2['total']}", va="center", fontsize=10, color=MUTED)
    ax.text(max(hi, a36["pct"]) + 1.5, y - bh / 2 - 0.02, f"{a36['correct']}/{a36['total']}", va="center", fontsize=10,
            color=INK, fontweight="bold")
ax.set_yticks(ys); ax.set_yticklabels([a[1] for a in arms], fontsize=11)
ax.set_xlim(0, 118); ax.set_xticks([0, 25, 50, 75, 100]); ax.set_xlabel("questions answered correctly (%)", fontsize=10)
ax.set_ylim(-0.6, len(arms) - 0.4)
ax.xaxis.grid(True, color=GRIDC, linewidth=0.8); ax.set_axisbelow(True)
ax.set_title("(a) Correctness", loc="left", fontsize=12, fontweight="bold", color=INK, pad=22)
ax.legend(handles=[Patch(facecolor=MUTED, alpha=0.42, label=f"L2, {arms[0][3]['total']} questions"),
                   Patch(facecolor=MUTED, label=f"L2-scale, {arms[0][4]['total']} questions (bar: 95% Wilson)")],
          loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, frameon=False, fontsize=9, labelcolor=MUTED,
          handlelength=1.2, columnspacing=1.0, borderaxespad=0.2)

# (b) median claim latency
ax = fig.add_subplot(gs[0, 1]); style(ax)
ax.plot(workers, lat["B1"], color=C_SQL, marker="o", markersize=6, linewidth=2.4, label="SQLite (in process)")
ax.plot(workers, lat["P"], color=C_KNEWAT, marker="s", markersize=6, linewidth=2.4, label="Knewat (over the network)")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xticks(workers); ax.set_xticklabels([str(w) for w in workers]); ax.minorticks_off()
ax.set_xlabel("concurrent workers", fontsize=10); ax.set_ylabel("median claim latency (ms)", fontsize=10)
ax.yaxis.grid(True, color=GRIDC, linewidth=0.8); ax.set_axisbelow(True)
ax.annotate(f"{lat['B1'][-1]:.2f} ms", (workers[-1], lat["B1"][-1]), textcoords="offset points", xytext=(-4, 9), ha="right", fontsize=10, color=C_SQL, fontweight="bold")
ax.annotate(f"{lat['P'][-1]:.0f} ms", (workers[-1], lat["P"][-1]), textcoords="offset points", xytext=(-10, -3), ha="right", fontsize=10, color=C_KNEWAT, fontweight="bold")
ax.set_title("(b) Median claim latency", loc="left", fontsize=12, fontweight="bold", color=INK, pad=22)
ax.set_ylim(0.05, 2500)
ax.legend(loc="center right", bbox_to_anchor=(1.0, 0.47), frameon=False, fontsize=9, labelcolor=MUTED, borderaxespad=0.6, handlelength=1.6)

# (c) tokens per question (L2)
ax = fig.add_subplot(gs[0, 2]); style(ax)
rows = [("files", tokens["B0"], C_LLM), ("SQLite CSV", tokens["B1"], C_LLM), ("vector", tokens["B2"], C_LLM),
        ("hand SQL", b1h["L2"]["arm"]["usage"]["tokens_per_question"], C_SQL), ("Knewat", tokens["P"], C_KNEWAT)]
yy = list(range(len(rows)))[::-1]
for y, (nm, v, col) in zip(yy, rows):
    ax.barh(y, v, height=0.55, color=col)
    ax.text(v + 250, y, f"{v:,.0f}" if v else "0 (no LLM)", va="center", fontsize=10, color=INK, fontweight="bold" if not v else "normal")
ax.set_yticks(yy); ax.set_yticklabels([r[0] for r in rows], fontsize=10)
ax.set_xlim(0, 24500); ax.set_xticks([0, 5000, 10000, 15000, 20000]); ax.set_xticklabels(["0", "5k", "10k", "15k", "20k"])
ax.set_xlabel("tokens per question (L2)", fontsize=10); ax.xaxis.grid(True, color=GRIDC, linewidth=0.8); ax.set_axisbelow(True)
ax.set_title("(c) Tokens per answer", loc="left", fontsize=12, fontweight="bold", color=INK, pad=22)

# footnotes + footer
fig.text(0.037, 0.115,
         f"Synthetic Acme scenario, one model, one run per question. L2-scale history is {over['B1']:.1f}x (SQLite CSV) to {over['B0']:.1f}x (files) the 32k-character context budget, "
         f"vector {over['B2']:.1f}x.",
         fontsize=9.5, color=MUTED, va="center")
fig.text(0.037, 0.083, "Knewat and hand-written SQL are deterministic query code (no LLM); both were written by the author who knew the questions. "
         f"Hand SQL and Knewat differ on {d_l2} of {arms[0][3]['total']} and {d_l2s} of {arms[0][4]['total']} questions.", fontsize=9.5, color=MUTED, va="center")
fig.text(0.037, 0.035, f"source: {RES.relative_to(REPO).as_posix()} (run {run_id}); hand-written SQL: {b1h_src} · commit {commit} · bench_fig.py",
         fontsize=9, color=DIM, va="center")
fig.text(0.985, 0.035, "Knewat \u00b7 FalkorDB 6.0.2", fontsize=10, color=DIM, ha="right", va="center")

out = OUT / "05_benchmark.png"
fig.savefig(out, dpi=200, facecolor=CARD)
from PIL import Image  # noqa: E402
print("saved", out, Image.open(out).size, round(out.stat().st_size / 1024, 1), "KB")
