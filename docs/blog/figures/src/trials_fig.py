"""Figure 06: the everyday-workflow trials (6, 7, 8), one dot per run, 4 runs per arm.

Numbers are typed here ONLY from these two files (nothing else is used):
  trials/RESULTS_T678.md   trial 6 table, column "per run" (violations of 6 per run: baseline 6,6,6,6; claudemd 6,6,6,6; plexus 0,0,0,0)
                           trial 7 table, column "per run" (violations of 3 per run: baseline 3,3,0,3; claudemd 1,1,3,3; plexus 0,0,0,0)
                           trial 8 "Session-3 per-rule outcome" table (C1 kept / C3 removed / P1 kept, x/4 per arm)
  trials/FINDINGS.md s5    summary table: trial 6 violations of 24 = 24/24/0; trial 7 of 12 = 9/8/0;
                           trial 8 rules kept of 8 / memo-only C3 removed of 4 = 8/0, 8/4, 8/4
The script re-checks that the per-run values sum to the FINDINGS totals before drawing.
Canvas: 12 x 6.3 in at 200 dpi = 2400 x 1260 px (= 1200 x 630 at 2x). No bbox_inches='tight', so the size is exact.
Colours come from tokens.css (written by figlib.py), same as 05: slate = plain Claude Code, amber = CLAUDE.md, emerald = Plexus.
"""
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SRC = Path(__file__).resolve().parent
OUT = SRC.parent

css = (SRC / "tokens.css").read_text(encoding="utf-8")
tok = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", css))
CARD, PANEL, INK, MUTED, DIM, GRIDC = tok["card"], tok["panel"], tok["ink"], tok["muted"], tok["dim"], tok["grid"]
ARMS = [("baseline", "plain Claude Code", tok["node-step-stroke"]),
        ("claudemd", "committed CLAUDE.md", tok["node-toolcall-stroke"]),
        ("plexus", "Plexus", tok["node-fact-stroke"])]

# ---- data, copied from the two source files (see docstring) ------------------------------------------------------------
T6 = {"baseline": [6, 6, 6, 6], "claudemd": [6, 6, 6, 6], "plexus": [0, 0, 0, 0]}   # of 6 per run
T7 = {"baseline": [3, 3, 0, 3], "claudemd": [1, 1, 3, 3], "plexus": [0, 0, 0, 0]}   # of 3 per run
T6_TOT, T7_TOT = {"baseline": 24, "claudemd": 24, "plexus": 0}, {"baseline": 9, "claudemd": 8, "plexus": 0}  # FINDINGS s5
T8_KEPT = {"baseline": 8, "claudemd": 8, "plexus": 8}      # C1 + P1 kept, of 8 (4 runs x 2 rules)
T8_C3 = {"baseline": 0, "claudemd": 4, "plexus": 4}        # memo-only C3 removed, of 4 runs
for a in T6:
    assert sum(T6[a]) == T6_TOT[a] and sum(T7[a]) == T7_TOT[a], a
    assert all(len(v) == 4 for v in (T6[a], T7[a]))

print("== plotted numbers (trials/RESULTS_T678.md, trials/FINDINGS.md s5) ==")
print("trial 6, violations per run of 6 (totals of 24):")
for a, lab, _ in ARMS:
    print(f"  {a:9s} {T6[a]} total {sum(T6[a])}/24")
print("trial 7, violations per run of 3 (totals of 12):")
for a, lab, _ in ARMS:
    print(f"  {a:9s} {T7[a]} total {sum(T7[a])}/12")
print("trial 8: rules correctly kept (C1+P1) of 8 / memo-only C3 removed of 4:")
for a, lab, _ in ARMS:
    print(f"  {a:9s} {T8_KEPT[a]}/8  C3 {T8_C3[a]}/4")

# ---- figure ----------------------------------------------------------------------------------------------------------------
plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans"], "text.color": INK, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": "#334155", "font.size": 10})
fig = plt.figure(figsize=(12, 6.3), dpi=200, facecolor=CARD)
fig.text(0.037, 0.935, "Decided in one repo, followed in the next: Plexus carries team decisions where no file reaches the agent",
         fontsize=15.5, fontweight="bold", color="#f8fafc", va="center")
fig.text(0.037, 0.875, "Real Claude Code agents, separate sessions, scored by running their code. 4 runs per arm, "
         "small synthetic repos, designed after trials 1-5.", fontsize=11.5, color=MUTED, va="center")
gs = fig.add_gridspec(1, 3, left=0.055, right=0.985, top=0.735, bottom=0.255, width_ratios=[1, 1, 1], wspace=0.14)


def style(ax):
    ax.set_facecolor(PANEL)
    for s in ax.spines.values():
        s.set_color("#334155")
    ax.tick_params(length=3, labelsize=10)
    ax.set_axisbelow(True)


def strip(ax, data, tot, of_run, of_tot, title, sub):
    style(ax)
    offs = [-0.27, -0.09, 0.09, 0.27]                  # run 1..4 keep a fixed slot, so equal values never hide each other
    for i, (a, lab, col) in enumerate(ARMS):
        xs = [i + o for o in offs]
        ax.plot([i - 0.36, i + 0.36], [sum(data[a]) / 4] * 2, color=col, lw=1.3, alpha=0.55, ls=(0, (4, 3)), zorder=1)
        ax.scatter(xs, data[a], s=150, color=col, edgecolor=CARD, linewidth=1.2, zorder=3)
        ax.text(i, -0.19, f"{tot[a]} of {of_tot}", ha="center", va="top", fontsize=11, fontweight="bold", color=col,
                clip_on=False, transform=ax.get_xaxis_transform())
    ax.set_xlim(-0.6, 2.6)
    ax.set_ylim(-0.5, of_run + 0.5)
    ax.set_yticks(range(0, of_run + 1))
    ax.set_xticks(range(3))
    ax.set_xticklabels(["plain\nClaude Code", "committed\nCLAUDE.md", "Plexus"], fontsize=10, color=INK)
    ax.tick_params(axis="x", pad=3)
    ax.yaxis.grid(True, color=GRIDC, linewidth=0.8)
    ax.set_ylabel(f"violations per run (of {of_run})", fontsize=10)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=24)
    ax.text(0, 1.035, sub, transform=ax.transAxes, fontsize=9, color=MUTED, va="bottom")


ax6 = fig.add_subplot(gs[0, 0])
strip(ax6, T6, T6_TOT, 6, 24, "(a) Trial 6: two repos", "decision made in repo A, work done in repo B")
ax7 = fig.add_subplot(gs[0, 1])
strip(ax7, T7, T7_TOT, 3, 12, "(b) Trial 7: parallel worktrees", "unmerged branch + a non-LLM ci-bot's note")

# (c) trial 8: outcome counts, one dot per run for C3, text for the rest
ax = fig.add_subplot(gs[0, 2]); style(ax)
ax.set_xlim(0, 10); ax.set_ylim(0, 10)
ax.set_xticks([]); ax.set_yticks([])
ax.set_title("(c) Trial 8: retract a void source", loc="left", fontsize=12, fontweight="bold", color=INK, pad=24)
ax.text(0, 1.035, "session 3: memo is void; what happens to its rules?", transform=ax.transAxes, fontsize=9, color=MUTED, va="bottom")
ax.text(0.45, 9.2, "rules kept (C1, P1)", fontsize=9.5, color=MUTED, va="center", fontweight="bold")
ax.text(9.55, 9.2, "memo-only C3 removed", fontsize=9.5, color=MUTED, va="center", ha="right", fontweight="bold")
ax.text(0.45, 8.55, "of 8", fontsize=9, color=DIM, va="center")
ax.text(9.55, 8.55, "of 4 runs, one dot per run", fontsize=9, color=DIM, va="center", ha="right")
ys = [7.0, 4.9, 2.8]
for y, (a, lab, col) in zip(ys, ARMS):
    ax.text(0.45, y + 0.05, f"{T8_KEPT[a]} / 8", fontsize=16, fontweight="bold", color=col, va="center")
    for k in range(4):
        filled = k < T8_C3[a]
        ax.scatter([6.15 + k * 0.95], [y + 0.05], s=150, facecolor=col if filled else "none", edgecolor=col, linewidth=1.8, zorder=3)
    ax.text(9.55, y - 0.85, f"{T8_C3[a]} / 4", fontsize=11, fontweight="bold", color=col, va="center", ha="right")
ax.text(0.45, 0.8, "baseline made no change in session 3 (an honest no-op,\nnot a wrong retraction)", fontsize=8.5, color=MUTED,
        va="center", linespacing=1.35)
for y in (5.95, 3.85):
    ax.plot([0.3, 9.7], [y, y], color=GRIDC, lw=0.8)

# arm legend
from matplotlib.lines import Line2D  # noqa: E402
fig.legend(handles=[Line2D([0], [0], marker="o", color="none", markerfacecolor=c, markeredgecolor=CARD, markersize=9, label=lab)
                    for _, lab, c in ARMS], loc="lower left", bbox_to_anchor=(0.045, 0.072), ncol=3, frameon=False, fontsize=10,
           labelcolor=INK, handletextpad=0.3, columnspacing=1.6)
fig.text(0.985, 0.088, "dashed line = mean of the 4 runs (a, b); dots left to right = run 1-4", fontsize=9, color=MUTED, ha="right", va="center")
fig.text(0.037, 0.03, "trials 6-7: build trials-int 76da7d7; trial 8 re-run: main 7618d18 · trials/RESULTS_T678.md, trials/FINDINGS.md s5 · trials_fig.py",
         fontsize=9, color=DIM, va="center")
fig.text(0.985, 0.035, "Plexus \u00b7 FalkorDB 6.0.2", fontsize=10, color=DIM, ha="right", va="center")

out = OUT / "06_trials.png"
fig.savefig(out, dpi=200, facecolor=CARD)
from PIL import Image  # noqa: E402
print("saved", out, Image.open(out).size, round(out.stat().st_size / 1024, 1), "KB")
