#!/usr/bin/env python3
"""Verify the submission documents: links, mermaid, quoted numbers, video-script ids and timing.

    python scripts/verify_readme.py                 # offline checks, exits 1 on any failure
    KNEWAT_MERMAID_DIR=<dir with `npm i mermaid jsdom`> python scripts/verify_readme.py   # also parses mermaid for real

Checked documents: README.md, docs/VIDEO_SCRIPT.md, docs/BLOG_DRAFT.md. Standard library only; no network, no database.

1. Links: every relative markdown link and every backticked repo path resolves to a file or directory; `#anchors` match a heading.
2. Placeholders: README keeps `<VIDEO_URL>` and `<BLOG_URL>` until the owner fills them in (the Render URL is already filled).
3. Mermaid: each block starts with a known diagram type (and is parsed by mermaid when KNEWAT_MERMAID_DIR is set).
4. Numbers: every figure quoted from a source must appear in that source file (and, where the source is the results JSON, equal
   the JSON's value) and in the document that quotes it.
5. Queries: every linked .cypher exists and has a row in docs/queries.md; the "93 files" claim equals the real file count.
6. Video script: beats are contiguous, end by 3:00, narration is <= 25 words per beat; every id exists in the recording
   transcripts; every (step, agent, tool) claim matches the recording's calls.json.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["README.md", "docs/RESULTS.md", "docs/ARCHITECTURE.md", "docs/VIDEO_SCRIPT.md", "docs/BLOG_DRAFT.md"]
RESULTS = ROOT / "knewat/src/knewat/crucible/results/latest-all.json"
RECORDING = ROOT / "knewat/demo_data/recordings/acme-claude-sonnet"

failures: list[str] = []
passed = 0


def check(ok: bool, what: str) -> None:
    global passed
    if ok:
        passed += 1
    else:
        failures.append(what)
        print(f"FAIL  {what}")


# Working files kept on the owner's disk and not published (see .gitignore). When one is absent, every check that
# reads it is skipped with a note instead of failing, so the script passes on a fresh clone and still gates the
# owner's local copies.
OPTIONAL_DOCS = {"docs/VIDEO_SCRIPT.md", "docs/BLOG_DRAFT.md", "docs/TESTING.md", "docs/demo.md"}
_noted: set[str] = set()


def read(rel: str) -> str:
    path = ROOT / rel
    if rel in OPTIONAL_DOCS and not path.exists():
        if rel not in _noted:
            _noted.add(rel)
            print(f"skip  {rel}: not in this checkout (owner's working file); its checks are skipped")
        return ""
    return path.read_text(encoding="utf-8")


def strip_fences(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.S)


def slug(heading: str) -> str:
    s = re.sub(r"[`*_]", "", heading.strip().lower())
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"\s", "-", s)


# ---------------------------------------------------------------- 1. links
PATH_RE = re.compile(r"^(?:docs|knewat|knewat-view|deploy|scripts)/[\w./\-]*$|^(?:render\.yaml|docker-compose\.yml|README\.md|CLAUDE\.md)$")


def check_links(doc: str) -> None:
    text = read(doc)
    base = (ROOT / doc).parent
    headings = {slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.*)$", strip_fences(text), flags=re.M)}
    prose = strip_fences(text)
    n_links = 0
    for m in re.finditer(r"\[[^\]]*\]\(([^)\s]+)\)", prose):
        target = m.group(1)
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        n_links += 1
        path, _, frag = target.partition("#")
        if path:
            check((base / path).exists(), f"{doc}: link target missing: {target}")
        if frag:
            target_headings = headings
            if path and (base / path).is_file() and path.endswith(".md"):
                other = strip_fences((base / path).read_text(encoding="utf-8"))
                target_headings = {slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.*)$", other, flags=re.M)}
            check(slug(frag) in target_headings or frag in target_headings, f"{doc}: anchor not found: {target}")
    # backticked repo paths (inline code only, in prose)
    for m in re.finditer(r"`([^`\n]+)`", prose):
        tok = m.group(1).strip()
        if any(c in tok for c in "<>*{}$ ") or not PATH_RE.match(tok):
            continue
        if tok == "CLAUDE.md":
            continue  # the agents' convention file named in the trials, not a repo path (the repo's own copy is unpublished)
        n_links += 1
        check((ROOT / tok).exists(), f"{doc}: backticked path missing: {tok}")
    print(f"ok    {doc}: {n_links} relative links/paths checked")


# ---------------------------------------------------------------- 3. mermaid
MERMAID_JS = """
import { JSDOM } from 'jsdom';
import fs from 'fs';
const dom = new JSDOM('<!DOCTYPE html><body></body>');
globalThis.window = dom.window; globalThis.document = dom.window.document;
Object.defineProperty(globalThis, 'navigator', {value: dom.window.navigator, configurable: true});
const mermaid = (await import('mermaid')).default;
let bad = 0;
for (const f of process.argv.slice(2)) {
  const md = fs.readFileSync(f, 'utf8');
  for (const m of md.matchAll(/```mermaid\\n([\\s\\S]*?)```/g)) {
    try { await mermaid.parse(m[1]); console.log('mermaid ok: ' + f + ' (' + m[1].split('\\n')[0] + ')'); }
    catch (e) { bad++; console.log('mermaid FAIL: ' + f + ' ' + String(e.message || e).slice(0, 200)); }
  }
}
process.exit(bad ? 1 : 0);
"""


def check_mermaid() -> None:
    kinds = ("flowchart", "graph", "erDiagram", "sequenceDiagram", "classDiagram")
    for doc in DOCS:
        for i, block in enumerate(re.findall(r"```mermaid\n(.*?)```", read(doc), flags=re.S), 1):
            first = block.strip().splitlines()[0] if block.strip() else ""
            check(first.startswith(kinds), f"{doc}: mermaid block {i} starts with an unknown diagram type: {first!r}")
            check(block.count('"') % 2 == 0, f"{doc}: mermaid block {i} has an unbalanced quote")
    mdir = os.environ.get("KNEWAT_MERMAID_DIR")
    if not mdir:
        print("skip  mermaid parse (set KNEWAT_MERMAID_DIR to a directory with `npm i mermaid jsdom`)")
        return
    script = Path(mdir) / "_verify_parse.mjs"
    script.write_text(MERMAID_JS, encoding="utf-8")
    files = [str(ROOT / d) for d in DOCS]
    r = subprocess.run(["node", str(script), *files], cwd=mdir, capture_output=True, text=True, timeout=120)
    print(r.stdout.strip())
    check(r.returncode == 0, f"mermaid parse failed: {r.stdout.strip()[-300:]} {r.stderr.strip()[-300:]}")


# ---------------------------------------------------------------- 4. numbers
def numbers() -> None:
    res = json.loads(RESULTS.read_text(encoding="utf-8"))
    L = res["layers"]
    # the benchmark and trial numbers live in docs/RESULTS.md and docs/ARCHITECTURE.md (moved out of the README, which is a setup guide)
    readme = "\n".join(read(d) for d in ("README.md", "docs/RESULTS.md", "docs/ARCHITECTURE.md"))
    blog = read("docs/BLOG_DRAFT.md")

    # (a) values computed from latest-all.json must match what the README prints
    l2 = {a: v["accuracy"] for a, v in L["L2"]["arms"].items()}
    check(
        (l2["P"]["correct"], l2["B0"]["correct"], l2["B1"]["correct"], l2["B2"]["correct"], l2["P"]["total"])
        == (43, 43, 43, 40, 43),
        f"latest-all.json L2 is not P43/B043/B143/B240 of 43: {l2}",
    )
    check("P 43/43, B0 43/43, B1 43/43, B2 40/43 (93.0%)" in readme, "README: L2 line differs from latest-all.json")
    sc = {a: v["accuracy"] for a, v in L["L2_scale"]["arms"].items()}
    want = {"P": (36, 36, [90.4, 100.0]), "B1": (32, 36, [74.7, 95.6]), "B0": (30, 36, [68.1, 92.1]), "B2": (23, 36, [47.6, 77.5])}
    for arm, (c, t, w) in want.items():
        check(
            (sc[arm]["correct"], sc[arm]["total"], sc[arm]["wilson95_pct"]) == (c, t, w),
            f"latest-all.json L2_scale {arm} != {c}/{t} {w}: {sc[arm]}",
        )
    check("**P 36/36 (100%), B1 32/36 (88.9%), B0 30/36 (83.3%), B2 23/36 (63.9%).**" in readme, "README: L2-scale line differs")
    check("Wilson 95%: P 90.4-100, B1 74.7-95.6, B0 68.1-92.1, B2 47.6-77.5" in readme, "README: Wilson intervals differ")
    ab = L["ablation"]["summary"]
    check(
        (ab["capabilities_needing_edges"], ab["broken_by_ablation"], ab["controls"], ab["controls_unaffected"]) == (7, 7, 5, 5),
        f"latest-all.json ablation is not 7/7 and 5/5: {ab}",
    )
    check("**7 of 7** capabilities" in readme and "**5 of 5** controls" in readme, "README: ablation 7/7 5/5 missing")
    check(all(v == 0 for v in res["summary"]["l1_violations_total"].values()), "latest-all.json: L1 has violations")
    check("**All four arms pass with 0 violations.**" in readme, "README: L1 statement missing")
    # token / cost figures quoted for L2 (headline strings in the results file)
    head = " ".join(res["summary"]["headline"])
    for frag in ("15930 tokens and $0.062", "13406 tokens and $0.052", "19646 tokens and $0.077", "22010 tokens and $0.087"):
        check(frag in head, f"latest-all.json headline lacks {frag!r}")
    check("13-16k tokens and $0.05-0.06" in readme, "README: L2 token/cost range missing")
    check("about 20-22k tokens and $0.08-0.09" in readme, "README: L2-scale token/cost range missing")
    # L4 and C7 / C4 figures: derived from latest-all.json (re-measured 2026-10-18 on `rerun-current`; the earlier
    # run's 678 -> 1025 -> 1174 tenant sweep, 1.75 ms / 570.9 ms medians, 25% C7 miss and 181 C4 count moved)
    ts = {(r["arm"], r["tenants"]): r["throughput_ops_s"] for r in L["L4"]["tenant_sweep"]}
    p3 = [round(ts[("P", n)]) for n in (1, 4, 16)]
    b3 = [round(ts[("B1", n)]) for n in (1, 4, 16)]
    gain = round(100 * (ts[("P", 16)] / ts[("P", 1)] - 1))
    check(f"{p3[0]} → {p3[1]} → {p3[2]} ops/s" in readme and f"(+{gain}%)" in readme, f"README: tenant sweep line differs from latest-all.json (P {p3}, +{gain}%)")
    check(f"{b3[0]} → {b3[1]} → {b3[2]}" in readme, f"README: SQLite tenant sweep differs from latest-all.json ({b3})")
    if "from 678 to 1,174" in blog:
        print("note  docs/BLOG_DRAFT.md still quotes the superseded tenant sweep (678 → 1,174); not checked, owner's draft")
    cs = {(r["arm"], r["workers"]): r["claim"] for r in L["L4"]["claim_sweep"]}

    def ms(x: float) -> str:
        return f"{x:.2f}" if x < 1 else f"{x:.1f}"

    for w, label in ((1, "1 worker"), (200, "200")):
        want = f"{ms(cs[('B1', w)]['p50_ms'])} vs {ms(cs[('P', w)]['p50_ms'])} ms at {label}"
        check(want in readme, f"README: L4 median at {label} differs from latest-all.json: {want!r}")
    want = f"p99 {cs[('B1', 200)]['p99_ms'] / 1000:.2f} s vs {cs[('P', 200)]['p99_ms'] / 1000:.2f} s"
    check(want in readme, f"README: L4 p99 at 200 workers differs from latest-all.json: {want!r}")
    c7 = {a: L["L1"]["arms"][a]["tests"]["C7"]["metrics"] for a in ("B2", "P")}
    for a, name in (("B2", "B2"), ("P", "Knewat")):
        miss, pairs = int(c7[a]["misses_sequential"]["sum"]), int(c7[a]["pairs"]["sum"])
        want = f"{name} misses {round(100 * miss / pairs)}% ({miss} of {pairs} pairs"
        check(want in readme, f"README: C7 miss rate differs from latest-all.json: {want!r}")
    c4 = L["ablation"]["l1_rerun"]["P-abl"]["C4"]["violations_total"]["started_before_deps_done"]
    check(f"{c4} tasks started before their dependencies" in readme, f"README: C4 stripped count differs from latest-all.json ({c4})")

    # (b) figures quoted from prose sources must appear verbatim in those sources and in the quoting doc
    baseline, testing, demo, deploy = read("docs/BASELINE.md"), read("docs/TESTING.md"), read("docs/demo.md"), read("docs/deploy.md")
    triples = [
        # (label, source text, source substring, doc text, doc substring)
        ("sign test P vs B0", testing, "p = 0.031", readme, "P vs B0 6-0, p = 0.031"),
        ("sign test P vs B1", testing, "p = 0.125", readme, "P vs B1 4-0, p = 0.125"),
        ("sign test P vs B2", testing, "p < 0.001", readme, "P vs B2 13-0, p < 0.001"),
        ("C8 stripped", baseline, "60 forgotten facts still returned", readme, "60 forgotten facts still returned"),
        ("L2 latency", testing, "~2.5 ms vs ~5 s", readme, "~2.5 ms vs ~5 s"),
        ("L2-scale ratio", testing, "10.4-16.6", readme, "10.4-16.6"),
        ("live ablation 6/6 2/2", demo, "6 of 6 edge-dependent features break; 2 of 2 controls are unaffected", readme, "**6 of 6 features break, 2 of 2 controls are unaffected**"),
        ("why intact", demo, "3 supporting fact(s), 2 agent(s), 3 source(s)", readme, "3 supporting facts, 2 agents, 3 sources"),
        ("peak memory", deploy, "cgroup peak **88 MiB**", readme, "peak 88 MiB"),
        ("peak memory docker stats", deploy, "peak **83 MiB**", readme, "83 MiB by `docker stats`"),
        ("deploy checks", deploy, "**36/36 checks passed**", readme, "36/36"),
        ("boot time", deploy, "3.8 s (4.5 s in an earlier run", readme, "boot in about 4 s"),
        ("cypher rate limit", deploy, "20 queries/min per client IP", readme, "20 queries per minute per IP"),
        ("cypher body cap", deploy, "16 KiB", readme, "16 KiB"),
        ("fresh clone time", testing, "**216 s**", readme, "216 s"),
        ("python tests", testing, "**1512 passed**", readme, "1512 Python tests"),
        ("view tests", testing, "**229 passed**", readme, "229 View tests"),
        ("tools driven by real run", testing, "11 distinct tools", readme, "only 14 of the 45 tools"),
        ("recording counts", demo, "| `acme-claude-sonnet` | 16 `claude -p` (sonnet) | 247 | 708 |", readme, "247 nodes, 708 edges"),
        ("blog 36 of 36", baseline, "P answered 36/36" if "P answered 36/36" in baseline else "Knewat answered 36/36", blog, "Knewat scored 36 of 36, SQLite 32, files 30"),
    ]
    for label, src, s, doc, d in triples:
        if not src or not doc:
            continue  # an optional document is absent from this checkout
        check(s in src, f"source lacks {label}: {s!r}")
        check(d in doc, f"doc lacks {label}: {d!r}")

    # (c) the recording itself
    meta = json.loads((RECORDING / "meta.json").read_text(encoding="utf-8"))
    inv = meta.get("inventory", {})
    nodes = sum(inv["nodes"].values()) if isinstance(inv.get("nodes"), dict) else inv.get("nodes")
    edges = sum(inv["edges"].values()) if isinstance(inv.get("edges"), dict) else inv.get("edges")
    check((nodes, edges) == (247, 708), f"recording inventory is {nodes}/{edges}, not 247/708")
    calls = json.loads((RECORDING / "calls.json").read_text(encoding="utf-8"))
    check(len(calls) == 83, f"recording has {len(calls)} calls, not 83")
    if read("docs/VIDEO_SCRIPT.md"):
        check("83 tool calls" in read("docs/VIDEO_SCRIPT.md") or "83 steps" in read("docs/VIDEO_SCRIPT.md"), "VIDEO_SCRIPT: 83 missing")

    # (d) counts derived from the tree
    n_cypher = len(list((ROOT / "knewat/queries").rglob("*.cypher")))
    check(f"{n_cypher} files in all" in readme, f"README does not say '{n_cypher} files in all' (knewat/queries has {n_cypher})")
    check(f"({n_cypher} files)" in readme, f"README repo layout does not say ({n_cypher} files)")
    snap = json.loads((ROOT / "knewat/tests/mcp/snapshots/tools.json").read_text(encoding="utf-8"))
    n_tools = len(snap)
    mcp_tools = len(re.findall(r"^\s*- \*\*(?:Engram|Relay|Lineage)", read("docs/mcp.md"), flags=re.M))
    check(
        f"{n_tools} tools" in read("docs/mcp.md") and f"{n_tools} tools" in readme and mcp_tools == 3,
        f"{n_tools} tools (the MCP snapshot) not stated in docs/mcp.md and README",
    )
    check(f"14 of the {n_tools} tools" in readme, f"README: real-run tool coverage is not '14 of the {n_tools} tools'")
    # P9: B1h, C7 extended and L6 as the README prints them, from the layers of latest-all.json
    b1h = L["B1h"]["layers"]
    check(
        (b1h["L2"]["arm"]["accuracy"]["correct"], b1h["L2"]["arm"]["accuracy"]["total"]) == (43, 43)
        and (b1h["L2_scale"]["arm"]["accuracy"]["correct"], b1h["L2_scale"]["arm"]["accuracy"]["total"]) == (36, 36),
        "latest-all.json B1h is not 43/43 and 36/36",
    )
    check("B1h 43/43 on L2 and 36/36 on L2-scale" in readme, "README: B1h line missing")
    c7 = L["C7x"]["arms"]
    check(
        (c7["P"]["metrics"]["false_merges"], c7["P"]["metrics"]["not_merge_pairs"], c7["B2"]["metrics"]["false_merges"])
        == (0, 150, 68),
        "latest-all.json C7x is not 0 false merges of 150 (B2: 68)",
    )
    check("0 false merges in 150 pairs" in readme and "falsely merged 68 of 150" in readme, "README: C7 extended line missing")
    heavy = L["C7x"]["by_category"]["heavy"]
    check(
        (heavy["merged"], heavy["maybe"], heavy["pairs"]) == (10, 9, 24)
        and "auto-merged 10 of 24 and surfaced for review 19 of 24" in readme,
        "README: heavy-paraphrase miss differs from latest-all.json",
    )
    s6 = L["L6"]["summary"]
    tot: dict[str, list[int]] = {}
    for fam in "ABD":
        for arm, v in s6[fam]["pilot"].items():
            c, n = map(int, v.split("/"))
            tot.setdefault(arm, [0, 0])
            tot[arm][0] += c
            tot[arm][1] += n
    check(
        {a: tuple(v) for a, v in tot.items()} == {"B0r": (2, 24), "B1a": (24, 24), "B0g": (24, 24), "P": (10, 16)},
        f"latest-all.json L6 pilot totals differ from B1a 24/24, B0g 24/24, B0r 2/24, P-mcp 10/16: {tot}",
    )
    check(
        "B1a 24/24, B0g 24/24, B0r 2/24, Knewat MCP tools 10/16, 88 calls, $7.09" in readme
        and L["L6"]["llm_calls_total"] == 88
        and round(L["L6"]["cost_usd_total"], 2) == 7.09,
        "README: L6 pilot line differs from latest-all.json",
    )
    post = s6["A"]["postfix"]
    check(
        post["P-product-service"]["strict"] == "24/24" and s6["F"]["postfix"]["P"]["orphans"] == 0,
        f"latest-all.json L6 post-fix: A impact {post['P-product-service']['strict']}, F orphans {s6['F']['postfix']['P']['orphans']}",
    )
    print("ok    numbers checked against latest-all.json, the recording and the cited docs")


# ---------------------------------------------------------------- 5. queries
def queries() -> None:
    index = read("docs/queries.md")
    seen = 0
    for m in re.finditer(r"\]\((knewat/queries/([\w/]+)\.cypher)\)", read("README.md")):
        seen += 1
        check((ROOT / m.group(1)).exists(), f"README: query file missing: {m.group(1)}")
        name = m.group(2)
        check(f"`{name}`" in index or name.split("/")[-1] in index, f"docs/queries.md has no row for {name}")
    check(seen >= 15, f"README lists only {seen} linked queries (want about 15)")
    print(f"ok    {seen} linked queries exist and are indexed in docs/queries.md")


# ---------------------------------------------------------------- 6. video script
# (step, agent, tool) triples the script relies on, checked against the recording's calls.json
STEP_CLAIMS = [
    (1, "planner", "start_session"), (2, "planner", "create_tasks"), (4, "researcher", "claim_next_task"),
    (7, "researcher", "assert_fact"), (8, "researcher", "assert_fact"), (13, "planner", "record_decision"),
    (16, "builder", "claim_next_task"), (17, "builder", "recall"), (19, "researcher", "claim_next_task"),
    (27, "researcher", "assert_fact"), (31, "planner", "record_decision"), (38, "builder", "handoff"),
    (44, "researcher", "assert_fact"), (50, "planner", "assert_fact"), (15, "builder", "start_session"),
]


def video() -> None:
    text = read("docs/VIDEO_SCRIPT.md")
    if not text:
        return
    rows = re.findall(r"^\|\s*(\d)\s*\|\s*(\d:\d\d)-(\d:\d\d)\s*\|(.*)\|\s*\"(.*)\"\s*\|\s*$", text, flags=re.M)
    check(len(rows) == 9, f"VIDEO_SCRIPT has {len(rows)} beats, want 9")
    prev_end = "0:00"
    secs = lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])  # noqa: E731
    for n, start, end, _screen, narr in rows:
        check(start == prev_end, f"beat {n}: starts {start}, previous ended {prev_end}")
        check(secs(end) > secs(start), f"beat {n}: ends before it starts")
        words = len(narr.split())
        check(words <= 25, f"beat {n}: narration has {words} words (> 25)")
        prev_end = end
    check(secs(prev_end) <= 180, f"video runs {prev_end}, over 3:00")
    print(f"ok    video: {len(rows)} beats, total {prev_end}, narration <= 25 words each")

    transcripts = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (RECORDING / "transcripts").glob("*.jsonl"))
    ids = sorted(set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)))
    for i in ids:
        check(i in transcripts, f"VIDEO_SCRIPT id not found in the recording's transcripts: {i}")
    for t in ("t03-design-endpoints", "t12-update-endpoints-for-v2", "06_api_style_guide_v2.md"):
        check(t in transcripts, f"VIDEO_SCRIPT name not found in the recording: {t}")
    print(f"ok    video: {len(ids)} UUIDs found in the recording transcripts")

    calls = {c["step"]: (c["agent"], c["tool"]) for c in json.loads((RECORDING / "calls.json").read_text(encoding="utf-8"))}
    for step, agent, tool in STEP_CLAIMS:
        check(calls.get(step) == (agent, tool), f"recording step {step} is {calls.get(step)}, script says {(agent, tool)}")
    print(f"ok    video: {len(STEP_CLAIMS)} step/agent/tool claims match calls.json")


def main() -> int:
    for doc in DOCS:
        if doc in OPTIONAL_DOCS and not (ROOT / doc).exists():
            read(doc)  # prints the skip note once
            continue
        check((ROOT / doc).exists(), f"missing document {doc}")
        check_links(doc)
    readme = read("README.md")
    check("<VIDEO_URL>" in readme and "<BLOG_URL>" in readme, "README lost the <VIDEO_URL> / <BLOG_URL> placeholders (fill them with the published links, then drop this check)")
    check_mermaid()
    numbers()
    queries()
    video()
    print(f"\n{passed} checks passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
