#!/usr/bin/env python3
"""Verify the submission documents: links, mermaid, quoted numbers, video-script ids and timing.

    python scripts/verify_readme.py                 # offline checks, exits 1 on any failure
    PLEXUS_MERMAID_DIR=<dir with `npm i mermaid jsdom`> python scripts/verify_readme.py   # also parses mermaid for real

Checked documents: README.md, docs/VIDEO_SCRIPT.md, docs/BLOG_DRAFT.md. Standard library only; no network, no database.

1. Links: every relative markdown link and every backticked repo path resolves to a file or directory; `#anchors` match a heading.
2. Placeholders: README keeps `<RENDER_URL>` and `<VIDEO_URL>` (the owner fills them in).
3. Mermaid: each block starts with a known diagram type (and is parsed by mermaid when PLEXUS_MERMAID_DIR is set).
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
DOCS = ["README.md", "docs/VIDEO_SCRIPT.md", "docs/BLOG_DRAFT.md"]
RESULTS = ROOT / "plexus/src/plexus/crucible/results/latest-all.json"
RECORDING = ROOT / "plexus/demo_data/recordings/acme-claude-sonnet"

failures: list[str] = []
passed = 0


def check(ok: bool, what: str) -> None:
    global passed
    if ok:
        passed += 1
    else:
        failures.append(what)
        print(f"FAIL  {what}")


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def strip_fences(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.S)


def slug(heading: str) -> str:
    s = re.sub(r"[`*_]", "", heading.strip().lower())
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"\s", "-", s)


# ---------------------------------------------------------------- 1. links
PATH_RE = re.compile(r"^(?:docs|plexus|plexus-view|deploy|scripts)/[\w./\-]*$|^(?:render\.yaml|docker-compose\.yml|README\.md|CLAUDE\.md)$")


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
            check(slug(frag) in headings or frag in headings, f"{doc}: anchor not found: #{frag}")
    # backticked repo paths (inline code only, in prose)
    for m in re.finditer(r"`([^`\n]+)`", prose):
        tok = m.group(1).strip()
        if any(c in tok for c in "<>*{}$ ") or not PATH_RE.match(tok):
            continue
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
    mdir = os.environ.get("PLEXUS_MERMAID_DIR")
    if not mdir:
        print("skip  mermaid parse (set PLEXUS_MERMAID_DIR to a directory with `npm i mermaid jsdom`)")
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
    readme = read("README.md")
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
    # L4 tenant sweep
    ts = {(r["arm"], r["tenants"]): r["throughput_ops_s"] for r in L["L4"]["tenant_sweep"]}
    check([round(ts[("P", n)]) for n in (1, 4, 16)] == [678, 1025, 1174], f"L4 tenant sweep P != 678/1025/1174: {ts}")
    check([round(ts[("B1", n)]) for n in (1, 4, 16)] == [1103, 1480, 500], f"L4 tenant sweep B1 != 1103/1480/500: {ts}")
    check(round(100 * (1174 / 678 - 1)) == 73, "tenant sweep gain is not +73%")
    check("678 → 1025 → 1174 ops/s" in readme and "(+73%)" in readme, "README: tenant sweep line missing")
    check("1103 → 1480 → 500" in readme, "README: SQLite tenant sweep missing")
    check("from 678 to 1,174" in blog and "+73%" in blog and "1,103 → 1,480 → 500" in blog, "BLOG: tenant sweep numbers missing")

    # (b) figures quoted from prose sources must appear verbatim in those sources and in the quoting doc
    baseline, testing, demo, deploy = read("docs/BASELINE.md"), read("docs/TESTING.md"), read("docs/demo.md"), read("docs/deploy.md")
    triples = [
        # (label, source text, source substring, doc text, doc substring)
        ("sign test P vs B0", testing, "p = 0.031", readme, "P vs B0 6-0, p = 0.031"),
        ("sign test P vs B1", testing, "p = 0.125", readme, "P vs B1 4-0, p = 0.125"),
        ("sign test P vs B2", testing, "p < 0.001", readme, "P vs B2 13-0, p < 0.001"),
        ("L4 1 worker median", testing, "0.10 ms vs 1.75 ms at 1 worker", readme, "0.10 vs 1.75 ms at 1 worker"),
        ("L4 200 worker median", testing, "0.82 ms vs 570.9 ms at 200", readme, "0.82 vs 570.9 ms at 200"),
        ("L4 p99 at 200", testing, "p99 2.18 s vs 1.86 s", readme, "p99 2.18 s vs 1.86 s"),
        ("C4 stripped", baseline, "181 tasks started before their dependencies finished", readme, "181 tasks started before their dependencies"),
        ("C8 stripped", baseline, "60 forgotten facts still returned", readme, "60 forgotten facts still returned"),
        ("C7 miss rate", baseline, "25% overall miss, 30 of 120 pairs", readme, "miss 25% (30 of 120 pairs"),
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
        ("blog 36 of 36", baseline, "P answered 36/36" if "P answered 36/36" in baseline else "Plexus answered 36/36", blog, "Plexus scored 36 of 36, SQLite 32, files 30"),
    ]
    for label, src, s, doc, d in triples:
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
    check("83 tool calls" in read("docs/VIDEO_SCRIPT.md") or "83 steps" in read("docs/VIDEO_SCRIPT.md"), "VIDEO_SCRIPT: 83 missing")

    # (d) counts derived from the tree
    n_cypher = len(list((ROOT / "plexus/queries").rglob("*.cypher")))
    check(f"{n_cypher} files in all" in readme, f"README does not say '{n_cypher} files in all' (plexus/queries has {n_cypher})")
    check(f"({n_cypher} files)" in readme, f"README repo layout does not say ({n_cypher} files)")
    snap = json.loads((ROOT / "plexus/tests/mcp/snapshots/tools.json").read_text(encoding="utf-8"))
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
        "B1a 24/24, B0g 24/24, B0r 2/24, Plexus MCP tools 10/16, 88 calls, $7.09" in readme
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
    for m in re.finditer(r"\]\((plexus/queries/([\w/]+)\.cypher)\)", read("README.md")):
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
        check((ROOT / doc).exists(), f"missing document {doc}")
        check_links(doc)
    readme = read("README.md")
    check("<RENDER_URL>" in readme and "<VIDEO_URL>" in readme, "README lost the <RENDER_URL> / <VIDEO_URL> placeholders")
    check_mermaid()
    numbers()
    queries()
    video()
    print(f"\n{passed} checks passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
