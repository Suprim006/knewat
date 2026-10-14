"""What each baseline shows the LLM at scale: competent retrieval inside the same 32,000-character budget.

At scale the history is >= 10x the budget, so cutting an artifact at the cap would show the model one corner of it. The
spec asks for competent selection instead; the question text is the retrieval query for every arm:

* **B0 Files**: the arm's files are cut into small chunks (one task of ``tasks.json``, one entry of ``sources.json``, one
  bullet of ``MEMORY.md``, one line of each ``*.jsonl``), ranked by BM25 against the question, and the best chunks that
  fit the cap are shown, grouped by file in file order (``[...]`` marks a gap).
* **B1 SQLite**: the full schema (every ``CREATE TABLE``) is always shown. Every row of every table is a document whose
  searchable text is the row plus the text of the rows its id columns point to (one hop: a ``decision_facts`` row is
  searchable by its decision's and its fact's words), ranked by BM25; the best rows that fit the cap are shown as CSV
  per table.
* **B2 Vector**: unchanged (``contexts.B2Index``): top-12 chunks by cosine similarity (local bge-small), same cap.

BM25 is Okapi with k1=1.5, b=0.75, ``idf = ln(1 + (N - n + 0.5) / (n + 0.5))``. Tokens are lower-case alphanumeric
runs; identifiers such as ``s07-t03-design-endpoints`` or ``api_version=v13`` are indexed whole AND as their parts (``api_version``, ``v13``, ``api``, ``version``); a
short English stop list is dropped; UUIDs are not indexed. Ties break by document order. Nothing here sees an answer.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plexus.crucible.l2.contexts import (
    _DROP_COLS,
    B1_TABLES,
    CONTEXT_CHARS,
    Context,
    _ddl,
    b0_context,
    b1_context,
)

K1, B = 1.5, 0.75
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_TOKEN = re.compile(r"[a-z0-9]+(?:[-_./:=][a-z0-9]+)*")
_SPLIT = re.compile(r"[-_./:=]")
_PIECE = re.compile(r"[=:]")
STOP = frozenset(
    "a an and are as at be by did do does for from has have how if in is it its of on or that the then this to was were "
    "what when where which who whom whose with after before about into than their there these those while would".split()
)


def tokens(text: str) -> list[str]:
    out: list[str] = []
    for m in _TOKEN.finditer(_UUID.sub(" ", text.casefold())):
        w = m.group(0)
        if w not in STOP:
            out.append(w)
        if _SPLIT.search(w):
            for piece in _PIECE.split(w):  # `api_version=v13` -> api_version, v13
                if piece and piece != w and piece not in STOP:
                    out.append(piece)
                out.extend(p for p in _SPLIT.split(piece) if p and p != piece and p not in STOP)
    return out


class Bm25:
    def __init__(self, docs: list[str]):
        self.tf = [Counter(tokens(d)) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 0.0
        df: Counter[str] = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def scores(self, query: str) -> list[float]:
        q = set(tokens(query))
        out = []
        for tf, ln in zip(self.tf, self.len, strict=True):
            s = 0.0
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * ln / (self.avg or 1.0)))
            out.append(s)
        return out

    def ranked(self, query: str) -> list[int]:
        sc = self.scores(query)
        return sorted(range(len(sc)), key=lambda i: (-sc[i], i))


# ------------------------------------------------------------------------------------------------ B0
@dataclass(frozen=True)
class Chunk:
    file: str
    text: str  # what is shown
    index_text: str  # what is searched


def b0_chunks(tenant_dir: Path) -> list[Chunk]:
    out: list[Chunk] = []

    def add(name: str, text: str) -> None:
        text = text.rstrip()
        if text:
            out.append(Chunk(name, text, f"{Path(name).stem} {text}"))

    def read(name: str) -> str:
        return (tenant_dir / name).read_text(encoding="utf-8").replace("\r\n", "\n")

    for name in ("tasks.json", "MEMORY.md", "decisions.jsonl", "handoffs.jsonl", "sources.json"):
        if not (tenant_dir / name).exists():
            continue
        body = read(name)
        if name == "tasks.json":
            doc = json.loads(body)
            add(name, json.dumps({"next_seq": doc.get("next_seq")}, separators=(",", ":")))
            for tid, t in doc["tasks"].items():
                add(name, json.dumps({tid: t}, separators=(",", ":"), ensure_ascii=False))
        elif name == "sources.json":
            for sid, s in json.loads(body).items():
                add(name, json.dumps({sid: s}, separators=(",", ":"), ensure_ascii=False))
        else:
            for line in body.split("\n"):
                add(name, line)
    for p in sorted((tenant_dir / "logs").glob("*.jsonl")):
        for line in read(f"logs/{p.name}").split("\n"):
            add(f"logs/{p.name}", line)
    return out


def _render_groups(
    arm: str, preface: str, groups: list[tuple[str, str, list[tuple[int, str]]]], total: int, parts: list[str]
) -> Context:
    """``groups``: (group header, group name, [(doc index, line)]) in display order."""
    out = [preface]
    for header, _name, lines in groups:
        out.append(header)
        prev = None
        for idx, line in lines:
            if prev is not None and idx != prev + 1:
                out.append("[...]\n")
            out.append(line if line.endswith("\n") else line + "\n")
            prev = idx
        out.append("\n")
    text = "".join(out)
    return Context(arm, text, total, True, parts, [])


def b0_scale_context(tenant_dir: Path, query: str, budget: int = CONTEXT_CHARS) -> Context:
    chunks = b0_chunks(tenant_dir)
    pre = "The team's shared files (the complete memory directory of the team's whole history). Excerpts most relevant to the question, grouped by file:\n\n"
    bm = Bm25([c.index_text for c in chunks])
    chosen: dict[str, list[int]] = {}
    used = len(pre)
    for i in bm.ranked(query):
        c = chunks[i]
        cost = len(c.text) + 1 + (0 if c.file in chosen else len(f"=== file: {c.file} ===\n") + 1) + 6
        if used + cost > budget:
            continue
        chosen.setdefault(c.file, []).append(i)
        used += cost
    order = list(dict.fromkeys(c.file for c in chunks))
    groups = [
        (f"=== file: {f} ===\n", f, [(i, chunks[i].text) for i in sorted(chosen[f])])
        for f in order
        if f in chosen
    ]
    parts = [f"{f}#{i}" for _h, f, ls in groups for i, _ in ls]
    ctx = _render_groups("B0", pre, groups, 0, parts)
    ctx.artifact_chars = b0_context(tenant_dir, 10**9).artifact_chars
    ctx.omitted = [f"{len(chunks) - len(parts)} of {len(chunks)} chunks not shown"]
    assert ctx.chars <= budget, (ctx.chars, budget)
    return ctx


# ------------------------------------------------------------------------------------------------ B1
@dataclass(frozen=True)
class Row:
    table: str
    cells: list[str]
    index_text: str


def _csv_line(cells: list[Any]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(cells)
    return buf.getvalue()


def b1_rows(db_path: Path) -> tuple[dict[str, list[str]], list[Row]]:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        headers: dict[str, list[str]] = {}
        raw: dict[str, list[list[Any]]] = {}
        for t in B1_TABLES:
            cur = conn.execute(f"SELECT * FROM {t}")  # names come from B1_TABLES
            cols = [c[0] for c in cur.description]
            keep = [i for i, c in enumerate(cols) if c not in _DROP_COLS.get(t, ())]
            headers[t] = [cols[i] for i in keep]
            raw[t] = [[r[i] for i in keep] for r in cur]
    finally:
        conn.close()
    by_id: dict[str, str] = {}
    for t, rows in raw.items():
        if "id" in headers[t]:
            k = headers[t].index("id")
            for r in rows:
                by_id[str(r[k])] = " ".join(str(x) for x in r)
    out: list[Row] = []
    for t, rows in raw.items():
        for r in rows:
            own = " ".join(str(x) for x in r)
            refs = [by_id[str(x)] for x in r if str(x) in by_id and by_id[str(x)] != own]
            out.append(Row(t, [str(x) if x is not None else "" for x in r], f"{t} {own} {' '.join(refs)}"))
    return headers, out


def b1_scale_context(db_path: Path, query: str, budget: int = CONTEXT_CHARS) -> Context:
    headers, rows = b1_rows(db_path)
    pre = (
        "A SQLite database holding the team's whole history. The CREATE statements of every table come first, then the rows\n"
        "most relevant to the question as CSV per table (not all rows are shown).\n"
        "decision_facts links a decision to the facts it was based on; fact_links (kind derived_from / supersedes /\n"
        "contradicts) links facts to sources and other facts; fact_agents says which agents asserted a fact;\n"
        "handoff_items lists the artifacts and facts a handoff carries.\n\n-- schema\n"
        + "\n".join(_ddl(t) for t in B1_TABLES)
        + "\n\n"
    )
    bm = Bm25([r.index_text for r in rows])
    chosen: dict[str, list[int]] = {}
    used = len(pre)
    for i in bm.ranked(query):
        r = rows[i]
        line = _csv_line(r.cells)
        cost = len(line) + (
            0 if r.table in chosen else len(f"-- table {r.table}\n") + len(_csv_line(headers[r.table])) + 1
        )
        if used + cost > budget:
            continue
        chosen.setdefault(r.table, []).append(i)
        used += cost
    out = [pre]
    parts = []
    for t in B1_TABLES:
        if t not in chosen:
            continue
        out.append(f"-- table {t}\n{_csv_line(headers[t])}")
        for i in sorted(chosen[t]):
            out.append(_csv_line(rows[i].cells))
            parts.append(f"{t}#{i}")
        out.append("\n")
    text = "".join(out)
    full = b1_context(db_path, 10**9).artifact_chars
    ctx = Context("B1", text, full, True, parts, [f"{len(rows) - len(parts)} of {len(rows)} rows not shown"])
    assert ctx.chars <= budget, (ctx.chars, budget)
    return ctx


def sprint_share(ctx: Context, tag: str) -> dict[str, int]:
    """Diagnostic for the report: how many of the shown lines/rows/chunks mention the question's sprint."""
    low = tag.casefold()
    lines = [ln for ln in ctx.text.split("\n") if ln.strip() and not ln.startswith(("===", "--", "[...]"))]
    return {"lines": len(lines), "lines_with_sprint": sum(low in ln.casefold() for ln in lines)}
