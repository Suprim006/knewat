"""Crucible L7 family H: query expressiveness and traversal, Cypher (FalkorDB) vs SQL (SQLite), hand-written.

    python -m plexus.crucible.l7.h run --port 6367 --scale {dev,full} [--out DIR]

Every query text is a file in ``l7/h_queries/`` (lines are counted from it). The application-side BFS used by the
``*-bfs`` arms is :func:`bfs`, the same function for both backends (only the per-level statement differs); its
lines are counted from its source. Each question runs 5 times (the first answer is scored; a timeout is not
repeated and counts 10,000 ms for all repetitions). Ground truth: :class:`plexus.crucible.l7.h_world.Truth`.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sqlite3
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from falkordb import FalkorDB

from plexus.crucible.l7 import common as C
from plexus.crucible.l7.h_stores import CYPHER_INDEXES, SQL_INDEXES, build_sqlite, load_falkordb
from plexus.crucible.l7.h_world import H3_MAX_HOPS, HWorld, Truth, h_world

QDIR = Path(__file__).resolve().parent / "h_queries"
REPS = 5
SCALES = {"dev": ("small", "medium"), "full": ("small", "large"), "toy": ("toy",)}


def qtext(name: str) -> str:
    return (QDIR / name).read_text(encoding="utf-8")


def unbounded_cypher(text: str) -> str:
    """The same statement with the hop bound removed (``*1..8`` -> ``*1..``): what an author who does not know
    the path length writes."""
    return text.replace(f"*1..{H3_MAX_HOPS}]", "*1..]")


def unbounded_sql(text: str) -> str:
    return text.replace(f"r.depth < {H3_MAX_HOPS} AND ", "")


# ------------------------------------------------------------------------------------------------ executors
class FRunner:
    def __init__(self, g: Any):
        self.g = g

    def run(self, cypher: str, params: dict[str, Any]) -> tuple[list[list[Any]], float]:
        res = self.g.ro_query(cypher, params, timeout=C.TIMEOUT_MS)
        return res.result_set, float(res.run_time_ms)


class SRunner:
    def __init__(self, path: Path):
        self.c = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.c.execute("PRAGMA query_only=1")
        self.arm = C.sqlite_deadline(self.c)

    def run(self, sql: str, params: dict[str, Any]) -> tuple[list[tuple[Any, ...]], float]:
        self.arm()
        t = time.perf_counter()
        rows = self.c.execute(sql, params).fetchall()
        return rows, (time.perf_counter() - t) * 1000


def _is_timeout(exc: Exception) -> bool:
    m = str(exc).lower()
    return "interrupted" in m or "timed out" in m or "timeout" in m


def bfs(level: Callable[[list[str]], list[tuple[str, str, str]]], a: str, b: str) -> list[str] | None:
    """Application-side BFS for H3: ``level(frontier)`` returns (node, parent, parent_status) rows (one statement).

    Expands ``a`` and active intermediate facts only, stops at the first level that reaches ``b`` and rebuilds the
    path from the predecessor map. Unbounded (it stops when the frontier is empty).
    """
    pred: dict[str, str | None] = {a: None}
    frontier = [a]
    while frontier:
        nxt: list[str] = []
        for p, q, status in level(frontier):
            if q in pred:
                continue
            pred[q] = p
            if q == b:
                path = [b]
                while pred[path[-1]] is not None:
                    path.append(pred[path[-1]])  # type: ignore[arg-type]
                return path[::-1]
            if status == "active":
                nxt.append(q)
        frontier = nxt
    return None


BFS_LINES = C.code_lines(inspect.getsource(bfs).split('"""')[0] + inspect.getsource(bfs).split('"""')[2])


# ------------------------------------------------------------------------------------------------ arms
def _pack_f(rows: list[list[Any]]) -> dict[str, Any]:
    n, first = rows[0]
    return {"count": int(n), "first5": [list(x) for x in first]}


def _pack_s(rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    n, first = rows[0]
    return {"count": int(n), "first5": json.loads(first) if first else []}


def build_arms(fr: FRunner, sr: SRunner) -> dict[str, dict[str, Any]]:
    """name -> {family, lang, files, statements_note, fn(question)->(answer, server_ms, statements)}."""
    arms: dict[str, dict[str, Any]] = {}

    def one(fam: str, lang: str, file: str, pack: Callable, text: str | None = None, note: str = "") -> None:
        q = text if text is not None else qtext(file)
        runner = fr if lang == "cypher" else sr

        def fn(question: dict[str, Any], q: str = q, runner: Any = runner) -> tuple[Any, float, int]:
            params = dict(question.get("params", {}))
            qq = q.replace("{N}", str(params.pop("N"))) if "{N}" in q else q
            rows, server = runner.run(qq, params)
            return pack(rows), server, 1

        arms[f"{fam}:{lang}:{file}{note}"] = {"family": fam, "lang": lang, "file": file, "lines": C.code_lines(q),
                                              "variant": note or "", "fn": fn}  # fmt: skip

    for fam in ("H1a", "H1b", "H1c", "H2"):
        one(fam, "cypher", f"{fam.lower()}.cypher", _pack_f)
        one(fam, "sql", f"{fam.lower()}.sql", _pack_s)
    one("H1c", "cypher", "h1c.natural.cypher", _pack_f)  # the first form written: FalkorDB answers it wrongly

    def h4_f(rows: list[list[Any]]) -> list[list[Any]]:
        return [[r[0], int(r[1])] for r in rows]

    one("H4", "cypher", "h4.naive.cypher", h4_f)
    one("H4", "cypher", "h4.distinct.cypher", h4_f)
    one("H4", "cypher", "h4.bfs.cypher", h4_f)
    one("H4", "sql", "h4.sql", lambda rows: [[r[0], int(r[1])] for r in rows])

    # H3
    def path_f(rows: list[list[Any]]) -> dict[str, Any]:
        p = rows[0][0] if rows else None
        return {"path": list(p) if p is not None else None}

    def path_s(rows: list[tuple[Any, ...]]) -> dict[str, Any]:
        p = rows[0][0] if rows else None
        return {"path": [x for x in p.split(",") if x] if p else None}

    def depth_s(rows: list[tuple[Any, ...]]) -> dict[str, Any]:
        d = rows[0][0] if rows else None
        return {"hops": int(d) if d is not None else None}

    vl = qtext("h3.varlen.cypher")
    one("H3", "cypher", "h3.varlen.cypher", path_f)
    one("H3", "cypher", "h3.varlen.cypher", path_f, unbounded_cypher(vl), "+unbounded")
    one("H3", "cypher", "h3.shortestpath.cypher", path_f)
    pc = qtext("h3.path_cte.sql")
    one("H3", "sql", "h3.path_cte.sql", path_s)
    one("H3", "sql", "h3.path_cte.sql", path_s, unbounded_sql(pc), "+unbounded")
    one("H3", "sql", "h3.depth_cte.sql", depth_s)

    for lang, runner in (("cypher", fr), ("sql", sr)):
        file = f"h3.bfs_level.{lang}"
        text = qtext(file)

        def fn(question: dict[str, Any], text: str = text, runner: Any = runner, lang: str = lang) -> tuple:
            calls = {"n": 0, "server": 0.0}

            def level(frontier: list[str]) -> list[tuple[str, str, str]]:
                calls["n"] += 1
                params = {"frontier": frontier} if lang == "cypher" else {"frontier": json.dumps(frontier)}
                rows, server = runner.run(text, params)
                calls["server"] += server
                return [tuple(r) for r in rows]

            p = bfs(level, question["params"]["a"], question["params"]["b"])
            return {"path": p}, calls["server"], calls["n"]

        arms[f"H3:{lang}:{file}+app-bfs"] = {"family": "H3", "lang": lang, "file": file,
                                             "lines": C.code_lines(text), "app_lines": BFS_LINES,
                                             "variant": "+app-bfs", "fn": fn}  # fmt: skip
    return arms


# ------------------------------------------------------------------------------------------------ questions
def questions(w: HWorld, t: Truth) -> list[dict[str, Any]]:
    qs: list[dict[str, Any]] = [
        {"id": "H1a", "family": "H1a", "params": {}, "truth": t.h1a()},
        {"id": "H1b", "family": "H1b", "params": {}, "truth": t.h1b()},
        {"id": "H1c", "family": "H1c", "params": {}, "truth": t.h1c()},
        {"id": "H4", "family": "H4", "params": {}, "truth": t.h4()},
    ]
    for nh in (0, 2, 4):
        for a in w.h2_agents[nh]:
            qs.append({"id": f"H2-N{nh}-{a}", "family": "H2", "params": {"agent": a, "N": nh, "n": nh},
                       "truth": t.h2(a, nh)})  # fmt: skip
    for p in w.h3_pairs:
        qs.append({"id": p["id"], "family": "H3", "kind": p["kind"], "params": {"a": p["a"], "b": p["b"]},
                   "truth": t.h3(p["a"], p["b"])})  # fmt: skip
    return qs


def score(q: dict[str, Any], got: Any, t: Truth) -> tuple[bool, dict[str, bool]]:
    if q["family"] == "H3":
        want = q["truth"]
        if "hops" in got:
            return got["hops"] == want, {"hops": got["hops"] == want}
        p = got["path"]
        hops = None if p is None else len(p) - 1
        valid = p is None or t.h3_valid_path(p, q["params"]["a"], q["params"]["b"])
        return hops == want and valid, {"hops": hops == want, "valid_path": valid}
    if q["family"] == "H4":
        return got == q["truth"], {"top10": got == q["truth"]}
    c = got["count"] == q["truth"]["count"]
    f = got["first5"] == q["truth"]["first5"]
    return c and f, {"count": c, "first5": f}


def measure(arm: dict[str, Any], qs: list[dict[str, Any]], t: Truth, reps: int = REPS) -> dict[str, Any]:
    rows = []
    for q in qs:
        if q["family"] != arm["family"]:
            continue
        lats, servers, first, err, stmts = [], [], None, "", 0
        for r in range(reps):
            t0 = time.perf_counter()
            try:
                got, server, stmts = arm["fn"](q)
            except (
                Exception
            ) as exc:  # timeout or a query the engine rejects: a wrong answer, reported as such
                err = "timeout" if _is_timeout(exc) else f"{type(exc).__name__}: {str(exc)[:200]}"
                lats += [float(C.TIMEOUT_MS) if err == "timeout" else (time.perf_counter() - t0) * 1000] * (
                    reps - r
                )
                break
            lats.append((time.perf_counter() - t0) * 1000)
            servers.append(server)
            if r == 0:
                first = got
        if err and first is None:
            strict, comp = False, {}
        else:
            strict, comp = score(q, first, t)
        rows.append({
            "id": q["id"], "kind": q.get("kind"), "strict": strict, "components": comp, "error": err,
            "statements": stmts, "latency_ms": [round(x, 3) for x in lats],
            "server_ms": [round(x, 3) for x in servers],
            "expected": None if strict else q["truth"], "got": None if strict else json.dumps(first, default=str)[:400],
        })  # fmt: skip
    lat = [x for r in rows for x in r["latency_ms"]]
    return {
        "arm": arm["name"], "family": arm["family"], "lang": arm["lang"], "file": arm["file"],
        "variant": arm["variant"], "lines": arm["lines"], "app_lines": arm.get("app_lines", 0),
        "n": len(rows), "strict_correct": sum(r["strict"] for r in rows),
        "timeouts": sum(r["error"] == "timeout" for r in rows),
        "other_errors": sum(bool(r["error"]) and r["error"] != "timeout" for r in rows),
        "statements_max": max((r["statements"] for r in rows), default=0),
        "latency": C.lat_summary(lat), "questions": rows,
    }  # fmt: skip


# ------------------------------------------------------------------------------------------------ run
def run_scale(scale: str, host: str, port: int, tmp: Path, log: Callable[[str], None]) -> dict[str, Any]:
    t0 = time.time()
    w = h_world(scale)
    truth = Truth(w)
    qs = questions(w, truth)
    log(f"[{scale}] world {w.counts()} truth+questions {time.time() - t0:.1f} s")
    db = FalkorDB(host=host, port=port)
    gname = f"l7h_{scale}"
    try:
        db.select_graph(gname).delete()
    except Exception:
        pass
    g = db.select_graph(gname)
    t1 = time.time()
    fcounts = load_falkordb(w, g)
    f_load = time.time() - t1
    t1 = time.time()
    spath = tmp / f"h_{scale}.db"
    scounts = build_sqlite(w, spath)
    s_load = time.time() - t1
    log(f"[{scale}] loaded FalkorDB {f_load:.1f} s, SQLite {s_load:.1f} s")
    sr = SRunner(spath)
    arms = build_arms(FRunner(g), sr)
    out = []
    for name, arm in arms.items():
        arm["name"] = name
        t1 = time.time()
        res = measure(arm, qs, truth)
        out.append(res)
        log(f"[{scale}] {name}: {res['strict_correct']}/{res['n']} timeouts {res['timeouts']} "
            f"err {res['other_errors']} p50 {res['latency']['p50']} ms ({time.time() - t1:.1f} s)")  # fmt: skip
    g.delete()
    sr.c.close()
    return {
        "scale": scale, "counts": w.counts(), "store_counts": {"falkordb": fcounts, "sqlite": scounts},
        "load_s": {"falkordb": round(f_load, 2), "sqlite": round(s_load, 2)},
        "questions": [{k: q[k] for k in ("id", "family", "params", "truth") if k in q} | {"kind": q.get("kind")}
                      for q in qs],
        "arms": out,
    }  # fmt: skip


def report(doc: dict[str, Any]) -> str:
    L = [f"# Crucible L7 family H: expressiveness and traversal ({doc['run']['id']})", ""]
    L.append("SQLite = embedded (in-process); FalkorDB = server (Docker port-forward). Lines = non-blank non-comment "
             "lines of the statement file; app lines = Python BFS lines (for `+app-bfs`).")  # fmt: skip
    L.append("")
    for sc in doc["scales"]:
        L += [f"## scale {sc['scale']}: {sc['counts']}", ""]
        L.append(
            "| question | arm | lines | app lines | statements (max) | strict | timeouts | errors | p50 ms | p99 ms |"
        )
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for a in sc["arms"]:
            L.append(f"| {a['family']} | {a['lang']} {a['file']}{a['variant']} | {a['lines']} | {a['app_lines']} | "
                     f"{a['statements_max']} | {a['strict_correct']}/{a['n']} | {a['timeouts']} | {a['other_errors']} | "
                     f"{a['latency']['p50']} | {a['latency']['p99']} |")  # fmt: skip
        L.append("")
        for a in sc["arms"]:
            bad = [q for q in a["questions"] if not q["strict"]]
            if bad:
                L.append(f"* {a['arm']}: wrong on " + ", ".join(
                    f"{q['id']}({q['kind'] or ''}{'; ' + q['error'][:60] if q['error'] else ''})" for q in bad[:14]))  # fmt: skip
        L.append("")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l7-h")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--host", default=C.DEFAULT_HOST)
    r.add_argument("--port", type=int, required=True)
    r.add_argument("--scale", choices=sorted(SCALES), default="dev")
    r.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    started = time.time()
    doc = C.envelope(
        "h", a.host, a.port, started, " ".join(["python -m plexus.crucible.l7.h", *sys.argv[1:]])
    )
    doc["indexes"] = {"sqlite": list(SQL_INDEXES), "falkordb": list(CYPHER_INDEXES)}
    doc["reps"] = REPS
    doc["h3_max_hops_bounded"] = H3_MAX_HOPS
    doc["bfs_app_lines"] = BFS_LINES
    doc["scales"] = []
    with tempfile.TemporaryDirectory(prefix="l7h-", ignore_cleanup_errors=True) as td:
        for sc in SCALES[a.scale]:
            doc["scales"].append(run_scale(sc, a.host, a.port, Path(td), lambda m: print(m, flush=True)))
    d = C.write(doc, a.out, report(doc))
    print(f"wrote {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
