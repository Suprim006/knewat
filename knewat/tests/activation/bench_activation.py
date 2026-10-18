"""Benchmark for ``activation/activation`` (spec P7-K slice 3): 10k facts, each with up to 50 READ edges.

Run:  PLEXUS_TEST_DB_PORT=6392 uv run python -m tests.activation.bench_activation [facts] [reads_per_fact]
Prints the server-side ``run_time_ms`` (FalkorDB's own timing, not the Docker port-forward time) for 50 ids.
"""

from __future__ import annotations

import os
import random
import statistics
import sys
import time
import uuid

from plexus.activation import Activation, Settings
from plexus.graph.client import GraphClient
from plexus.graph.queries import QueryLibrary
from plexus.graph.schema import apply_schema

DAY = 86_400_000
NOW = 5_000 * DAY


def build(client: GraphClient, graph: str, facts: int, reads: int, steps: int = 500) -> list[str]:
    g = client.graph(graph)
    ids = [str(uuid.uuid4()) for _ in range(facts)]
    g.query(
        "UNWIND range(0, $n - 1) AS i "
        "CREATE (:Step {id: 'st' + toString(i), agent_id: 'bench', n: i, at: $now - i * 1000})",
        {"n": steps, "now": NOW},
    )
    g.query("CREATE (:Agent {id: 'bench'})")
    rng = random.Random(7)
    for lo in range(0, facts, 500):
        chunk = ids[lo : lo + 500]
        g.query(
            "UNWIND $rows AS row CREATE (:Fact {id: row.id, status: 'active', "
            "created_at: $now - row.age, surprise: 0.2, "
            "predicate: 'p', value: 'v', valid_from: 0, valid_to: 9999999999999})",
            {"rows": [{"id": i, "age": rng.randrange(DAY, 90 * DAY)} for i in chunk], "now": NOW},
        )
    for lo in range(0, facts, 100):
        chunk = ids[lo : lo + 100]
        pairs = [
            {"f": fid, "s": f"st{s}", "via": rng.choice(["use", "recall", "recall"])}
            for fid in chunk
            for s in rng.sample(range(steps), min(reads, steps))
        ]
        g.query(
            "UNWIND $pairs AS p MATCH (f:Fact {id: p.f}), (s:Step {id: p.s}) "
            "CREATE (s)-[:READ {via: p.via, at: s.at}]->(f)",
            {"pairs": pairs},
        )
    return ids


def main() -> None:
    facts = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    reads = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    port = int(os.environ.get("PLEXUS_TEST_DB_PORT", "6392"))
    client = GraphClient(host="127.0.0.1", port=port, password="", library=QueryLibrary())
    graph = f"test_bench_{uuid.uuid4().hex[:8]}"
    try:
        apply_schema(client, graph)
        t0 = time.time()
        ids = build(client, graph, facts, reads)
        print(f"built {facts} facts x {reads} READ edges in {time.time() - t0:.1f}s")
        act = Activation(client, graph, Settings(), clock=lambda: NOW)
        rng = random.Random(1)
        server_ms, wall_ms = [], []
        for _ in range(30):
            sample = rng.sample(ids, 50)
            t = time.perf_counter()
            rows = client.ro(graph, "activation/activation", {"fact_ids": sample, "now": NOW, "events": 50})
            wall_ms.append((time.perf_counter() - t) * 1000)
            server_ms.append(rows.run_time_ms)
            assert len(rows) == 50
        full = act.compute(rng.sample(ids, 50))
        print(f"events per fact (first of sample): {len(next(iter(full.values())).events)}")
        print(
            f"activation for 50 ids: server run_time_ms median {statistics.median(server_ms):.1f}, "
            f"p95 {sorted(server_ms)[int(0.95 * len(server_ms)) - 1]:.1f}, max {max(server_ms):.1f}; "
            f"client wall median {statistics.median(wall_ms):.1f} ms (includes the Docker port forward)"
        )
    finally:
        client.delete_graph(graph)
        client.close()


if __name__ == "__main__":
    main()
