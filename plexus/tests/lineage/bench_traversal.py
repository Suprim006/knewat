"""P9-b bench: path-enumerating vs level-wise traversal on diamond DAGs (server-side ``run_time_ms``).

    PLEXUS_TEST_DB_PORT=63NN uv run python -m tests.lineage.bench_traversal [--old-queries DIR]

``--old-queries`` = a ``queries/`` directory of the base commit
(``git archive <sha> plexus/queries | tar -x -C X``); the old forget_source / quarantine / why_edges are timed
from it. The ``*1..N`` rows run the natural path-enumerating
pattern (what Cypher users write) with a 3 s timeout and show the explosion the level-wise forms avoid.
"""

from __future__ import annotations

import argparse
import statistics
import uuid

from plexus.graph.client import GraphClient
from plexus.graph.queries import QueryLibrary
from plexus.graph.schema import apply_schema
from plexus.lineage import Lineage
from plexus.relay import Relay
from tests.conftest import TEST_DB_HOST, TEST_DB_PORT
from tests.lineage.diamond import TimedClient, build_lineage, build_tasks

REPS = 7
NOISE = 5000  # unrelated tasks (one long chain) added around the diamond DAG


def med(xs: list[float]) -> float:
    return round(statistics.median(xs), 1)


def timed_query(g, q: str, params: dict, timeout: int = 3000):
    try:
        r = g.ro_query(q, params, timeout=timeout)
        return r.run_time_ms, len(r.result_set)
    except Exception as exc:  # noqa: BLE001 - timeouts are the point
        return None, str(exc)[:40]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-queries")
    args = ap.parse_args()
    lib = QueryLibrary()
    c = GraphClient(host=TEST_DB_HOST, port=TEST_DB_PORT, password="", library=lib)
    old = None
    if args.old_queries:
        old = GraphClient(
            host=TEST_DB_HOST, port=TEST_DB_PORT, password="", library=QueryLibrary(args.old_queries)
        )
    name = f"test_bench_{uuid.uuid4().hex[:8]}"
    apply_schema(c, name)
    try:
        # ---- tasks: 145 tasks / 8 levels / fan-in 3 ----
        tc = TimedClient(c)
        relay = Relay(tc, name)
        build_tasks(relay, levels=8, width=18, fan_in=3)
        g = c.graph(name)
        tc.reset()
        times = []
        for _ in range(REPS):
            tc.reset()
            relay.blocked_by_failure("root")
            times.append(tc.server_ms)
        print(f"tasks 145/8/3  blocked_by_failure (level-wise, {tc.calls} calls): server {med(times)} ms")
        for n in (8, 12, 20):
            ms, rows = timed_query(
                g, f"MATCH (t:Task)-[:DEPENDS_ON*1..{n}]->(:Task {{id: 'root'}}) RETURN DISTINCT t.id", {}
            )
            print(f"tasks 145/8/3  path-enumerating *1..{n}: server {ms} ms  rows/err={rows}")

        # ---- tasks in a big graph: each BFS level must cost the frontier, not the graph ----
        for lo in range(0, NOISE, 500):
            g.query(
                "UNWIND range($lo, $lo + 499) AS i "
                "CREATE (:Task {id: 'N' + toString(i), status: 'open', title: 'n'})",
                {"lo": lo},
            )
        for lo in range(1, NOISE, 500):
            g.query(
                "UNWIND range($lo, $lo + 499) AS i MATCH (a:Task {id: 'N' + toString(i)}), "
                "(b:Task {id: 'N' + toString(i - 1)}) CREATE (a)-[:DEPENDS_ON]->(b)",
                {"lo": lo},
            )
        for who, cl in (("NEW", c), ("OLD", old)):
            if cl is None:
                continue
            tn = TimedClient(cl)
            rn = Relay(tn, name)
            times = []
            for _ in range(REPS):
                tn.reset()
                got = rn.blocked_by_failure("root")
                times.append(tn.server_ms)
            print(
                f"tasks 145/8/3 + {NOISE} noise: blocked_by_failure with {who} relay/dependents_of: "
                f"server {med(times)} ms over {tn.calls} calls, {len(got)} tasks"
            )

        # ---- lineage: depth 12 fan-in 3 ----
        d = build_lineage(c, name, levels=12, width=5, fan_in=3)
        for n in (4, 6, 8, 10, 12):
            ms, rows = timed_query(
                g,
                f"MATCH (s:Source {{id: $id}}) MATCH (s)<-[:DERIVED_FROM*1..{n}]-(f:Fact) "
                "RETURN DISTINCT f.id",
                {"id": d["source"]},
            )
            print(f"lineage 12/5/3 path-enumerating *1..{n} from the source: server {ms} ms  rows/err={rows}")
        tl = TimedClient(c)
        lin = Lineage(tl, name)
        why_t = []
        for _ in range(REPS):
            tl.reset()
            lin.why(d["decision"], max_elements=2000, depth=12)
            why_t.append(tl.server_ms)
        print(f"lineage 12/5/3 why(depth=12, {tl.calls} calls): server {med(why_t)} ms")
        if old is not None:
            og = old.graph(name)
            ms = []
            for _ in range(REPS):
                r = old.ro(name, "lineage/why_edges", {"id": d["decision"], "limit": 2000})
                ms.append(r.run_time_ms)
            print(f"lineage 12/5/3 OLD why_edges (*1..3 paths): server {med(ms)} ms, {len(r)} rows")
            del og
        for label, fn in (
            (
                "forget_source",
                lambda cl, **kw: cl.rw(
                    name,
                    "lineage/forget_source",
                    {
                        "source_id": d["source"],
                        "now": 5,
                        "limit": 5000,
                        "reason": "r",
                        "max_detail": 500,
                        **kw,
                    },
                ),
            ),
            (
                "quarantine",
                lambda cl, **kw: cl.rw(
                    name,
                    "lineage/quarantine",
                    {"source_id": d["source"], "now": 5, "limit": 5000, "max_detail": 500, **kw},
                ),
            ),
        ):
            for who, cl, kw in (
                ("NEW depth=12", c, {"depth": 12}),
                ("NEW depth=8", c, {"depth": 8}),
                ("OLD (5 hops)", old, {}),
            ):
                if cl is None:
                    continue
                ms = []
                for _ in range(REPS):
                    g.query(
                        "MATCH (f:Fact) SET f.status = 'active', f.valid_to = 9999999999999 "
                        "REMOVE f.prior_status"
                    )
                    r = fn(cl, **kw)
                    ms.append(r.run_time_ms)
                print(
                    f"lineage 12/5/3 {label} {who}: server {med(ms)} ms, "
                    f"facts changed={len(r[0]['fact_ids'])}"
                )
    finally:
        c.delete_graph(name)
        c.close()
        if old is not None:
            old.close()


if __name__ == "__main__":
    main()
