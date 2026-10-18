"""Concurrency: many agents (threads, each with its own connection) racing for the same tasks."""

from __future__ import annotations

import threading
import time
from collections import Counter

from knewat.graph.client import GraphClient
from knewat.relay import Relay
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


def test_dag_workers_never_run_a_task_before_its_dependencies(relay, client, graph, library):
    """Layered DAG, 20 workers: no task starts before every task of the previous layer has ended."""
    layers, width = 5, 12
    tasks = []
    for layer in range(layers):
        for k in range(width):
            deps = [f"L{layer - 1}-{j}" for j in range(width)] if layer else []
            tasks.append({"id": f"L{layer}-{k}", "title": "x", "depends_on": deps, "priority": layer})
    relay.create_tasks(tasks)
    n_workers = 20
    for i in range(n_workers):
        relay.register_agent(f"agent-{i:02d}", f"A{i}", "builder", "thread")

    lock = threading.Lock()
    events: list[tuple[str, str]] = []  # ("start"|"end", task id) in real time
    remaining = {"n": layers * width}

    def work(r: Relay, agent: str) -> int:
        n = 0
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            got = r.claim_next_task(agent, LEASE)
            if got is None:
                with lock:
                    if remaining["n"] == 0:
                        return n
                time.sleep(0.005)
                continue
            with lock:
                events.append(("start", got["id"]))
            with lock:
                events.append(("end", got["id"]))  # work is instantaneous; completion follows
            r.complete_task(agent, got["id"], got["version"])
            with lock:
                remaining["n"] -= 1
            n += 1
        raise TimeoutError("workers did not finish")

    results, errors, secs = _race(library, graph, n_workers, work)
    assert not errors, errors[:3]
    assert sum(results.values()) == layers * width
    started = [t for kind, t in events if kind == "start"]
    assert len(started) == len(set(started)) == layers * width  # each task started exactly once
    st = client.graph(graph).ro_query("MATCH (t:Task) RETURN t.status, count(t)").result_set
    assert st == [["done", layers * width]]
    # Graph invariant: no task finished before one of its dependencies.
    bad = (
        client.graph(graph)
        .ro_query("MATCH (t:Task)-[:DEPENDS_ON]->(d:Task) WHERE d.done_at > t.done_at RETURN count(*)")
        .result_set[0][0]
    )
    assert bad == 0
    # Real-time order: 'end' is logged before complete_task, so a layer-n task can only start after
    # every layer-(n-1) task has been completed in the graph.
    pos_end = {t: i for i, (kind, t) in enumerate(events) if kind == "end"}
    for i, (kind, t) in enumerate(events):
        if kind == "start" and not t.startswith("L0-"):
            layer = int(t[1 : t.index("-")])
            assert all(pos_end.get(f"L{layer - 1}-{j}", 10**9) < i for j in range(width)), t


def test_many_agents_racing_to_reclaim_one_expired_task_yield_one_winner(
    relay, client, graph, library, clock
):
    relay.register_agent("dead", "dead", "builder", "thread")
    relay.create_tasks([{"id": "t1", "title": "orphan"}])
    assert relay.claim_next_task("dead", 1_000, now=1_000)["id"] == "t1"
    n = 30
    for i in range(n):
        relay.register_agent(f"agent-{i:02d}", f"A{i}", "builder", "thread")

    def once(r: Relay, agent: str):
        return r.claim_next_task(agent, LEASE, now=50_000)  # far past the dead agent's lease

    results, errors, _ = _race(library, graph, n, once)
    assert not errors, errors[:3]
    winners = [a for a, got in results.items() if got is not None]
    assert len(winners) == 1
    assert results[winners[0]]["reclaimed_from"] == "dead" and results[winners[0]]["version"] == 2
    edges = client.graph(graph).ro_query("MATCH (a)-[c:CLAIMED]->(:Task {id:'t1'}) RETURN a.id").result_set
    assert sorted(r[0] for r in edges) == sorted(["dead", winners[0]])
