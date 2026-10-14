"""Concurrency: many agents (threads, each with its own connection) racing for the same tasks."""

from __future__ import annotations

import threading
import time
from collections import Counter

from plexus.graph.client import GraphClient
from plexus.relay import Relay
from tests.conftest import TEST_DB_HOST, TEST_DB_PORT

N_THREADS = 50
N_TASKS = 200
LEASE = 600_000  # nothing may expire during the test


def _race(library, graph, n_threads, claim_loop):
    """Start n_threads, release them together, return ({agent: result}, errors, seconds)."""
    results: dict[str, object] = {}
    errors: list[BaseException] = []
    barrier = threading.Barrier(n_threads)

    def worker(i: int):
        agent = f"agent-{i:02d}"
        c = GraphClient(host=TEST_DB_HOST, port=TEST_DB_PORT, password="", library=library)
        try:
            relay = Relay(c, graph)
            barrier.wait(timeout=60)
            results[agent] = claim_loop(relay, agent)
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assertions below
            errors.append(exc)
        finally:
            c.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=240)
    return results, errors, time.perf_counter() - t0


def test_50_threads_claim_200_tasks_with_zero_double_claims(relay, client, graph, library, capsys):
    for i in range(N_THREADS):
        relay.register_agent(f"agent-{i:02d}", f"Agent {i}", "builder", "thread")
    relay.create_tasks([{"id": f"t{i:03d}", "title": f"task {i}", "priority": i % 5} for i in range(N_TASKS)])

    def claim_loop(r: Relay, agent: str) -> list[str]:
        mine = []
        while (got := r.claim_next_task(agent, LEASE)) is not None:
            mine.append(got["id"])
        return mine

    results, errors, secs = _race(library, graph, N_THREADS, claim_loop)
    assert not errors, errors[:3]
    assert len(results) == N_THREADS

    claimed = [tid for ids in results.values() for tid in ids]
    dupes = {t: n for t, n in Counter(claimed).items() if n > 1}
    assert dupes == {}, f"double claims: {dupes}"
    assert sorted(claimed) == [f"t{i:03d}" for i in range(N_TASKS)]

    # The graph agrees: exactly one CLAIMED edge per task, claimed_by matches the edge, version == 1.
    rows = (
        client.graph(graph)
        .ro_query(
            "MATCH (t:Task) OPTIONAL MATCH (a:Agent)-[c:CLAIMED]->(t) "
            "RETURN t.id, count(c), collect(a.id), t.claimed_by, t.version"
        )
        .result_set
    )
    assert len(rows) == N_TASKS
    for tid, n_edges, agents, claimed_by, version in rows:
        assert n_edges == 1 and agents == [claimed_by] and version == 1, (tid, n_edges, agents)
    total_edges = client.graph(graph).ro_query("MATCH ()-[c:CLAIMED]->() RETURN count(c)").result_set[0][0]
    assert total_edges == N_TASKS

    per_agent = sorted(len(v) for v in results.values())
    with capsys.disabled():
        print(
            f"\n[relay concurrency] {N_THREADS} threads x {N_TASKS} tasks: {secs:.2f}s wall, "
            f"{(N_TASKS + N_THREADS) / secs:.0f} claim calls/s (incl. {N_THREADS} empty), "
            f"0 double claims, tasks/agent min={per_agent[0]} max={per_agent[-1]}"
        )
