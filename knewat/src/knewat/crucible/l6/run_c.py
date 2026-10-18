"""L6-C runner: multi-hop recall through ``RELATES`` (BASELINE.md §5.4 pre-registration, Part 2). No LLM.

    python -m knewat.crucible.l6.run_c --host 127.0.0.1 --port 6313 --scale 1.0 --out knewat/demo_data/crucible/l6

Writes ``<out>/<stamp>-c/results.json`` and ``<out>/latest-c.json`` (the envelope of the other L6 runs).
"""

from __future__ import annotations

import argparse
import shutil
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from knewat.crucible.l6 import arms_a as A
from knewat.crucible.l6 import arms_c as C
from knewat.crucible.l6 import run as R
from knewat.crucible.l6 import stores_c as S
from knewat.crucible.l6 import world_c as W
from knewat.crucible.util import percentile
from knewat.embed import get_embedder
from knewat.engram.service import Engram
from knewat.graph.client import GraphClient

ARMS = ("B1h", "B1h-untuned", "P-tuned", "P-product", "P-flat")
REPS = R.REPS
Fn = Callable[[W.QuestionC], tuple[dict[str, Any], dict[str, Any]]]


def _stat(xs: list[float]) -> dict[str, float]:
    return {
        "p50": round(percentile(xs, 50), 2), "p99": round(percentile(xs, 99), 2),
        "mean": round(statistics.fmean(xs), 2) if xs else 0.0,
    }  # fmt: skip


def _summ(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n": len(rows), "strict": sum(r["strict"] for r in rows), "hit5": sum(r["hit5"] for r in rows),
        "hit_any": sum(r["hit_any"] for r in rows),
        "top5_equal_expected": sum(r["top5_equal_expected"] for r in rows),
        "timeouts": sum(R.is_timeout(r["error"]) for r in rows),
        "other_errors": sum(bool(r["error"]) and not R.is_timeout(r["error"]) for r in rows),
        "not_answerable": sum(r["not_answerable"] for r in rows),
        "latency_ms": _stat([r["latency_ms"] for r in rows]),
        "server_ms": {k: v for k, v in _stat([r["server_ms"] for r in rows]).items() if k != "mean"},
        "statements": {"mean": round(statistics.fmean([r["statements"] for r in rows]), 2) if rows else 0.0},
    }  # fmt: skip


def measure_c(arm: str, qs: list[W.QuestionC], fn: Fn, reps: int = REPS) -> dict[str, Any]:
    """Each question ``reps`` times: the first answer is scored, the latency is the median (a timeout counts 5,000 ms)."""
    rows = []
    none = {"strict": False, "hit5": False, "top5_equal": False, "hit_any": False}
    for q in qs:
        lats, servers, first = [], [], None
        for r in range(reps):
            got, m = fn(q)
            lats.append(A.TIMEOUT_MS if R.is_timeout(m["error"]) else m["latency_ms"])
            servers.append(m["server_ms"])
            if r == 0:
                first = (got, m)
        got, m = first  # type: ignore[misc]
        sc = none if m["error"] else C.score(q, got)
        rows.append({
            "id": q.id, "depth": q.depth, "stage": q.stage, "strict": sc["strict"], "hit5": sc["hit5"],
            "top5_equal_expected": sc["top5_equal"], "hit_any": sc["hit_any"],
            "latency_ms": round(statistics.median(lats), 2), "server_ms": round(statistics.median(servers), 3),
            "statements": m["statements"], "error": m["error"], "not_answerable": m.get("not_answerable", False),
            "top5": got.get("top5", []),
        })  # fmt: skip
    by_depth = {str(d): _summ([r for r in rows if r["depth"] == d]) for d in W.DEPTHS}
    return {"arm": arm, "n": len(rows), "by_depth": by_depth, "all": _summ(rows), "questions": rows}


def det_c(
    client: GraphClient,
    tmp: Path,
    log: Callable[[str], None],
    scale: float = 1.0,
    arms: set[str] | None = None,
    embedder_kind: str = "hash",
) -> dict[str, Any]:
    """``embedder_kind`` is ``hash`` in the registered run; ``fastembed`` is the labelled post-hoc re-run of the
    product arms (the hash embedder ties and collides on two-word names, see BASELINE)."""
    arms = set(ARMS) if arms is None else arms
    embedder = get_embedder(embedder_kind)
    t = time.time()
    world = W.generate(scale=scale)
    qs = world.questions
    log(
        f"C: world {world.counts()} generated in {time.time() - t:.1f}s; cost_matters {world.meta['cost_matters_share']}"
    )
    fns: dict[str, Fn] = {}
    timing: dict[str, float] = {}
    if arms & {"B1h", "B1h-untuned"}:
        t = time.time()
        if "B1h" in arms:
            fns["B1h"] = C.SqlC(S.build_sqlite_c(world, tmp / "c_tuned.db", tuned=True)[0]).answer
        if "B1h-untuned" in arms:
            fns["B1h-untuned"] = C.SqlC(S.build_sqlite_c(world, tmp / "c_untuned.db", tuned=False)[0]).answer
        timing["sqlite_load_s"] = round(time.time() - t, 2)
    name = ""
    try:
        if arms & {"P-tuned", "P-product", "P-flat"}:
            t = time.time()
            name, counts = S.load_knewat_c(world, client, "l6c_run", embedder)
            timing["knewat_load_s"] = round(time.time() - t, 2)
            log(f"C: Knewat graph loaded in {timing['knewat_load_s']}s: {counts}")
            if "P-tuned" in arms:
                fns["P-tuned"] = C.TunedC(client.graph(name)).answer
            for nm, hops in (("P-product", None), ("P-flat", 0)):
                if nm in arms:
                    eng = Engram(C.RecordingClient(client), name, embedder)  # type: ignore[arg-type]
                    fns[nm] = C.ProductC(eng, world.scope_id, hops).answer
        out = {nm: measure_c(nm, qs, fns[nm]) for nm in ARMS if nm in fns}
    finally:
        if name:
            client.delete_graph(name)
    for nm, v in out.items():
        bd = v["by_depth"]
        log(
            f"C {nm}: strict {[bd[str(d)]['strict'] for d in W.DEPTHS]} of {[bd[str(d)]['n'] for d in W.DEPTHS]}, "
            f"p50 {v['all']['latency_ms']['p50']} ms, timeouts {v['all']['timeouts']}"
        )
    pairs: dict[str, Any] = {}
    if "P-tuned" in out and "B1h" in out:
        a = {r["id"]: r["top5"] for r in out["P-tuned"]["questions"]}
        b = {r["id"]: r["top5"] for r in out["B1h"]["questions"]}
        pairs["P-tuned_vs_B1h_identical_top5"] = {
            str(d): sum(a[q.id] == b[q.id] for q in qs if q.depth == d) for d in W.DEPTHS
        } | {"n": {str(d): sum(q.depth == d for q in qs) for d in W.DEPTHS}}
    return {
        "world": {"counts": world.counts(), "meta": world.meta}, "timing": timing,
        "embedder": type(embedder).__name__, "arms": out, "pairs": pairs,
        "query_lines": {
            "B1h": R.loc(C.SqlC), "B1h_sql": C.sql_lines(), "P-tuned": R.loc(C.TunedC),
            "P-tuned_cypher": C.cypher_lines(), "P-product": R.loc(C.ProductC),
        },
        "questions": [
            {"id": q.id, "depth": q.depth, "stage": q.stage, "anchor_id": q.anchor_id, "predicate": q.predicate,
             "text": q.text, "answer_fact_id": q.answer_fact_id, "cost_matters": q.cost_matters,
             "n_candidates": q.n_candidates, "expected_top5": q.expected_top5}
            for q in qs
        ],
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l6-c")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6361)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--out", type=Path, default=R.DEMO)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--embedder", choices=("hash", "fastembed"), default="hash")
    ap.add_argument(
        "--tag", default="", help="suffix of the result directory (e.g. fastembed for the post-hoc run)"
    )
    a = ap.parse_args(argv)
    log: Callable[[str], None] = lambda s: print(s, flush=True)  # noqa: E731
    started = time.time()
    cmd = "python -m knewat.crucible.l6.run_c " + " ".join(argv if argv is not None else sys.argv[1:])
    wanted = set(a.arms.split(","))
    if wanted - set(ARMS):
        ap.error(f"unknown arms {sorted(wanted - set(ARMS))}; choose from {list(ARMS)}")
    client = GraphClient(host=a.host, port=a.port)
    tmp = Path(tempfile.mkdtemp(prefix="crucible-l6c-"))
    try:
        doc = R.envelope("c", a.host, a.port, started, cmd)
        doc["environment"]["embedder"] = a.embedder
        doc["config"] = {
            "scale": a.scale,
            "arms": sorted(wanted),
            "reps": REPS,
            "seed": W.SEED,
            "embedder": a.embedder,
            "tag": a.tag,
        }
        doc["families"] = {"C": det_c(client, tmp, log, a.scale, wanted, a.embedder)}
        if a.tag:
            doc["run"]["id"] += f"-{a.tag}"
        d = R.write(doc, a.out)
        print(f"results: {d / 'results.json'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
