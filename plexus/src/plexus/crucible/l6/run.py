"""L6 runner: deterministic arms (A, A-dag, B, D), concurrency (E), crash-consistency (F) and the combined L6 layer.

    python -m plexus.crucible.l6.run det    --port 6361          # A, A-dag, B, D: P-naive/P-anchored/P-tuned/B1h/B1h-untuned/P-pre
    python -m plexus.crucible.l6.run conc   --port 6361 --runs 10 --seconds 6
    python -m plexus.crucible.l6.run crash  --port 6361 --kills 200
    python -m plexus.crucible.l6.run layer                         # merge the latest of each into demo_data/crucible/l6/latest.json

Every command writes ``demo_data/crucible/l6/<stamp>-<kind>/results.json`` and a ``latest-<kind>.json`` copy. A result
records the git commit and whether the tree was dirty. No LLM is called here (the pilot is ``l6.pilot``).
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from plexus.crucible import environment
from plexus.crucible.l6 import arms_a as A
from plexus.crucible.l6 import arms_b as B
from plexus.crucible.l6 import arms_d as D
from plexus.crucible.l6 import conc, crash
from plexus.crucible.l6 import score as SC
from plexus.crucible.l6 import stores as S
from plexus.crucible.l6 import world as W
from plexus.crucible.util import iso_utc, percentile, run_stamp
from plexus.graph.client import GraphClient

PKG = Path(__file__).resolve()
DEMO = PKG.parents[5] / "demo_data" / "crucible" / "l6"
REPS = 3


def sign_test(b: int, c: int) -> float:
    """Exact two-sided sign test on b vs c discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return round(min(1.0, 2 * p), 4)


def git_state() -> dict[str, Any]:
    def g(*a: str) -> str:
        return subprocess.run(
            ["git", *a], capture_output=True, text=True, cwd=PKG.parent, timeout=20
        ).stdout.strip()

    return {
        "commit": g("rev-parse", "HEAD"),
        "short": g("rev-parse", "--short", "HEAD"),
        "dirty": bool(g("status", "--porcelain", "--", ".")),
        "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
    }


# ------------------------------------------------------------------------------------------------ measuring one arm
def measure(
    arm: str,
    family: str,
    qs: list[Any],
    fn: Callable[[Any], tuple[Any, dict[str, Any]]],
    *,
    template: Callable[[Any], str] = lambda q: "",
    reps: int = REPS,
) -> dict[str, Any]:
    rows = []
    for q in qs:
        lats, servers, first = [], [], None
        for r in range(reps):
            got, m = fn(q)
            lats.append(A.TIMEOUT_MS if m["error"] == "timeout" else m["latency_ms"])
            servers.append(m["server_ms"])
            if r == 0:
                first = (got, m)
        got, m = first  # type: ignore[misc]
        if m["error"]:
            strict, comp = False, {}
        else:
            strict, comp = SC.score(family, q.answer, got, template(q))
        rows.append({
            "id": q.id, "strict": strict, "components": comp, "error": m["error"], "statements": m["statements"],
            "latency_ms_median": round(statistics.median(lats), 2), "latency_ms_all": [round(x, 2) for x in lats],
            "server_ms_median": round(statistics.median(servers), 3),
            "expected": q.answer if not strict else None, "got": (json.dumps(got, default=str)[:300] if not strict else None),
        })  # fmt: skip
    return summarise(arm, rows)


def summarise(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    lat = [x for r in rows for x in r["latency_ms_all"]]
    comps: dict[str, int] = {}
    for r in rows:
        for k, v in r["components"].items():
            comps[k] = comps.get(k, 0) + int(v)
    return {
        "arm": arm, "n": len(rows), "strict_correct": sum(r["strict"] for r in rows),
        "timeouts": sum(r["error"] == "timeout" for r in rows), "other_errors": sum(bool(r["error"]) and r["error"] != "timeout" for r in rows),
        "components_correct": comps,
        "latency_ms": {"p50": round(percentile(lat, 50), 2), "p99": round(percentile(lat, 99), 2), "max": round(max(lat), 2) if lat else 0},
        "server_ms_median": round(statistics.median([r["server_ms_median"] for r in rows]), 3) if rows else 0,
        "statements_per_answer_median": statistics.median([r["statements"] for r in rows]) if rows else 0,
        "questions": rows,
    }  # fmt: skip


def paired(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    x = {r["id"]: r["strict"] for r in a["questions"]}
    y = {r["id"]: r["strict"] for r in b["questions"]}
    only_a = sum(1 for i in x if x[i] and not y.get(i, False))
    only_b = sum(1 for i in y if y[i] and not x.get(i, False))
    return {
        "a": a["arm"],
        "b": b["arm"],
        "only_a_right": only_a,
        "only_b_right": only_b,
        "both_right": sum(1 for i in x if x[i] and y.get(i)),
        "p_two_sided": sign_test(only_a, only_b),
    }


def loc(obj: Any) -> int:
    return sum(
        1
        for ln in inspect.getsource(obj).splitlines()
        if ln.strip() and not ln.strip().startswith(("#", '"""'))
    )


# ------------------------------------------------------------------------------------------------ the families
def det_a(client: GraphClient, tmp: Path, log: Callable[[str], None], scale: float = 1.0) -> dict[str, Any]:
    t = time.time()
    w, qs = W.gen_a(scale)
    log(f"A: world {w.counts()} generated in {time.time() - t:.1f}s")
    p_tuned, c1 = S.build_sqlite(w, tmp, "a_tuned", tuned=True)
    p_untuned, c2 = S.build_sqlite(w, tmp, "a_untuned", tuned=False)
    name, c3 = S.load_plexus(w, client, "l6_a")
    g = client.graph(name)
    arms: dict[str, Callable[[Any], tuple[Any, dict[str, Any]]]] = {
        "B1h": A.SqlArm(p_tuned).blast, "B1h-untuned": A.SqlArm(p_untuned, tuned=False).blast,
        "P-tuned": A.TunedArm(g).blast, "P-anchored": A.AnchoredArm(g).blast, "P-naive": A.NaiveArm(g).blast,
    }  # fmt: skip
    out = {nm: measure(nm, "A", qs, fn) for nm, fn in arms.items()}
    for nm, v in out.items():
        log(
            f"A {nm}: {v['strict_correct']}/{v['n']} strict, {v['timeouts']} timeouts, p50 {v['latency_ms']['p50']} ms, p99 {v['latency_ms']['p99']} ms"
        )
    plans = {
        "B1h_explain_A12": A.SqlArm(p_tuned).explain(qs[11]),
        "B1h_untuned_explain_A12": A.SqlArm(p_untuned, tuned=False).explain(qs[11]),
    }
    plans["P-tuned_level_explain"] = str(g.explain(A.TunedArm.LEVEL, {"frontier": ["f000001"]}))
    plans["P-naive_facts_explain"] = str(
        g.explain(
            "MATCH (:Source {id: $s})<-[:DERIVED_FROM*1..12]-(f:Fact) RETURN count(DISTINCT f)",
            {"s": qs[0].source},
        )
    )
    plans["P-anchored_facts_explain"] = str(
        g.explain(
            "MATCH (s:Source {id: $s}) MATCH (s)<-[:DERIVED_FROM*1..12]-(f:Fact) WITH DISTINCT f RETURN count(f)",
            {"s": qs[0].source},
        )
    )
    client.delete_graph(name)
    return {
        "world": w.counts(), "loader_counts_checked": True, "arms": out,
        "pairs_vs_B1h": [paired(out["B1h"], out[n]) for n in out if n != "B1h"],
        "plans": plans, "query_lines": {"B1h": loc(A.SqlArm), "P-tuned": loc(A.TunedArm), "P-naive": loc(A.NaiveArm), "P-anchored": loc(A.AnchoredArm)},
        "questions": [{"id": q.id, "blast": q.blast, "depth": q.depth, "source": q.source} for q in qs],
    }  # fmt: skip


def det_dag(client: GraphClient, tmp: Path, log: Callable[[str], None]) -> dict[str, Any]:
    from plexus.relay.service import Relay

    rows: dict[str, list[dict[str, Any]]] = {}
    for layers in (8, 12, 16, 20, 24):
        w, q = W.gen_dag(layers)
        path, _ = S.build_sqlite(w, tmp, f"dag{layers}")
        name, _ = S.load_plexus(w, client, f"l6_dag{layers}")
        g = client.graph(name)
        relay = Relay(client, name)

        def product(_q: Any, relay: Any = relay, probes: list[str] = q.probes) -> tuple[Any, dict[str, Any]]:
            t0 = time.perf_counter()
            ids = sorted(relay.blocked_by_failure("root"))
            return {
                "tasks": len(ids),
                "probes": [p in set(ids) for p in q.probes],
                "first5": ids[:5],
            }, A.meta(t0, 0, 1 + len(ids) // 1000)

        sq = A.SqlArm(path)
        fns: dict[str, Callable[[Any], tuple[Any, dict[str, Any]]]] = {
            "B1h": sq.dag, "B1h-UNION-ALL": lambda x, sq=sq: sq.dag(x, union_all=True),
            "P-naive": A.NaiveArm(g).dag, "P-tuned": A.TunedArm(g).dag, "P-product(blocked_by_failure)": product,
        }  # fmt: skip
        for nm, fn in fns.items():
            r = measure(nm, "dag", [q], fn)
            if (
                nm == "B1h-UNION-ALL" and not r["questions"][0]["error"]
            ):  # count-only arm: compared on the count
                ans, _ = fn(q)
                r["questions"][0]["strict"] = ans["tasks"] == q.answer["tasks"]
                r["strict_correct"] = int(r["questions"][0]["strict"])
            rows.setdefault(nm, []).append({"layers": layers, "tasks": len(w.tasks), **r["questions"][0]})
            log(
                f"A-dag L={layers} {nm}: strict={r['questions'][0]['strict']} err={r['questions'][0]['error']} p50={r['latency_ms']['p50']} ms"
            )
        client.delete_graph(name)
    return {
        "arms": {
            nm: {
                "sizes": v,
                "strict_correct": sum(x["strict"] for x in v),
                "n": len(v),
                "timeouts": sum(x["error"] == "timeout" for x in v),
            }
            for nm, v in rows.items()
        }
    }


def det_b(client: GraphClient, tmp: Path, log: Callable[[str], None], scale: float = 1.0) -> dict[str, Any]:
    from plexus.lineage.service import Lineage

    w, qs = W.gen_b(scale)
    path, _ = S.build_sqlite(w, tmp, "b")
    name, _ = S.load_plexus(w, client, "l6_b")
    g = client.graph(name)
    arms: dict[str, Callable[[Any], tuple[Any, dict[str, Any]]]] = {
        "B1h": B.SqlB(path).answer, "P-tuned": B.TunedB(g).answer, "P-naive": B.NaiveB(g).answer,
        "P-pre(why@5191976)": B.ProductWhyB(Lineage(client, name)).answer,
    }  # fmt: skip
    out = {nm: measure(nm, "B", qs, fn) for nm, fn in arms.items()}
    by_depth = {}
    for nm, v in out.items():
        by_depth[nm] = {
            d: sum(r["strict"] for r, q in zip(v["questions"], qs, strict=True) if q.depth == d)
            for d in W.CHAIN_DEPTHS
        }
        log(f"B {nm}: {v['strict_correct']}/{v['n']}; by depth {by_depth[nm]}")
    client.delete_graph(name)
    return {
        "world": w.counts(),
        "arms": out,
        "correct_by_depth_of_4": by_depth,
        "pairs_vs_B1h": [paired(out["B1h"], out[n]) for n in out if n != "B1h"],
        "query_lines": {"B1h": loc(B.SqlB), "P-tuned": loc(B.TunedB), "P-naive": loc(B.NaiveB)},
    }


def det_d(client: GraphClient, tmp: Path, log: Callable[[str], None], scale: float = 1.0) -> dict[str, Any]:
    w, qs = W.gen_d(scale)
    path, _ = S.build_sqlite(w, tmp, "d")
    name, _ = S.load_plexus(w, client, "l6_d")
    g = client.graph(name)
    out = {
        "B1h": measure("B1h", "D", qs, D.SqlD(path).answer, template=lambda q: q.template),
        "P": measure("P", "D", qs, D.CypherD(g).answer, template=lambda q: q.template),
    }  # fmt: skip
    for nm, v in out.items():
        log(f"D {nm}: {v['strict_correct']}/{v['n']}, p50 {v['latency_ms']['p50']} ms")
    client.delete_graph(name)
    return {
        "world": w.counts(),
        "world_meta": w.meta,
        "arms": out,
        "pairs_vs_B1h": [paired(out["B1h"], out["P"])],
        "shared_source_k": {q.id: q.k for q in qs if q.template == "shared_sources"},
    }


# ------------------------------------------------------------------------------------------------ envelope
def envelope(kind: str, host: str, port: int, started: float, command: str) -> dict[str, Any]:
    return {
        "schema": "crucible-l6/1", "kind": kind, "run": {"id": run_stamp() + f"-{kind}", "started_at": iso_utc(started), "finished_at": "", "command": command, "llm_calls": 0, "cost_usd": 0.0},
        "git": git_state(), "environment": environment.collect(host, port, "none"),
    }  # fmt: skip


def write(doc: dict[str, Any], out: Path) -> Path:
    doc["run"]["finished_at"] = iso_utc()
    d = out / doc["run"]["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(
        json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    shutil.copyfile(d / "results.json", out / f"latest-{doc['kind']}.json")
    return d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l6")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("det", "conc", "crash", "layer"):
        p = sub.add_parser(name)
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=6361)
        p.add_argument("--out", type=Path, default=DEMO)
        p.add_argument("--scale", type=float, default=1.0)
    sub.choices["det"].add_argument("--families", default="A,dag,B,D")
    sub.choices["conc"].add_argument("--runs", type=int, default=10)
    sub.choices["conc"].add_argument("--seconds", type=float, default=6.0)
    sub.choices["crash"].add_argument("--kills", type=int, default=200)
    sub.choices["crash"].add_argument("--arms", default="B1h,P,B0")
    a = ap.parse_args(argv)
    log: Callable[[str], None] = lambda s: print(s, flush=True)  # noqa: E731
    started = time.time()
    cmd = "python -m plexus.crucible.l6.run " + " ".join(argv if argv is not None else sys.argv[1:])
    if a.cmd == "layer":
        print(json.dumps(build_layer(a.out), indent=1)[:2000])
        return 0
    client = GraphClient(host=a.host, port=a.port)
    tmp = Path(tempfile.mkdtemp(prefix="crucible-l6-"))
    try:
        if a.cmd == "det":
            doc = envelope("det", a.host, a.port, started, cmd)
            fams = set(a.families.split(","))
            res: dict[str, Any] = {}
            if "A" in fams:
                res["A"] = det_a(client, tmp, log, a.scale)
            if "dag" in fams:
                res["A_dag"] = det_dag(client, tmp, log)
            if "B" in fams:
                res["B"] = det_b(client, tmp, log, a.scale)
            if "D" in fams:
                res["D"] = det_d(client, tmp, log, a.scale)
            doc["families"] = res
        elif a.cmd == "conc":
            doc = envelope("conc", a.host, a.port, started, cmd)
            doc["config"] = {
                "runs": a.runs,
                "seconds": a.seconds,
                "appenders": 4,
                "quarantiner_every_s": 0.25,
                "readers": 8,
                "scale": a.scale,
            }
            doc["families"] = {
                "E": conc.run_all(runs=a.runs, seconds=a.seconds, scale=a.scale, client=client, log=log)
            }
        else:
            doc = envelope("crash", a.host, a.port, started, cmd)
            doc["config"] = {
                "kills_per_arm": a.kills,
                "delay_ms": [0, 400],
                "seed": 20261016,
                "embedder": "hash",
            }
            res = {}
            for arm in a.arms.split(","):
                root = tempfile.mkdtemp(prefix="l6f-")
                tenant = f"l6f_{arm.lower()}_{int(time.time()) % 100000}"
                res[arm] = crash.kill_loop(arm, a.kills, root, tenant, a.host, a.port, 20261016, log=log)
                if arm == "P":
                    from plexus.graph.tenancy import graph_name

                    client.delete_graph(graph_name(tenant))
                shutil.rmtree(root, ignore_errors=True)
                log(
                    f"F {arm}: orphans {res[arm]['orphans']}, missing derived {res[arm]['missing_derived_from']}, lost {res[arm]['lost_acknowledged_total']}"
                )
            doc["families"] = {"F": res}
        d = write(doc, a.out)
        print(f"results: {d / 'results.json'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        client.close()
    return 0


def build_layer(root: Path) -> dict[str, Any]:
    """Merge the latest deterministic, concurrency, crash and pilot results into one L6 layer dict."""
    layer: dict[str, Any] = {"title": "Beat-SQL families (pre-registered)", "families": {}, "sources": {}}
    for kind in ("det", "conc", "crash", "pilot"):
        p = root / f"latest-{kind}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        layer["sources"][kind] = {"run": d["run"]["id"], "git": d.get("git", {})}
        for fam, v in d.get("families", {}).items():
            layer["families"].setdefault(fam, {})[kind] = v
        if kind == "pilot":
            layer["pilot"] = {k: d[k] for k in d if k not in ("schema", "kind", "environment", "families")}
    return layer


if __name__ == "__main__":
    sys.exit(main())
