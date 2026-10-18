"""Shared helpers for the Plexus blog figures 01-04 (HTML + inline SVG, rendered by headless Chrome).

Design: dark slate card, monospace labels, 40 px grid, one semantic colour per node label, one visual
channel per edge type (see tokens.css, which this module writes so the two can never drift).
Edges are drawn before nodes; nodes use the double-rect masking trick from the architecture-diagram skill.
No external fonts, no emoji, no <foreignObject>.
"""
from __future__ import annotations

import html
import math
import subprocess
from pathlib import Path

SRC = Path(__file__).resolve().parent
OUT = SRC.parent
CHROME = r"C:/Program Files/Google/Chrome/Application/chrome.exe"

# ---- tokens ---------------------------------------------------------------------------------------------------
CARD = "#0b1020"
GRID = "#1a2338"
PANEL = "#0f172a"
INK = "#e2e8f0"
MUTED = "#94a3b8"
DIM = "#64748b"

# node label -> (fill rgba, stroke hex)   [architecture-diagram rule: translucent fill + 1.5 px bright stroke]
NODES = {
    "agent": ("rgba(8,51,68,0.55)", "#22d3ee", "Agent"),
    "fact": ("rgba(6,78,59,0.55)", "#34d399", "Fact"),
    "decision": ("rgba(131,24,67,0.50)", "#f472b6", "Decision"),
    "source": ("rgba(76,29,149,0.50)", "#a78bfa", "Source"),
    "task": ("rgba(124,45,18,0.50)", "#fb923c", "Task"),
    "step": ("rgba(30,41,59,0.70)", "#94a3b8", "Step"),
    "toolcall": ("rgba(120,53,15,0.45)", "#fbbf24", "ToolCall"),
}
# edge type -> (stroke, width, dasharray, linecap, label)
EDGES = {
    "based": ("#60a5fa", 2.6, "", "round", "BASED_ON"),
    "derived": ("#bfdbfe", 1.8, "", "round", "DERIVED_FROM"),
    "read": ("#e2e8f0", 2.0, "0.1 6", "round", "READ"),
    "depends": ("#64748b", 1.3, "", "round", "DEPENDS_ON"),
    "supersedes": ("#fde68a", 2.2, "8 5", "butt", "SUPERSEDES"),
    "contradicts": ("#f87171", 2.8, "", "round", "CONTRADICTS"),
    "asserted": ("#22d3ee", 1.4, "", "round", "ASSERTED_BY"),
}
FONT_MONO = "'JetBrains Mono','Cascadia Mono','Consolas','Courier New',monospace"
FONT_UI = "'Segoe UI','Inter','Helvetica Neue',Arial,sans-serif"


def write_tokens() -> None:
    lines = ["/* Plexus blog figures: shared design tokens. Written by figlib.write_tokens(); edit there. */", ":root {"]
    lines += [f"  --card: {CARD};", f"  --grid: {GRID};", f"  --panel: {PANEL};", f"  --ink: {INK};",
              f"  --muted: {MUTED};", f"  --dim: {DIM};",
              f"  --font-mono: {FONT_MONO};", f"  --font-ui: {FONT_UI};"]
    for k, (fill, stroke, label) in NODES.items():
        lines += [f"  --node-{k}-fill: {fill};  /* {label} */", f"  --node-{k}-stroke: {stroke};"]
    for k, (stroke, w, dash, cap, label) in EDGES.items():
        lines += [f"  --edge-{k}: {stroke};  /* {label} */"]
    lines.append("}")
    lines += ["html,body{margin:0;padding:0;background:var(--card);overflow:hidden}",
              "svg{display:block}",
              "text{font-family:var(--font-mono);fill:var(--ink)}",
              ".t-title{font-family:var(--font-ui);font-weight:700;fill:#f8fafc}",
              ".t-sub{font-family:var(--font-ui);fill:var(--muted)}",
              ".t-node{font-weight:600}",
              ".t-muted{fill:var(--muted)}",
              ".t-dim{fill:var(--dim)}"]
    for k in NODES:
        lines.append(f".n-{k}{{fill:var(--node-{k}-fill);stroke:var(--node-{k}-stroke);stroke-width:1.6}}")
    for k, (stroke, w, dash, cap, label) in EDGES.items():
        d = f"stroke-dasharray:{dash};" if dash else ""
        lines.append(f".e-{k}{{fill:none;stroke:var(--edge-{k});stroke-width:{w};{d}stroke-linecap:{cap}}}")
    (SRC / "tokens.css").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---- geometry -------------------------------------------------------------------------------------------------
class Box:
    def __init__(self, cx: float, cy: float, w: float, h: float):
        self.cx, self.cy, self.w, self.h = cx, cy, w, h

    @property
    def x(self): return self.cx - self.w / 2
    @property
    def y(self): return self.cy - self.h / 2

    def clip(self, tx: float, ty: float, pad: float = 3.0):
        """Point on the box outline in the direction of (tx, ty), pushed out by pad."""
        dx, dy = tx - self.cx, ty - self.cy
        if dx == 0 and dy == 0:
            return self.cx, self.cy
        hw, hh = self.w / 2 + pad, self.h / 2 + pad
        s = min(hw / abs(dx) if dx else 1e9, hh / abs(dy) if dy else 1e9)
        return self.cx + dx * s, self.cy + dy * s


def f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


class Fig:
    def __init__(self, W: int, H: int, title: str, subtitle: str, footer: str = "Plexus \u00b7 FalkorDB 6.0.2"):
        self.W, self.H = W, H
        self.title, self.subtitle, self.footer = title, subtitle, footer
        self.defs: list[str] = []
        self.under: list[str] = []   # edges
        self.over: list[str] = []    # nodes
        self.labels: list[str] = []  # edge labels, drawn last
        self.top: list[str] = []
        self.boxes: dict[str, Box] = {}
        self.footer_y = H - 22
        self._markers()

    # -- markers: one per arrow colour ----------------------------------------------------------------------------
    def _markers(self):
        for k, (stroke, w, dash, cap, label) in EDGES.items():
            if k == "contradicts":
                self.defs.append(
                    f'<marker id="m-{k}" viewBox="0 0 10 20" refX="5" refY="10" markerWidth="10" markerHeight="20" '
                    f'markerUnits="userSpaceOnUse" orient="auto"><line x1="5" y1="1" x2="5" y2="19" stroke="{stroke}" '
                    f'stroke-width="3" stroke-linecap="round"/></marker>')
            else:
                self.defs.append(
                    f'<marker id="m-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" '
                    f'markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{stroke}"/></marker>')
        self.defs.append(
            '<marker id="m-ghost" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" '
            'markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#475569"/></marker>')

    # -- nodes ----------------------------------------------------------------------------------------------------
    def node(self, nid, cx, cy, w, h, kind, label, sub=None, opacity=1.0, ghost=False, strike=False,
             outline=None, size=14, weight=600):
        b = Box(cx, cy, w, h)
        self.boxes[nid] = b
        stroke_extra = ' stroke-dasharray="5 4"' if ghost else ""
        g = [f'<g opacity="{opacity}">']
        g.append(f'<rect x="{f(b.x)}" y="{f(b.y)}" width="{w}" height="{h}" rx="7" fill="{PANEL}"/>')
        g.append(f'<rect class="n-{kind}" x="{f(b.x)}" y="{f(b.y)}" width="{w}" height="{h}" rx="7"{stroke_extra}/>')
        if outline:
            g.append(f'<rect x="{f(b.x-5)}" y="{f(b.y-5)}" width="{w+10}" height="{h+10}" rx="11" fill="none" '
                     f'stroke="{outline}" stroke-width="2.4" stroke-dasharray="3 3"/>')
        if sub:
            g.append(f'<text x="{f(cx)}" y="{f(cy-3)}" text-anchor="middle" font-size="{size}" font-weight="{weight}">{html.escape(label)}</text>')
            g.append(f'<text x="{f(cx)}" y="{f(cy+14)}" text-anchor="middle" font-size="13" class="t-muted">{html.escape(sub)}</text>')
        else:
            g.append(f'<text x="{f(cx)}" y="{f(cy+size*0.36)}" text-anchor="middle" font-size="{size}" font-weight="{weight}">{html.escape(label)}</text>')
        if strike:
            tw = min(w - 14, len(label) * size * 0.6)
            yy = cy + (-6 if sub else size * 0.36 - size * 0.3)
            g.append(f'<line x1="{f(cx-tw/2-4)}" y1="{f(yy)}" x2="{f(cx+tw/2+4)}" y2="{f(yy)}" stroke="#f87171" stroke-width="1.8" stroke-opacity="0.9"/>')
        g.append("</g>")
        self.over.append("".join(g))
        return b

    # -- edges ----------------------------------------------------------------------------------------------------
    def edge(self, a, b, kind, label=None, curve=0.0, opacity=1.0, ghost=False, lx=None, ly=None, arrow=True,
             start=None, end=None, label_size=12, label_dy=0):
        A, B = self.boxes[a], self.boxes[b]
        sx, sy = start if start else (A.cx, A.cy)
        ex, ey = end if end else (B.cx, B.cy)
        mx, my = (sx + ex) / 2, (sy + ey) / 2
        dx, dy = ex - sx, ey - sy
        ln = math.hypot(dx, dy) or 1
        cx, cy = mx - dy / ln * curve, my + dx / ln * curve
        tgt_a = (cx, cy) if curve else (ex, ey)
        tgt_b = (cx, cy) if curve else (sx, sy)
        p0 = start if start else A.clip(*tgt_a)
        p1 = end if end else B.clip(*tgt_b, pad=4.0 if arrow else 3.0)
        cls = f"e-{kind}"
        style = ""
        marker = f' marker-end="url(#m-{kind})"' if arrow else ""
        if kind == "contradicts":
            marker = f' marker-start="url(#m-{kind})" marker-end="url(#m-{kind})"'
        if ghost:
            style = ' style="stroke:#475569;stroke-width:1.6;stroke-dasharray:4 5"'
            marker = ' marker-end="url(#m-ghost)"' if arrow else ""
        if curve:
            d = f"M{f(p0[0])},{f(p0[1])} Q{f(cx)},{f(cy)} {f(p1[0])},{f(p1[1])}"
        else:
            d = f"M{f(p0[0])},{f(p0[1])} L{f(p1[0])},{f(p1[1])}"
        self.under.append(f'<path d="{d}" class="{cls}"{style}{marker} opacity="{opacity}"/>')
        if label and not ghost:
            qx = lx if lx is not None else (0.25 * p0[0] + 0.5 * cx + 0.25 * p1[0] if curve else (p0[0] + p1[0]) / 2)
            qy = ly if ly is not None else (0.25 * p0[1] + 0.5 * cy + 0.25 * p1[1] if curve else (p0[1] + p1[1]) / 2)
            col = EDGES[kind][0]
            self.labels.append(
                f'<text x="{f(qx)}" y="{f(qy+label_dy)}" text-anchor="middle" font-size="{label_size}" font-weight="600" '
                f'style="fill:{col};paint-order:stroke;stroke:{CARD};stroke-width:5px;stroke-linejoin:round" '
                f'opacity="{opacity}">{html.escape(label)}</text>')
        return p0, p1

    def cross(self, x, y, r=7, color="#f87171"):
        self.labels.append(
            f'<g stroke="{color}" stroke-width="2.6" stroke-linecap="round">'
            f'<line x1="{f(x-r)}" y1="{f(y-r)}" x2="{f(x+r)}" y2="{f(y+r)}"/>'
            f'<line x1="{f(x-r)}" y1="{f(y+r)}" x2="{f(x+r)}" y2="{f(y-r)}"/></g>')

    def raw(self, svg: str, layer="top"):
        getattr(self, {"top": "top", "under": "under", "over": "over", "labels": "labels"}[layer]).append(svg)

    def text(self, x, y, s, size=14, cls="", anchor="start", weight=400, fill=None, layer="top", opacity=1):
        st = f' style="fill:{fill}"' if fill else ""
        self.raw(f'<text x="{f(x)}" y="{f(y)}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
                 f'class="{cls}"{st} opacity="{opacity}">{html.escape(s)}</text>', layer)

    # -- legend (outside the diagram boxes) -------------------------------------------------------------------------
    def legend_edges(self, x, y, kinds, gap=None, names=None):
        cx = x
        for k in kinds:
            stroke, w, dash, cap, label = EDGES[k]
            label = (names or {}).get(k, label)
            marker = f' marker-end="url(#m-{k})"' if k != "contradicts" else f' marker-start="url(#m-{k})" marker-end="url(#m-{k})"'
            if k == "contradicts":
                self.top.append(f'<path d="M{f(cx+4)},{f(y)} L{f(cx+40)},{f(y)}" class="e-{k}"{marker}/>')
            else:
                self.top.append(f'<path d="M{f(cx)},{f(y)} L{f(cx+36)},{f(y)}" class="e-{k}"{marker}/>')
            self.top.append(f'<text x="{f(cx+48)}" y="{f(y+4.5)}" font-size="13" class="t-muted">{label}</text>')
            cx += 48 + len(label) * 7.9 + (gap or 26)
        return cx

    def legend_nodes(self, x, y, kinds):
        cx = x
        for k in kinds:
            fill, stroke, label = NODES[k]
            self.top.append(f'<rect x="{f(cx)}" y="{f(y-8)}" width="18" height="16" rx="4" fill="{PANEL}"/>')
            self.top.append(f'<rect class="n-{k}" x="{f(cx)}" y="{f(y-8)}" width="18" height="16" rx="4"/>')
            self.top.append(f'<text x="{f(cx+26)}" y="{f(y+4.5)}" font-size="13" class="t-muted">{label}</text>')
            cx += 26 + len(label) * 7.9 + 24
        return cx

    # -- output ---------------------------------------------------------------------------------------------------
    def svg(self, title_y=62, sub_y=94, title_size=32, sub_size=17) -> str:
        W, H = self.W, self.H
        head = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
            "<defs>",
            f'<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0 L0 0 0 40" fill="none" stroke="{GRID}" stroke-width="0.6"/></pattern>',
            *self.defs,
            "</defs>",
            f'<rect width="{W}" height="{H}" fill="{CARD}"/>',
            f'<rect width="{W}" height="{H}" fill="url(#grid)"/>',
            f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14" fill="none" stroke="#1e293b" stroke-width="2"/>',
            f'<text x="44" y="{title_y}" font-size="{title_size}" class="t-title">{html.escape(self.title)}</text>',
            f'<text x="44" y="{sub_y}" font-size="{sub_size}" class="t-sub">{html.escape(self.subtitle)}</text>',
        ]
        foot = f'<text x="{W-44}" y="{self.footer_y}" font-size="13" text-anchor="end" class="t-dim">{html.escape(self.footer)}</text>'
        return "\n".join(head + self.under + self.over + self.labels + self.top + [foot, "</svg>"])

    def write(self, name: str, layout_comment: str = "", **kw) -> Path:
        write_tokens()
        doc = (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"><title>{html.escape(self.title)}</title>\n'
               f'<link rel="stylesheet" href="tokens.css">\n</head><body>\n<!--\n{layout_comment}\n-->\n'
               f'{self.svg(**kw)}\n</body></html>\n')
        p = SRC / f"{name}.html"
        p.write_text(doc, encoding="utf-8")
        return p


def render(name: str, W: int, H: int) -> Path:
    """Headless Chrome screenshot at 2x -> docs/blog/figures/<name>.png (exact command from the spec)."""
    out = OUT / f"{name}.png"
    url = "file:///" + (SRC / f"{name}.html").as_posix()
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
           f"--window-size={W},{H}", f"--screenshot={out.as_posix()}", url]
    subprocess.run(cmd, check=False, capture_output=True, timeout=120)
    try:
        from PIL import Image
        print(name, Image.open(out).size, round(out.stat().st_size / 1024, 1), "KB")
    except Exception as e:  # noqa: BLE001
        print("render check failed:", e)
    return out
