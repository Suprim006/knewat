"""What each baseline arm shows the LLM: its own artifacts, at an equal character budget (BASELINE §2 step 3).

* **B0 Files**: the tenant directory as the arm wrote it (``tasks.json``, ``MEMORY.md``, ``decisions.jsonl``,
  ``handoffs.jsonl``, ``sources.json``, per-agent ``logs/*.jsonl``), concatenated in that priority order and cut at the
  budget. Lock files and empty agent markers are skipped.
* **B1 SQLite**: the schema (``CREATE TABLE`` text) plus every content table dumped as CSV, in priority order, cut at
  the budget. Single-shot: the model cannot run SQL, so a dump is what a one-shot reader gets.
* **B2 Vector**: the store's rows rendered as self-contained memory chunks (one per fact, decision, handoff, episode,
  task, source), embedded with the same local model Plexus uses; the top-k chunks for the question text, cut at the
  budget. Retrieval is the point of this arm, so it sees only k chunks, not the whole store.

Each builder returns a :class:`Context` with the exact text, its length and whether anything was cut, so the report
can say when an arm's artifacts did not fit.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from plexus.crucible.backends.sqlite import SCHEMA
from plexus.embed import Embedder, embed_checked

CONTEXT_CHARS = 32_000
B2_TOP_K = 12


@dataclass
class Context:
    arm: str
    text: str
    artifact_chars: int  # size of the arm's artifacts before the budget cut
    truncated: bool
    parts: list[str] = field(default_factory=list)  # which files / tables / chunks went in
    omitted: list[str] = field(default_factory=list)  # what the budget cut (or did not fit)

    @property
    def chars(self) -> int:
        return len(self.text)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def _fit(arm: str, blocks: list[tuple[str, str]], budget: int, preface: str = "") -> Context:
    """Concatenate ``(name, text)`` blocks in order until ``budget`` chars; the block that crosses it is cut."""
    out, used, parts, omitted = [preface] if preface else [], len(preface), [], []
    total = len(preface) + sum(len(t) for _, t in blocks)
    for name, text in blocks:
        room = budget - used
        if room <= 0:
            omitted.append(name)
            continue
        if len(text) > room:
            mark = "\n...[cut at the context budget]\n"
            text = text[: max(0, room - len(mark))] + mark[:room]
            omitted.append(f"{name} (cut)")
        out.append(text)
        used += len(text)
        parts.append(name)
    return Context(arm, "".join(out), total, bool(omitted), parts, omitted)


# ------------------------------------------------------------------------------------------------ B0
B0_ORDER = ("tasks.json", "MEMORY.md", "decisions.jsonl", "handoffs.jsonl", "sources.json")


def b0_context(tenant_dir: Path, budget: int = CONTEXT_CHARS) -> Context:
    blocks: list[tuple[str, str]] = []
    names = [n for n in B0_ORDER if (tenant_dir / n).exists()]
    names += [f"logs/{p.name}" for p in sorted((tenant_dir / "logs").glob("*.jsonl"))]
    for n in names:
        body = (tenant_dir / n).read_text(encoding="utf-8").replace("\r\n", "\n")
        blocks.append((n, f"=== file: {n} ===\n{body.rstrip()}\n\n"))
    pre = "The team's shared files (the complete memory directory of one run):\n\n"
    return _fit("B0", blocks, budget, pre)


# ------------------------------------------------------------------------------------------------ B1
B1_TABLES = (
    "tasks", "deps", "artifacts", "facts", "fact_agents", "fact_links", "sources", "decisions",
    "decision_facts", "handoffs", "handoff_items", "episodes", "agents", "steps", "step_reads", "step_wrote",
)  # fmt: skip
_DROP_COLS = {"facts": {"entity", "norm_value", "tokens", "recorded_at", "confidence"}}


def _ddl(table: str) -> str:
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table}\((.*?)\);\n", SCHEMA, re.DOTALL)
    return f"CREATE TABLE {table}({' '.join(m.group(1).split())});" if m else ""


def _csv(conn: sqlite3.Connection, table: str) -> str:
    cur = conn.execute(f"SELECT * FROM {table}")  # table names come from B1_TABLES, never from input
    cols = [c[0] for c in cur.description]
    keep = [i for i, c in enumerate(cols) if c not in _DROP_COLS.get(table, ())]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([cols[i] for i in keep])
    for row in cur:
        w.writerow([row[i] for i in keep])
    return buf.getvalue()


def b1_context(db_path: Path, budget: int = CONTEXT_CHARS, arm: str = "B1") -> Context:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        blocks = []
        for t in B1_TABLES:
            blocks.append((t, f"-- table {t}\n{_ddl(t)}\n{_csv(conn, t).rstrip()}\n\n"))
    finally:
        conn.close()
    pre = (
        "A SQLite database holding one team run. Each table follows, with its CREATE statement and its rows as CSV.\n"
        "decision_facts links a decision to the facts it was based on; fact_links (kind derived_from / supersedes /\n"
        "contradicts) links facts to sources and other facts; fact_agents says which agents asserted a fact;\n"
        "handoff_items lists the artifacts and facts a handoff carries.\n\n"
    )
    return _fit(arm, blocks, budget, pre)


# ------------------------------------------------------------------------------------------------ B2
def _label(pred: str, value: str) -> str:
    return f"{pred}={' '.join(str(value).split())}"


def b2_chunks(db_path: Path) -> list[tuple[str, str]]:
    """Render the vector arm's store as self-contained memory chunks ``(kind, text)``."""
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        facts = {r["id"]: r for r in conn.execute("SELECT * FROM facts")}
        lab = {i: _label(r["predicate"], r["value"]) for i, r in facts.items()}
        src = {r["id"]: r["uri"] for r in conn.execute("SELECT id, uri FROM sources")}
        agents: dict[str, list[str]] = {}
        for r in conn.execute("SELECT fact_id, agent_id FROM fact_agents ORDER BY at"):
            agents.setdefault(r["fact_id"], []).append(r["agent_id"])
        links: dict[tuple[str, str], list[str]] = {}
        for r in conn.execute("SELECT src, dst, kind FROM fact_links ORDER BY src, dst"):
            links.setdefault((r["src"], r["kind"]), []).append(r["dst"])
            if r["kind"] in ("supersedes", "contradicts"):
                links.setdefault((r["dst"], "by_" + r["kind"]), []).append(r["src"])
        chunks: list[tuple[str, str]] = []
        for i, f in facts.items():
            origin = [src[x] for x in links.get((i, "derived_from"), []) if x in src]
            sup = [lab[x] for x in links.get((i, "supersedes"), [])]
            sup_by = [lab[x] for x in links.get((i, "by_supersedes"), [])]
            con = [
                lab[x] for x in {*links.get((i, "contradicts"), []), *links.get((i, "by_contradicts"), [])}
            ]
            text = (
                f"Fact {lab[i]} about '{f['entity_name']}' (scope {f['scope']}; status {f['status']}; "
                f"valid_from {f['valid_from']}; valid_to {f['valid_to']}); asserted by {', '.join(agents.get(i, []))}"
                + (f"; source {', '.join(origin)}" if origin else "")
                + (f"; supersedes {', '.join(sup)}" if sup else "")
                + (f"; superseded by {', '.join(sup_by)}" if sup_by else "")
                + (f"; contradicts {', '.join(sorted(con))}" if con else "")
                + "."
            )
            chunks.append(("fact", text))
        based: dict[str, list[str]] = {}
        for r in conn.execute("SELECT decision_id, fact_id FROM decision_facts"):
            based.setdefault(r["decision_id"], []).append(lab[r["fact_id"]])
        for r in conn.execute("SELECT * FROM decisions ORDER BY at"):
            chunks.append(
                (
                    "decision",
                    f'Decision by {r["agent_id"]} for task {r["task_id"]}: "{r["text"]}" '
                    f"Based on facts: {', '.join(based.get(r['id'], [])) or 'none'}."
                    + (" Flagged: a fact it relied on was forgotten." if r["flagged"] else ""),
                )
            )
        arts = {r["id"]: r["uri"] for r in conn.execute("SELECT id, uri FROM artifacts")}
        items: dict[str, list[tuple[str, str]]] = {}
        for r in conn.execute("SELECT handoff_id, kind, item_id FROM handoff_items"):
            items.setdefault(r["handoff_id"], []).append((r["kind"], r["item_id"]))
        for r in conn.execute("SELECT * FROM handoffs ORDER BY at"):
            its = items.get(r["id"], [])
            chunks.append(
                (
                    "handoff",
                    f'Handoff for task {r["task_id"]} from {r["from_agent"]} to {r["to_agent"]}: "{r["note"]}" '
                    f"Artifacts: {', '.join(arts.get(i, i) for k, i in its if k == 'artifact') or 'none'}. "
                    f"Facts: {', '.join(lab.get(i, i) for k, i in its if k == 'fact') or 'none'}.",
                )
            )
        for r in conn.execute("SELECT * FROM episodes ORDER BY at"):
            chunks.append(("episode", f'Episode recorded by {r["agent_id"]}: "{r["text"]}"'))
        deps: dict[str, list[str]] = {}
        for r in conn.execute("SELECT task_id, dep_id FROM deps ORDER BY dep_id"):
            deps.setdefault(r["task_id"], []).append(r["dep_id"])
        by_task: dict[str, list[str]] = {}
        for r in conn.execute("SELECT task_id, uri FROM artifacts"):
            by_task.setdefault(r["task_id"], []).append(r["uri"])
        for r in conn.execute("SELECT * FROM tasks ORDER BY seq"):
            chunks.append(
                (
                    "task",
                    f"Task {r['id']} ('{r['title']}', priority {r['priority']}) status {r['status']}, "
                    f"claimed by {r['claimed_by'] or 'nobody'}; depends on {', '.join(deps.get(r['id'], [])) or 'nothing'}; "
                    f"artifacts {', '.join(by_task.get(r['id'], [])) or 'none'}.",
                )
            )
        for r in conn.execute("SELECT * FROM sources ORDER BY created_at"):
            chunks.append(("source", f"Source {r['uri']} (kind {r['kind']}, trust {r['trust']})."))
        return chunks
    finally:
        conn.close()


class B2Index:
    """Chunks of one B2 store, embedded once; ``context(question)`` returns the top-k for a question."""

    def __init__(self, db_path: Path, embedder: Embedder):
        self.embedder = embedder
        self.chunks = b2_chunks(db_path)
        mat = np.asarray(embed_checked(embedder, [t for _, t in self.chunks]), dtype=np.float32)
        self.mat = mat / np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9)

    def top(self, query: str, k: int = B2_TOP_K) -> list[int]:
        q = np.asarray(embed_checked(self.embedder, [query]), dtype=np.float32)[0]
        q = q / max(float(np.linalg.norm(q)), 1e-9)
        sims = self.mat @ q
        order = np.lexsort((np.arange(len(sims)), -sims))  # best first, ties by position
        return [int(i) for i in order[:k]]

    def context(self, query: str, k: int = B2_TOP_K, budget: int = CONTEXT_CHARS) -> Context:
        idx = self.top(query, k)
        blocks = [(self.chunks[i][1], f"[{n}] {self.chunks[i][1]}\n") for n, i in enumerate(idx, 1)]
        pre = f"The {k} memory chunks most similar to the question, best first (retrieved from a vector store):\n\n"
        ctx = _fit("B2", blocks, budget, pre)
        ctx.artifact_chars = len(pre) + sum(
            len(t) + 1 for _, t in self.chunks
        )  # the whole store, for the report
        return ctx
