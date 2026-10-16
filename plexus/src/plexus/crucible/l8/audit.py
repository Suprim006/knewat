"""L8 end-of-run audit (§6.5) and the query-authoring probe (§6.9).

Audit: three questions per run against the arm's final store. P answers with Cypher statements, B1 with SQL
statements (both written before any run output was inspected; amendment 1 item 11), B0' with the L2-style tool-less
reader (``claude -p``, 32k chars of BM25-ranked context from ``memory/`` + ``history/``, one JSON answer, cached).
Ground truth comes from the L2-scale ledger (history) and the run's own transcripts and scorer output, never from a
store. Scoring is exact.

* Q1 decisions (all 21 sprints) that rely on the API style guide v1 family -> answered as {count, probes (10 decision
  texts: 5 in, 5 hard negatives from the v2 family), earliest5 (sprint tags of the 5 earliest)}; strict = all three.
* Q2 agents that read a fact later invalidated by c* (the run's first landed ``value`` commit), before it landed.
* Q3 S21 tasks whose ``complete_task`` used a fact already stale at completion (the scorer's own list).

Probe: one cold ``claude -p`` per (language, question, repetition), given only the schema document and the
question, asked for one statement; run by the harness on the seed-1 stores; up to 3 fix iterations with the error.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import sqlite3
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from plexus.crucible.l8.score import load_events

CACHE = Path(__file__).resolve().parents[4] / "demo_data" / "crucible" / "l8" / "cache"
MODEL = "sonnet"
READER_BUDGET = 32_000
V1 = "02_api_style_guide_v1"
V2 = "06_api_style_guide_v2"

Q_TEXT = {
    "Q1": "Which decisions, across all 21 sprints (S01-S21), relied directly on a fact that came from the API style "
          "guide v1 family of sources (the documents named '02_api_style_guide_v1')?",
    "Q2": "Which agents read a fact whose value was {old} (the value(s) of {funcs} before change {k}), before that "
          "change landed?",
    "Q3": "Which tasks of sprint S21 were completed (complete_task) with an artifact summary that used a fact value "
          "that was already stale (superseded, or flagged suspect) when the task was completed?",
}  # fmt: skip

# ------------------------------------------------------------------------------------------------ statements
CYPHER = {
    "Q1": (
        "MATCH (d:Decision)-[:BASED_ON]->(:Fact)-[:DERIVED_FROM*1..3]->(s:Source) "
        "WHERE s.uri CONTAINS '02_api_style_guide_v1' RETURN DISTINCT d.text AS text, d.at AS at ORDER BY at"
    ),
    "Q2": "MATCH (s:Step)-[:READ]->(f:Fact) WHERE f.value IN $old AND s.at < $t RETURN DISTINCT s.agent_id AS agent",
    "Q3": (
        "MATCH (a:Artifact)-[:FOR]->(t:Task {status: 'done'}) MATCH (f:Fact) "
        "WHERE f.value STARTS WITH 'AX-' AND a.summary CONTAINS f.value "
        "AND (f.valid_to <= t.done_at OR (coalesce(f.suspect_since, 0) > 0 AND f.suspect_since <= t.done_at)) "
        "RETURN DISTINCT t.id AS task"
    ),
}
SQL = {
    "Q1": (
        "WITH RECURSIVE anc(fact_id, node) AS ("
        " SELECT src, dst FROM fact_links WHERE kind = 'derived_from'"
        " UNION SELECT a.fact_id, l.dst FROM anc a JOIN fact_links l ON l.src = a.node AND l.kind = 'derived_from')"
        " SELECT DISTINCT d.text, d.at FROM decisions d JOIN decision_facts df ON df.decision_id = d.id"
        " JOIN anc ON anc.fact_id = df.fact_id JOIN sources s ON s.id = anc.node"
        " WHERE s.uri LIKE '%02_api_style_guide_v1%' ORDER BY d.at"
    ),
    "Q2": (
        "SELECT DISTINCT s.agent_id FROM step_reads r JOIN steps s ON s.id = r.step_id JOIN facts f ON f.id = r.fact_id"
        " WHERE f.value IN ({old}) AND s.at < :t"
    ),
    "Q3": (
        "SELECT DISTINCT t.id FROM tasks t JOIN artifacts a ON a.task_id = t.id JOIN facts f"
        " ON instr(a.summary, f.value) > 0 WHERE t.status = 'done' AND f.value LIKE 'AX-%' AND f.valid_to <= t.done_at"
    ),
}


def norm(s: str) -> str:
    return " ".join(str(s).split()).strip()


# ------------------------------------------------------------------------------------------------ truth
_LEDGER: list[Any] | None = None


def history_ledger() -> list[Any]:
    """The L2-scale ledger of the 20 preloaded sprints (deterministic; replayed into a throwaway SQLite store)."""
    global _LEDGER
    if _LEDGER is None:
        from plexus.crucible.api import BackendSpec
        from plexus.crucible.backends import open_backend
        from plexus.crucible.l2.scale_scenario import play_scale

        root = tempfile.mkdtemp(prefix="l8-ledger-", dir=os.environ.get("TMPDIR"))
        b = open_backend(BackendSpec(arm="B1", tenant="l8ledger", root=root))
        _LEDGER = play_scale(b, 20).ledgers
        b.close()
    return _LEDGER


def q1_truth(evs: list[Any]) -> dict[str, Any]:
    hist = []
    for led in history_ledger():
        src = {f["label"]: f["source_uri"] for f in led.facts}
        for d in led.decisions:
            if any(V1 in src.get(lab, "") for lab in d["fact_labels"]):
                hist.append((d["t"], norm(d["text"]), led.subject.rsplit(" ", 1)[-1]))
    # S21: record_decision whose based_on includes a fact asserted with the v1 source's id
    v1_sources, v1_facts, s21 = set(), set(), []
    uses = [e for e in evs if e.kind == "use"]
    for e in uses:
        if not (e.mcp and e.result and not e.result.is_error):
            continue
        if e.tool == "add_source" and V1 in str(e.input.get("uri", "")):
            v1_sources.add(e.result.data.get("source_id"))
        elif (
            e.tool == "assert_fact"
            and e.input.get("source_id") in v1_sources
            and e.result.data.get("fact_id")
        ):
            v1_facts.add(e.result.data["fact_id"])
        elif e.tool == "record_decision" and set(e.input.get("based_on_fact_ids") or []) & v1_facts:
            s21.append((math.inf, norm(e.input.get("text", "")), "S21"))
    allv = sorted(hist) + s21
    return {"texts": [x[1] for x in allv], "count": len(allv), "earliest5": [x[2] for x in sorted(hist)[:5]]}


def q1_probes(seed: int) -> list[tuple[str, bool]]:
    rng = random.Random(seed)
    led = history_ledger()
    ins = [
        norm(next(d["text"] for d in led[n - 1].decisions if "Build the Acme" in d["text"]))
        for n in rng.sample(range(1, 21), 5)
    ]
    outs = [
        norm(next(d["text"] for d in led[n - 1].decisions if "Adopt style guide" in d["text"]))
        for n in rng.sample(range(1, 21), 5)
    ]
    probes = [(t, True) for t in ins] + [(t, False) for t in outs]
    rng.shuffle(probes)
    return probes


def first_value_commit(run: dict[str, Any], sent: dict[str, Any]) -> dict[str, Any] | None:
    vc = [c for c in run["commits_landed"] if c["kind"] == "value"]
    if not vc:
        return None
    c = min(vc, key=lambda x: x["k"])
    old = []
    for f in c["funcs"]:
        prev = [
            h["token"]
            for h in sent["functions"][f]
            if h.get("from_turn", 0) >= 0 and (h.get("change") is None or h["change"] < c["k"])
        ]
        old.append(prev[-1])
    return {"k": c["k"], "funcs": c["funcs"], "old": old, "turn": c["landed_before_turn"], "t_ms": c["t_ms"]}


def q2_truth(evs: list[Any], cstar: dict[str, Any]) -> list[str]:
    agents = set()
    for e in evs:
        if e.turn >= cstar["turn"]:
            continue
        if e.kind == "result" and not e.is_error and any(o in e.text for o in cstar["old"]):
            agents.add(e.agent)
    return sorted(agents)


def q3_truth(metrics: dict[str, Any]) -> list[str]:
    return sorted({a["task"] for a in metrics["actions"] if a["tool"] == "complete_task" and a["stale"]})


# ------------------------------------------------------------------------------------------------ store answers
def q1_from_rows(rows: list[tuple[str, Any]], probes: list[tuple[str, bool]]) -> dict[str, Any]:
    texts = [norm(r[0]) for r in rows]
    have = set(texts)
    tags = []
    for t in texts:
        m = re.match(r"(S\d\d):", t)
        tags.append(m.group(1) if m else "S21")
    return {"count": len(texts), "probes": [p in have for p, _ in probes], "earliest5": tags[:5]}


def q1_correct(ans: dict[str, Any], truth: dict[str, Any], probes: list[tuple[str, bool]]) -> dict[str, Any]:
    pr = ans.get("probes") or []
    probes_ok = len(pr) == len(probes) and all(bool(a) == b for a, (_, b) in zip(pr, probes, strict=False))
    count_ok = ans.get("count") == truth["count"]
    early_ok = [str(x).upper() for x in (ans.get("earliest5") or [])] == truth["earliest5"]
    return {"count_ok": count_ok, "probes_ok": probes_ok, "earliest_ok": early_ok, "correct": count_ok and probes_ok and early_ok,
            "probes_right": sum(1 for a, (_, b) in zip(pr, probes, strict=False) if bool(a) == b)}  # fmt: skip


def answer_p(
    tenant: str, host: str, port: int, cstar: dict[str, Any] | None, probes: list[tuple[str, bool]]
) -> dict[str, Any]:
    from plexus.graph.client import GraphClient
    from plexus.graph.tenancy import graph_name

    gc = GraphClient(host=host, port=port)
    g = gc.graph(graph_name(tenant))
    out: dict[str, Any] = {}
    out["Q1"] = q1_from_rows(g.ro_query(CYPHER["Q1"]).result_set, probes)
    if cstar:
        out["Q2"] = sorted(
            r[0] for r in g.ro_query(CYPHER["Q2"], {"old": cstar["old"], "t": cstar["t_ms"]}).result_set
        )
    out["Q3"] = sorted(r[0] for r in g.ro_query(CYPHER["Q3"]).result_set)
    gc.close()
    return out


def b1_db(run: dict[str, Any]) -> Path:
    root = Path(run["workdir"]).parent / "store"
    return next(root.rglob("crucible.db"))


def answer_b1(db: Path, cstar: dict[str, Any] | None, probes: list[tuple[str, bool]]) -> dict[str, Any]:
    c = sqlite3.connect(str(db))
    out: dict[str, Any] = {"Q1": q1_from_rows(c.execute(SQL["Q1"]).fetchall(), probes)}
    if cstar:
        q = SQL["Q2"].format(old=",".join("?" for _ in cstar["old"])).replace(":t", "?")
        out["Q2"] = sorted(r[0] for r in c.execute(q, [*cstar["old"], cstar["t_ms"]]).fetchall())
    out["Q3"] = sorted(r[0] for r in c.execute(SQL["Q3"]).fetchall())
    c.close()
    return out


# ------------------------------------------------------------------------------------------------ the B0' reader
def _chunks(text: str, size: int = 1500) -> list[str]:
    lines, cur, out = text.splitlines(), [], []
    n = 0
    for line in lines:
        cur.append(line)
        n += len(line) + 1
        if n >= size:
            out.append("\n".join(cur))
            cur, n = [], 0
    if cur:
        out.append("\n".join(cur))
    return out


def bm25_context(run_dir: Path, history: Path | None, question: str, budget: int = READER_BUDGET) -> str:
    mem = "\n\n".join(f"=== {p.relative_to(run_dir).as_posix()} ===\n{p.read_text(encoding='utf-8', errors='replace')}"
                      for p in sorted((run_dir / "memory").rglob("*")) if p.is_file())  # fmt: skip
    parts = [mem[: budget // 2]]
    left = budget - len(parts[0])
    if history and history.exists():
        docs = []
        for p in sorted(history.rglob("*")):
            if p.is_file() and p.suffix in (".md", ".jsonl", ".json"):
                docs += _chunks(p.read_text(encoding="utf-8", errors="replace"))
        q = [w for w in re.findall(r"\w+", question.lower()) if len(w) > 2]
        df = Counter(w for d in docs for w in set(re.findall(r"\w+", d.lower())))
        N = len(docs) or 1
        avg = sum(len(d) for d in docs) / N

        def score(d: str) -> float:
            tf = Counter(re.findall(r"\w+", d.lower()))
            return sum(
                math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
                * tf[w]
                * 2.2
                / (tf[w] + 1.2 * (0.25 + 0.75 * len(d) / avg))
                for w in q
            )

        for d in sorted(docs, key=score, reverse=True):
            if len(d) + 10 > left:
                break
            parts.append(d)
            left -= len(d) + 10
    return "\n\n".join(parts)


def ask_claude(prompt: str, tag: str, cache: Path = CACHE) -> dict[str, Any]:
    """One cached ``claude -p`` call (no tools, no MCP); returns {reply, cost, tokens, cached}."""
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{MODEL}\n{tag}\n{prompt}".encode()).hexdigest()[:24]
    p = cache / f"{tag}-{key}.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        return {**d, "cached": True}
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    empty = Path(tempfile.mkdtemp(prefix="l8-ask-", dir=os.environ.get("TMPDIR")))
    (empty / "mcp.json").write_text('{"mcpServers": {}}')
    t0 = time.time()
    r = subprocess.run(
        ["claude", "-p", "--model", MODEL, "--max-turns", "2", "--tools", "", "--strict-mcp-config", "--mcp-config",
         str(empty / "mcp.json"), "--output-format", "json", "--no-session-persistence"],
        input=prompt, capture_output=True, text=True, encoding="utf-8", cwd=str(empty), env=env, timeout=600,
    )  # fmt: skip
    try:
        res = json.loads(r.stdout)
    except json.JSONDecodeError:
        res = {"result": r.stdout[-2000:], "is_error": True, "stderr": r.stderr[-500:]}
    d = {"reply": res.get("result", ""), "cost": float(res.get("total_cost_usd") or 0), "usage": res.get("usage") or {},
         "is_error": bool(res.get("is_error")), "seconds": round(time.time() - t0, 1), "tag": tag}  # fmt: skip
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")
    return {**d, "cached": False}


def last_json(text: str) -> Any:
    for m in reversed(list(re.finditer(r"\{", text))):
        try:
            return json.loads(text[m.start() :].strip().rstrip("`").strip())
        except json.JSONDecodeError:
            continue
    return None


def reader_prompt(context: str, question: str, fmt: str) -> str:
    return (
        "You are answering a question about a software team's records. Everything is synthetic. Use only the records "
        "below; do not invent ids or names.\n\n=== RECORDS ===\n" + context + "\n=== END RECORDS ===\n\n"
        f"Question: {question}\nAnswer format: {fmt}\n"
        'Your reply must END with exactly one JSON object {"answer": ...} in that format, with nothing after it.'
    )


def answer_b0p(
    run_dir: Path, run: dict[str, Any], cstar: dict[str, Any] | None, probes: list[tuple[str, bool]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    hist = Path(run["workdir"]) / "history"
    calls, out = [], {}
    probe_txt = "\n".join(f"{i + 1}. {t}" for i, (t, _) in enumerate(probes))
    qs = {
        "Q1": (Q_TEXT["Q1"] + "\nAlso say, for each of these 10 decisions, whether it is one of them:\n" + probe_txt,
               '{"count": <number of such decisions>, "probes": [10 booleans in the order above], '
               '"earliest5": [sprint tags like "S01" of the 5 earliest such decisions, earliest first]}'),
        "Q3": (Q_TEXT["Q3"], '["<task id>", ...] (empty list if none)'),
    }  # fmt: skip
    if cstar:
        qs["Q2"] = (Q_TEXT["Q2"].format(old=", ".join(cstar["old"]), funcs=", ".join(cstar["funcs"]), k=cstar["k"]),
                    '["planner" | "researcher" | "builder", ...] (empty list if none)')  # fmt: skip
    for qid, (q, fmt) in qs.items():
        ctx = bm25_context(run_dir, hist, q)
        r = ask_claude(reader_prompt(ctx, q, fmt), f"b0p-{run['seed']}-{qid}")
        calls.append({k: v for k, v in r.items() if k != "reply"})
        ans = (last_json(r["reply"]) or {}).get("answer")
        if qid == "Q1":
            out[qid] = ans if isinstance(ans, dict) else {}
        else:
            out[qid] = sorted(str(x) for x in ans) if isinstance(ans, list) else None
    return out, calls


# ------------------------------------------------------------------------------------------------ one run
def audit_run(run_dir: Path, seed_dir: Path, host: str = "127.0.0.1", port: int = 6365) -> dict[str, Any]:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    sent = json.loads((seed_dir / "sentinels.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    evs = load_events(run_dir)
    probes = q1_probes(run["seed"])
    cstar = first_value_commit(run, sent)
    truth = {"Q1": q1_truth(evs), "Q2": q2_truth(evs, cstar) if cstar else None, "Q3": q3_truth(metrics)}
    calls: list[dict[str, Any]] = []
    if run["arm"] == "P":
        ans = answer_p(run["tenant"], host, port, cstar, probes)
    elif run["arm"] == "B1":
        ans = answer_b1(b1_db(run), cstar, probes)
    else:
        ans, calls = answer_b0p(run_dir, run, cstar, probes)
    q1 = q1_correct(ans.get("Q1") or {}, truth["Q1"], probes)
    res = {
        "Q1": {**q1, "truth_count": truth["Q1"]["count"], "answer": ans.get("Q1")},
        "Q2": {"truth": truth["Q2"], "answer": ans.get("Q2"), "correct": ans.get("Q2") == truth["Q2"], "cstar": cstar},
        "Q3": {"truth": truth["Q3"], "answer": ans.get("Q3"), "correct": ans.get("Q3") == truth["Q3"]},
        "reader_calls": calls,
    }  # fmt: skip
    res["score"] = sum(bool(res[q]["correct"]) for q in ("Q1", "Q2", "Q3"))
    (run_dir / "audit.json").write_text(
        json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    return res


# ------------------------------------------------------------------------------------------------ §6.9 probe
PROBE_Q = {
    "Q1": ("List the text of every decision that relies directly (BASED_ON / decision_facts) on a fact that derives "
           "(directly, or through other facts) from a source whose uri contains '02_api_style_guide_v1'. "
           "Return one column: the decision text."),
    "Q2": ("List the ids of the agents that read (a recall step that returned it) a fact whose value is in the "
           "parameter list `old`, at a step whose time is before the epoch-ms parameter `t`. Return one column: the "
           "agent id."),
    "Q3": ("List the ids of the tasks with status 'done' that have an artifact whose summary contains the value of a "
           "fact whose value starts with 'AX-' and which had already stopped being valid (its valid_to is at or before "
           "the task's done_at) when the task was done. Return one column: the task id."),
}  # fmt: skip


def probe_prompt(lang: str, schema: str, qid: str, error: str = "", previous: str = "") -> str:
    params = ("Parameters, if the question uses them, are passed as $old (a list of strings) and $t (an integer)."
              if lang == "cypher" else
              "Parameters, if the question uses them, are written as :t for the time and {old} where the list of "
              "values goes (the harness substitutes ?,?,... for {old}).")  # fmt: skip
    head = (f"You are given the schema of a {'FalkorDB graph (openCypher)' if lang == 'cypher' else 'SQLite database'}."
            f"\n\n=== SCHEMA ===\n{schema}\n=== END SCHEMA ===\n\nWrite ONE {'Cypher' if lang == 'cypher' else 'SQLite SQL'} "
            f"read-only statement that answers:\n{PROBE_Q[qid]}\n{params}\n")  # fmt: skip
    if error:
        head += f"\nYour previous statement was:\n{previous}\nIt failed or returned a wrong result: {error}\nFix it.\n"
    return head + "Reply with the statement only, inside one ```code block```."


def extract_stmt(reply: str) -> str:
    m = re.findall(r"```(?:\w+)?\s*\n(.*?)```", reply, re.S)
    return (m[-1] if m else reply).strip().rstrip(";")


def run_probe(seed_run_p: dict[str, Any], seed_run_b1: dict[str, Any], sent: dict[str, Any], host: str, port: int,
              reps: int = 3) -> dict[str, Any]:  # fmt: skip
    from plexus.crucible.backends.sqlite import SCHEMA as B1_DDL
    from plexus.graph.client import GraphClient
    from plexus.graph.tenancy import graph_name

    doc = (Path(__file__).resolve().parents[5] / "docs" / "graph-model.md").read_text(encoding="utf-8")
    gc = GraphClient(host=host, port=port)
    g = gc.graph(graph_name(seed_run_p["tenant"]))
    db = sqlite3.connect(str(b1_db(seed_run_b1)))
    cs_p = first_value_commit(seed_run_p, sent)
    cs_b = first_value_commit(seed_run_b1, sent)

    def run_c(stmt: str) -> list[Any]:
        return sorted(
            {
                str(r[0])
                for r in g.ro_query(stmt, {"old": cs_p["old"], "t": cs_p["t_ms"]}, timeout=5000).result_set
            }
        )

    def run_s(stmt: str) -> list[Any]:
        q = stmt.replace("{old}", ",".join("?" for _ in cs_b["old"]))
        args = [*cs_b["old"]] if "{old}" in stmt else []
        if ":t" in q:
            q = q.replace(":t", "?")
            args.append(cs_b["t_ms"])
        db.set_progress_handler(None, 0)
        t0 = time.time()
        db.set_progress_handler(lambda: 1 if time.time() - t0 > 5 else 0, 10000)
        return sorted({str(r[0]) for r in db.execute(q, args).fetchall()})

    ref = {
        "cypher": {"Q1": run_c(CYPHER["Q1"]), "Q2": run_c(CYPHER["Q2"]), "Q3": run_c(CYPHER["Q3"])},
        "sql": {"Q1": run_s(SQL["Q1"]), "Q2": run_s(SQL["Q2"]), "Q3": run_s(SQL["Q3"])},
    }
    rows = []
    for lang, schema, runner in (("cypher", doc, run_c), ("sql", B1_DDL, run_s)):
        for qid in ("Q1", "Q2", "Q3"):
            for rep in range(1, reps + 1):
                stmt, err, iters, calls, exact, defects = "", "", 0, [], False, []
                for it in range(0, 4):
                    r = ask_claude(
                        probe_prompt(lang, schema, qid, err, stmt), f"probe-{lang}-{qid}-r{rep}-i{it}"
                    )
                    calls.append({k: v for k, v in r.items() if k != "reply"})
                    stmt = extract_stmt(r["reply"])
                    try:
                        got = runner(stmt)
                    except Exception as exc:  # noqa: BLE001
                        err = f"{type(exc).__name__}: {str(exc)[:300]}"
                        defects.append("error")
                        iters = it
                        continue
                    if got == ref[lang][qid]:
                        exact, iters = True, it
                        break
                    err = f"wrong result ({len(got)} rows; expected a different set)"
                    defects.append("wrong")
                    iters = it
                rows.append({"lang": lang, "q": qid, "rep": rep, "first_try_exact": exact and iters == 0, "exact": exact,
                             "fix_iterations": iters, "defects": defects, "lines": len([x for x in stmt.splitlines() if x.strip()]),
                             "statement": stmt, "cost": round(sum(c["cost"] for c in calls if not c.get("cached")), 4),
                             "cost_incl_cached": round(sum(c["cost"] for c in calls), 4)})  # fmt: skip
    gc.close()
    db.close()
    return {
        "reference_counts": {lang: {q: len(v) for q, v in d.items()} for lang, d in ref.items()},
        "rows": rows,
    }
