"""P9-f: ``blocked_by_failure`` (and so ``impact(kind='task')``) reads ONE snapshot under concurrent writes.

It walked the dependency DAG with one statement per BFS level, the reader that tore in Crucible L6-E.
Here a writer adds, in ONE statement, a task ``a`` that depends on the root (level 1) and a task ``b`` that
depends on the deepest task of a chain (level 9). In any snapshot both are blocked by the root, or neither:
**T1** the a-ids and the b-ids in an answer are the same set. **T2** the answer never shrinks.
"""

from __future__ import annotations

from plexus.relay import Relay
from tests.lineage.test_p9f_snapshot_reads import _race

CHAIN = 8

PAIR = (
    "MATCH (r:Task {id: 'root'}) MATCH (d:Task {id: $deep}) "
    "CREATE (a:Task {id: $a, title: $a, status: 'open', priority: 0, version: 0, created_at: 1}) "
    "CREATE (b:Task {id: $b, title: $b, status: 'open', priority: 0, version: 0, created_at: 1}) "
    "CREATE (a)-[:DEPENDS_ON]->(r) CREATE (b)-[:DEPENDS_ON]->(d)"
)


def test_blocked_by_failure_reads_one_snapshot_under_concurrent_writes(client, graph, clock):
    relay = Relay(client, graph, clock=clock)
    ids = ["root"] + [f"T{i}" for i in range(1, CHAIN + 1)]
    relay.create_tasks([{"id": "root", "title": "root"}])
    for prev, cur in zip(ids, ids[1:], strict=False):
        relay.create_tasks([{"id": cur, "title": cur, "depends_on": [prev]}])
    assert relay.blocked_by_failure("root") == ids[1:]

    def write(k: int) -> None:
        client.graph(graph).query(PAIR, {"deep": ids[-1], "a": f"a{k:05d}", "b": f"b{k:05d}"})

    def read(state: dict[str, int]) -> dict[str, int]:
        got = relay.blocked_by_failure("root")
        a = {i[1:] for i in got if i[0] == "a"}
        b = {i[1:] for i in got if i[0] == "b"}
        bad = {"t1": int(a != b), "t2": int(len(got) < state.get("n", 0))}
        state["n"] = len(got)
        return bad

    out = _race(4, read, write)
    assert out["reads"] >= 20 and out["writes"] >= 50, out
    assert out.get("t1", 0) == 0 and out.get("t2", 0) == 0, out
