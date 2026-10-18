"""P9-f: ``why`` and ``impact`` read ONE snapshot while writers append and a quarantiner flips a tree.

Modelled on Crucible L6-E (consistent reads under concurrent writes). There, a reader that issues one
statement per hop (``P-levelwise``, what ``Lineage.why`` did) tore 917 times in 4,470 reads, and the
single-statement read (``P-1stmt``) never did. Here the product's own calls are the readers:

* ``why(D)``: a writer adds, in ONE statement, a fact ``x`` that the deepest chain fact derives from AND a
  ``BASED_ON`` edge from the decision ``D`` to ``x``. In any snapshot both edges exist or neither does.
  **W1**: the pair facts reached through ``BASED_ON`` equal those reached through ``DERIVED_FROM``.
  **W2**: the chain facts (all derived from ``R``, which a quarantiner flips) show one status, never a mix.
* ``impact(source)``: a writer adds, in ONE statement, a fact derived from a chain fact and a decision on it.
  **I1**: (decisions - initial decisions) == (facts - initial facts). **I2**: the totals never decrease.
"""

from __future__ import annotations

import threading
import time

from plexus.lineage import Lineage

FAR = 9_999_999_999_999
CHAIN = 8  # c0 (BASED_ON by D) -> c1 -> ... -> c7 -> R
SECONDS = 4.0
MAX_PAIRS = 900  # keeps why() under 5,000 elements, so no read is cut (a cut read is not checked)


def _w(client, graph: str, q: str, **params) -> None:
    client.graph(graph).query(q, params or None)


def _chain_world(client, graph: str) -> list[str]:
    _w(client, graph, "CREATE (:Source {id: 'R', uri: 'urn:r', kind: 'doc', created_at: 1})")
    _w(client, graph, "CREATE (:Agent {id: 'ag', name: 'ag'}), (:Task {id: 't', title: 't', status: 'open'})")
    chain = [f"c{i}" for i in range(CHAIN)]
    _w(
        client,
        graph,
        "UNWIND $ids AS i CREATE (:Fact {id: i, predicate: 'p', value: i, status: 'active', valid_from: 1, "
        "valid_to: $far, created_at: 1})",
        ids=chain,
        far=FAR,
    )
    _w(
        client,
        graph,
        "UNWIND range(0, size($ids) - 2) AS k MATCH (a:Fact {id: $ids[k]}) MATCH (b:Fact {id: $ids[k + 1]}) "
        "CREATE (a)-[:DERIVED_FROM]->(b)",
        ids=chain,
    )
    _w(
        client,
        graph,
        "MATCH (a:Fact {id: $last}) MATCH (r:Source {id: 'R'}) MATCH (g:Agent {id: 'ag'}) "
        "MATCH (t:Task {id: 't'}) MATCH (c0:Fact {id: 'c0'}) "
        "CREATE (a)-[:DERIVED_FROM]->(r) "
        "CREATE (d:Decision {id: 'D', text: 'd', at: 2, created_at: 2}) "
        "CREATE (g)-[:DECIDED]->(d), (d)-[:FOR]->(t), (d)-[:BASED_ON]->(c0)",
        last=chain[-1],
    )
    return chain


PAIR = (
    "MATCH (d:Decision {id: 'D'}) MATCH (deep:Fact {id: $deep}) "
    "CREATE (x:Fact {id: $x, predicate: 'p', value: $x, status: 'active', valid_from: $at, valid_to: $far, "
    "created_at: $at}) "
    "CREATE (deep)-[:DERIVED_FROM]->(x) CREATE (d)-[:BASED_ON]->(x)"
)


def _race(n_readers: int, read, write, flip=None) -> dict[str, int]:
    """Run 1 writer, an optional flipper and ``n_readers`` readers for SECONDS; return the counters."""
    stop = threading.Event()
    out = {"reads": 0, "writes": 0, "flips": 0, "errors": 0}
    lock = threading.Lock()
    failures: list[str] = []

    def bump(k: str, n: int = 1) -> None:
        with lock:
            out[k] = out.get(k, 0) + n

    def writer() -> None:
        k = 0
        while not stop.is_set() and k < MAX_PAIRS:
            write(k)
            k += 1
            bump("writes")

    def flipper() -> None:
        on = False
        while not stop.is_set():
            time.sleep(0.02)
            flip(not on)
            on = not on
            bump("flips")

    def reader() -> None:
        state: dict[str, int] = {}
        while not stop.is_set():
            try:
                bad = read(state)
            except Exception as exc:  # noqa: BLE001 (counted; the test fails on any error)
                failures.append(repr(exc))
                bump("errors")
                continue
            bump("reads")
            for k, n in bad.items():
                bump(k, n)

    threads = [threading.Thread(target=writer)] + [threading.Thread(target=reader) for _ in range(n_readers)]
    if flip is not None:
        threads.append(threading.Thread(target=flipper))
    for t in threads:
        t.start()
    time.sleep(SECONDS)
    stop.set()
    for t in threads:
        t.join()
    assert not failures, failures[:3]
    return out


def test_why_reads_one_snapshot_under_concurrent_appends_and_quarantine(client, graph):
    chain = _chain_world(client, graph)
    lin = Lineage(client, graph)
    base = lin.why("D", depth=12, max_elements=5000)
    assert any(e["to"] == "R" for e in base["edges"])  # the chain reaches its source at depth 12

    def write(k: int) -> None:
        client.graph(graph).query(PAIR, {"deep": chain[-1], "x": f"x{k:05d}", "at": 10 + k, "far": FAR})

    def flip(on: bool) -> None:
        if on:
            lin.quarantine("R", depth=12)
        else:
            lin.release_quarantine("R", depth=12)

    def read(state: dict[str, int]) -> dict[str, int]:
        r = lin.why("D", depth=12, max_elements=5000)
        if r["truncated"]:
            return {"skipped": 1}
        edges = r["edges"]
        based = {e["to"] for e in edges if e["from"] == "D" and e["rel"] == "BASED_ON" and e["to"][0] == "x"}
        derived = {
            e["to"]
            for e in edges
            if e["from"] == chain[-1] and e["rel"] == "DERIVED_FROM" and e["to"][0] == "x"
        }
        status = {n["props"].get("status") for n in r["nodes"] if n["id"] in chain}
        bad = {"w1": int(based != derived), "w2": int(len(status) > 1)}
        bad["w3"] = int(len(based) < state.get("n", 0))
        state["n"] = len(based)
        return bad

    out = _race(4, read, write, flip)
    assert out["reads"] >= 20 and out["writes"] >= 50 and out["flips"] >= 20, out
    assert out.get("w1", 0) == 0 and out.get("w2", 0) == 0 and out.get("w3", 0) == 0, out


def test_impact_reads_one_snapshot_under_concurrent_appends(client, graph):
    chain = _chain_world(client, graph)
    lin = Lineage(client, graph)
    first = lin.impact("source", "R", depth=12, max_detail=1)
    f0, d0 = first["facts"]["total"], first["decisions"]["total"]
    assert (f0, d0) == (CHAIN, 1)
    one = (
        "MATCH (p:Fact {id: $p}) MATCH (t:Task {id: 't'}) "
        "CREATE (x:Fact {id: $x, predicate: 'p', value: $x, status: 'active', valid_from: $at, "
        "valid_to: $far, created_at: $at}) CREATE (x)-[:DERIVED_FROM]->(p) "
        "CREATE (d:Decision {id: $d, text: 'd', at: $at, created_at: $at}) CREATE (d)-[:BASED_ON]->(x) "
        "CREATE (d)-[:FOR]->(t)"
    )

    def write(k: int) -> None:
        p = chain[k % CHAIN]
        client.graph(graph).query(
            one, {"p": p, "x": f"y{k:05d}", "d": f"dy{k:05d}", "at": 10 + k, "far": FAR}
        )

    def read(state: dict[str, int]) -> dict[str, int]:
        r = lin.impact("source", "R", depth=12, max_detail=1)
        nf, nd = r["facts"]["total"], r["decisions"]["total"]
        bad = {"i1": int(nd - d0 != nf - f0), "i2": int(nf < state.get("f", 0))}
        state["f"] = nf
        return bad

    out = _race(4, read, write)
    assert out["reads"] >= 20 and out["writes"] >= 50, out
    assert out.get("i1", 0) == 0 and out.get("i2", 0) == 0, out
