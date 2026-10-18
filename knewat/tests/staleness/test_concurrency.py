"""Slice 7: concurrent ``mark_changed`` and ``assert_fact`` / ``anchor_fact`` on the same files.

Writes are serialised per graph and every call is one statement, so each call is atomic. The test checks the
consequences: no errors, one anchor per path, one Change per effective call (no duplicates), every old
fact anchored to a changed file is suspect, and a fact that is not suspect was anchored after the last change
touching its file.
"""

from __future__ import annotations

import threading

from knewat.codescan.paths import anchor_id

from .conftest import cypher

P1 = "C:/repo/app/one.py"
P2 = "C:/repo/app/two.py"
THREADS = 20
SKEW_MS = 250  # `at` is taken by the caller just before its statement runs; tolerate this much reordering


def test_concurrent_mark_changed_and_asserts(stale, mem, client, graph, eng):
    stale.mark_changed([{"path": P1, "new_hash": "base1"}, {"path": P2, "new_hash": "base2"}])
    old: dict[str, list[str]] = {P1: [], P2: []}
    for i in range(10):
        for p in (P1, P2):
            f = mem.fact(f"old {i}", f"value {i} {p}", subject=f"Old {p}")
            stale.anchor_fact(f, p)
            old[p].append(f)

    start = threading.Barrier(2 * THREADS)
    errors: list[BaseException] = []
    new_facts: list[tuple[str, str]] = []
    sent: dict[str, set[str]] = {P1: set(), P2: set()}
    lock = threading.Lock()

    def changer(i: int):
        paths = [(P1,), (P2,), (P1, P2)][i % 3]
        changes = [{"path": p, "new_hash": f"h{i}-{p[-7:]}"} for p in paths]
        try:
            start.wait()
            stale.mark_changed(changes, commit=f"c{i}", agent_id=f"hook-{i}")
            with lock:
                for c in changes:
                    sent[c["path"]].add(c["new_hash"])
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def asserter(i: int):
        p = (P1, P2)[i % 2]
        try:
            start.wait()
            r = eng.assert_fact(f"New {i}", "status", f"fresh {i}", mem.proj, f"agent-{i}")
            stale.anchor_fact(r["fact_id"], p)
            with lock:
                new_facts.append((r["fact_id"], p))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=changer, args=(i,)) for i in range(THREADS)]
    threads += [threading.Thread(target=asserter, args=(i,)) for i in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not errors, errors
    assert len(new_facts) == THREADS

    # one anchor per path, holding one of the hashes that was sent
    for p in (P1, P2):
        rows = cypher(client, graph, "MATCH (a:CodeAnchor {id:$i}) RETURN a.hash", i=anchor_id(p))
        assert len(rows) == 1 and rows[0][0] in sent[p], (p, rows, sent[p])
    assert cypher(client, graph, "MATCH (a:CodeAnchor {symbol:''}) RETURN count(a)") == [[2]]

    # every effective call made exactly one Change, with a unique id
    changes = cypher(client, graph, "MATCH (c:Change) RETURN c.id, c.at, c.commit")
    assert len(changes) == THREADS and len({c[0] for c in changes}) == THREADS
    assert {c[2] for c in changes} == {f"c{i}" for i in range(THREADS)}

    # facts that existed before the changes: all suspect, each SUSPECTED once per change that touched its file
    def state(fid):
        return cypher(
            client, graph, "MATCH (f:Fact {id:$f}) RETURN coalesce(f.verify_state,'verified')", f=fid
        )[0][0]

    touched = {
        p: cypher(
            client,
            graph,
            "MATCH (c:Change)-[:TOUCHED]->(:CodeAnchor {id:$i}) RETURN c.id, max(c.at)",
            i=anchor_id(p),
        )
        for p in (P1, P2)
    }
    n_changes = {p: len(rows) for p, rows in touched.items()}
    assert n_changes[P1] + n_changes[P2] >= THREADS  # P1 and P2 are touched by 2/3 of the calls each
    for p in (P1, P2):
        for fid in old[p]:
            assert state(fid) == "suspect", (p, fid)
            n = cypher(
                client, graph, "MATCH (c:Change)-[r:SUSPECTED]->(:Fact {id:$f}) RETURN count(r)", f=fid
            )
            assert n == [[n_changes[p]]]

    # facts asserted + anchored concurrently: suspect, or anchored after the last change on their file
    for fid, p in new_facts:
        if state(fid) == "suspect":
            continue
        anchored_at = cypher(client, graph, "MATCH (:Fact {id:$f})-[r:ANCHORED_TO]->() RETURN r.at", f=fid)[
            0
        ][0]
        last_change = max(at for _, at in touched[p])
        assert anchored_at >= last_change - SKEW_MS, (fid, p, anchored_at, last_change)

    # no duplicate edges from the MERGEs
    dup = cypher(
        client,
        graph,
        "MATCH (c:Change)-[r:SUSPECTED]->(f:Fact) WITH c, f, count(r) AS n WHERE n > 1 RETURN count(*)",
    )
    assert dup == [[0]]
