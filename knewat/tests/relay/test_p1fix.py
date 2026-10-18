"""P1-fix regression tests for Relay (review findings P1-05, 06, 07, 09, 11e, 12)."""

from __future__ import annotations

import threading
import time

import pytest

import plexus.relay.service as rsvc
from plexus.graph.client import GraphClient
from plexus.relay import ClaimConflict, DuplicateTask, Relay, UnknownReference
from tests.conftest import TEST_DB_HOST, TEST_DB_PORT

LEASE = 100_000


def _agents(relay, *names):
    for n in names:
        relay.register_agent(n, n.upper(), "builder", "test")


# -- P1-05: heartbeat only extends -----------------------------------------------------------------


def test_heartbeat_never_shortens_the_lease(relay, clock):
    _agents(relay, "a1")
    relay.create_tasks([{"id": "t1", "title": "one"}])
    claimed = relay.claim_next_task("a1", LEASE)
    assert claimed["lease_until"] == clock.t + LEASE
    assert relay.heartbeat("a1", "t1", lease_ms=10, now=clock.t + 1) is True  # smaller lease: no-op
    assert relay.task_status("t1")["lease_until"] == clock.t + LEASE
    assert relay.heartbeat("a1", "t1", lease_ms=10, now=clock.t - 500) is True  # older `now`: no-op
    assert relay.task_status("t1")["lease_until"] == clock.t + LEASE
    assert relay.heartbeat("a1", "t1", lease_ms=LEASE, now=clock.t + 50_000) is True  # real extension
    assert relay.task_status("t1")["lease_until"] == clock.t + 50_000 + LEASE


# -- P1-06: blocked_by_failure on wide DAGs --------------------------------------------------------


def _layered(relay, layers: int, width: int):
    relay.create_tasks([{"id": "root", "title": "root"}])
    prev = ["root"]
    for layer in range(layers):
        ids = [f"L{layer}-{i}" for i in range(width)]
        relay.create_tasks([{"id": t, "title": t, "depends_on": prev} for t in ids])
        prev = ids
    return prev


def test_blocked_by_failure_on_wide_diamond_dag_is_fast_and_complete(relay):
    _layered(relay, layers=10, width=8)  # 8**10 distinct paths; 80 distinct tasks
    t0 = time.perf_counter()
    got = relay.blocked_by_failure("root")
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, elapsed
    assert len(got) == 80 and len(set(got)) == 80
    assert got[:8] == [f"L0-{i}" for i in range(8)]  # nearest first, then by id
    assert got[-8:] == [f"L9-{i}" for i in range(8)]


def test_blocked_by_failure_depth_is_an_optional_bound(relay):
    _layered(relay, layers=12, width=1)
    assert relay.blocked_by_failure("root", depth=10) == [f"L{i}-0" for i in range(10)]
    assert relay.blocked_by_failure("root") == [f"L{i}-0" for i in range(12)]  # default 50 (was 10)


def test_blocked_by_failure_node_cap(relay, monkeypatch):
    _layered(relay, layers=3, width=5)
    monkeypatch.setattr(rsvc, "MAX_BLOCKED_NODES", 7)
    assert len(relay.blocked_by_failure("root")) == 7


# -- P1-07: VERIFIED_BY.independent is persisted ---------------------------------------------------


def test_verified_by_edge_persists_independence(relay, client, graph):
    _agents(relay, "producer", "reviewer")
    relay.create_tasks([{"id": "t1", "title": "one"}])
    relay.claim_next_task("producer", LEASE)
    done = relay.complete_task("producer", "t1", 1, [{"id": "x1", "kind": "doc", "uri": "file://x"}])
    assert relay.verify_artifact("producer", "x1")["independent"] is False
    assert relay.verify_artifact("reviewer", "x1")["independent"] is True
    rows = (
        client.graph(graph)
        .ro_query(
            "MATCH (:Artifact {id:'x1'})-[v:VERIFIED_BY]->(a:Agent) RETURN a.id, v.independent ORDER BY a.id"
        )
        .result_set
    )
    assert [list(r) for r in rows] == [["producer", False], ["reviewer", True]]
    assert done["artifact_ids"] == ["x1"]


# -- P1-09: Artifact -[:FOR]-> Task ----------------------------------------------------------------


@pytest.mark.parametrize("outcome", ["complete", "fail"])
def test_artifacts_link_to_their_task_with_a_for_edge(relay, client, graph, outcome):
    _agents(relay, "a1")
    relay.create_tasks([{"id": "t1", "title": "one"}])
    relay.claim_next_task("a1", LEASE)
    arts = [{"id": "x1", "kind": "doc", "uri": "u1"}, {"id": "x2", "kind": "doc", "uri": "u2"}]
    if outcome == "complete":
        relay.complete_task("a1", "t1", 1, arts)
    else:
        relay.fail_task("a1", "t1", 1, arts, reason="boom")
    rows = (
        client.graph(graph)
        .ro_query("MATCH (x:Artifact)-[:FOR]->(t:Task) RETURN x.id, t.id, x.task_id")
        .result_set
    )
    assert sorted(list(r) for r in rows) == [["x1", "t1", "t1"], ["x2", "t1", "t1"]]


def test_unfinished_task_keeps_done_at_zero(relay):
    relay.create_tasks([{"id": "t1", "title": "one"}])
    assert relay.task_status("t1")["done_at"] == 0


# -- P1-12: reopen + FIFO tie-break ----------------------------------------------------------------


def test_same_priority_tasks_in_one_batch_are_claimed_in_input_order(relay):
    _agents(relay, "a1")
    relay.create_tasks(
        [{"id": i, "title": i} for i in ["z", "m", "a", "q"]]
    )  # ids sort differently from input
    order = []
    for _ in range(4):
        got = relay.claim_next_task("a1", LEASE)
        order.append(got["id"])
    assert order == ["z", "m", "a", "q"]
    relay.create_tasks([{"id": i, "title": i} for i in ["y", "b"]])
    assert [t["id"] for t in relay.ready_tasks()] == ["y", "b"]


def test_reopen_failed_task_makes_it_claimable_again(relay, clock):
    _agents(relay, "a1", "a2")
    relay.create_tasks([{"id": "t1", "title": "one"}, {"id": "t2", "title": "two", "depends_on": ["t1"]}])
    got = relay.claim_next_task("a1", LEASE)
    relay.fail_task("a1", "t1", got["version"], reason="flaky")
    assert relay.claim_next_task("a2", LEASE) is None  # t2 blocked by the failure
    assert relay.blocked_by_failure("t1") == ["t2"]
    clock.advance(5)
    out = relay.reopen_task("a2", "t1")
    st = relay.task_status("t1")
    assert out == {"id": "t1", "status": "open", "version": got["version"] + 2}
    assert (st["status"], st["claimed_by"], st["lease_until"], st["done_at"]) == ("open", "", 0, 0)
    again = relay.claim_next_task("a2", LEASE)
    assert again["id"] == "t1" and again["version"] == got["version"] + 3
    relay.complete_task("a2", "t1", again["version"])
    assert relay.claim_next_task("a2", LEASE)["id"] == "t2"


def test_reopen_rejects_non_failed_and_unknown(relay):
    _agents(relay, "a1")
    relay.create_tasks([{"id": "t1", "title": "one"}])
    with pytest.raises(ClaimConflict, match="not failed"):
        relay.reopen_task("a1", "t1")
    with pytest.raises(UnknownReference) as exc:
        relay.reopen_task("a1", "ghost")
    assert exc.value.kind == "task"
    with pytest.raises(UnknownReference) as exc:
        relay.reopen_task("ghost-agent", "t1")
    assert exc.value.kind == "agent"
    assert relay.task_status("t1")["status"] == "open" and relay.task_status("t1")["version"] == 0


def test_stale_holder_cannot_complete_after_reopen_and_reclaim(relay):
    _agents(relay, "a1", "a2")
    relay.create_tasks([{"id": "t1", "title": "one"}])
    first = relay.claim_next_task("a1", LEASE)
    relay.fail_task("a1", "t1", first["version"])
    relay.reopen_task("a2", "t1")
    second = relay.claim_next_task("a2", LEASE)
    with pytest.raises(ClaimConflict):
        relay.complete_task("a1", "t1", first["version"])
    relay.complete_task("a2", "t1", second["version"])


# -- P1-11e: concurrent create_tasks ---------------------------------------------------------------


def test_concurrent_create_tasks_with_the_same_ids_has_exactly_one_winner(relay, client, graph, library):
    n = 12
    barrier = threading.Barrier(n)
    outcomes: list[object] = []
    lock = threading.Lock()

    def worker(i: int):
        c = GraphClient(host=TEST_DB_HOST, port=TEST_DB_PORT, password="", library=library)
        try:
            r = Relay(c, graph)
            barrier.wait(timeout=30)
            try:
                res = r.create_tasks(
                    [{"id": "t-a", "title": f"a{i}"}, {"id": "t-b", "title": f"b{i}", "depends_on": ["t-a"]}]
                )
            except DuplicateTask as exc:
                res = exc
            with lock:
                outcomes.append(res)
        finally:
            c.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for o in outcomes if o == ["t-a", "t-b"]) == 1
    assert sum(1 for o in outcomes if isinstance(o, DuplicateTask)) == n - 1
    g = client.graph(graph)
    assert g.ro_query("MATCH (t:Task) RETURN count(t)").result_set == [[2]]
    assert g.ro_query("MATCH ()-[d:DEPENDS_ON]->() RETURN count(d)").result_set == [[1]]
