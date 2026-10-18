"""P9-f, ported onto the P9-int / audit tree: ``assert_fact(derived_from=...)`` writes DERIVED_FROM itself.

Crucible L6-F killed a writer 200 times and found facts written "derived from an earlier fact" without that
link: the service wrote the fact, then ``Lineage.derive_from`` ran as a second statement. p9f-b also moved the
Step / WROTE / READ edges into the statement with a ``StepIntent``; the integ tree keeps P9-int / P12's design
for those (the runtime opens the Step first, the statement writes WROTE, ``tests/mcp/test_fold_wrote.py``),
so only the origins move here.
"""

from __future__ import annotations

import pytest

from knewat.embed import HashEmbedder
from knewat.engram import Engram
from knewat.engram.errors import UnknownReference
from knewat.lineage import Lineage


def q(client, graph, cypher, **p):
    return client.graph(graph).ro_query(cypher, p or None).result_set


@pytest.fixture
def svc(client, graph):
    eng, lin = Engram(client, graph, HashEmbedder()), Lineage(client, graph)
    scope = eng.create_scope("global", "global", now=1)
    src = lin.create_source("urn:src", now=1)
    ep = eng.start_session("a", now=1)
    return eng, lin, scope, src, ep


def test_origins_are_linked_by_the_assert_statement_itself(client, graph, svc):
    eng, lin, scope, src, _ = svc
    r1 = eng.assert_fact("S", "p", "one", scope, "a", source_id=src, now=100)
    r2 = eng.assert_fact(
        "S", "q", "two", scope, "a", now=200, derived_from=[r1["fact_id"], src, r1["fact_id"]]
    )
    got = q(
        client,
        graph,
        "MATCH (:Fact {id: $f})-[:DERIVED_FROM]->(o) RETURN o.id ORDER BY o.id",
        f=r2["fact_id"],
    )
    assert got == sorted([[r1["fact_id"]], [src]])  # duplicates in the list collapse
    # the same statement that made the fact made the links: nothing was left for Lineage.derive_from
    assert lin.derive_from(r2["fact_id"], [r1["fact_id"]]) == 1  # idempotent, as before


def test_origin_equal_to_the_given_source_is_not_linked_twice(client, graph, svc):
    eng, lin, scope, src, _ = svc
    r = eng.assert_fact("S", "p", "one", scope, "a", source_id=src, now=100, derived_from=[src])
    n = q(
        client,
        graph,
        "MATCH (:Fact {id: $f})-[d:DERIVED_FROM]->(:Source {id: $s}) RETURN count(d)",
        f=r["fact_id"],
        s=src,
    )
    assert n == [[1]]


def test_a_duplicate_gains_the_origins_and_never_derives_from_itself(client, graph, svc):
    eng, lin, scope, src, _ = svc
    first = eng.assert_fact("S", "p", "same value", scope, "a", now=100)
    other = eng.assert_fact("S", "q", "other", scope, "a", now=110)
    dup = eng.assert_fact(
        "S", "p", "same value", scope, "b", now=200, derived_from=[first["fact_id"], other["fact_id"], src]
    )
    assert dup["duplicate_of"] == first["fact_id"]
    got = q(
        client,
        graph,
        "MATCH (:Fact {id: $f})-[:DERIVED_FROM]->(o) RETURN o.id ORDER BY o.id",
        f=first["fact_id"],
    )
    assert got == sorted([[other["fact_id"]], [src]])  # its own id is skipped


def test_an_unknown_origin_writes_nothing_not_even_the_entity(client, graph, svc):
    eng, lin, scope, src, _ = svc
    before = q(client, graph, "MATCH (n) RETURN count(n)")
    with pytest.raises(UnknownReference) as exc:
        eng.assert_fact("Brand new subject", "p", "v", scope, "a", now=5, derived_from=[src, "nope"])
    assert exc.value.kind == "origin" and exc.value.ids == ["nope"]
    assert q(client, graph, "MATCH (n) RETURN count(n)") == before
    # an existing entity: the statement's own guard rejects it and no Agent / Fact appears
    eng.assert_fact("S", "p", "one", scope, "a", now=6)
    before = q(client, graph, "MATCH (n) RETURN count(n)")
    with pytest.raises(UnknownReference):
        eng.assert_fact("S", "p", "two", scope, "z", now=7, derived_from=["nope"])
    assert q(client, graph, "MATCH (n) RETURN count(n)") == before


def test_an_episode_is_an_origin_too(client, graph, svc):
    eng, lin, scope, src, session = svc
    eid = eng.remember_episode(session, "user", "something happened", now=50)
    r = eng.assert_fact("S", "p", "one", scope, "a", now=100, derived_from=[eid])
    assert q(
        client, graph, "MATCH (:Fact {id: $f})-[:DERIVED_FROM]->(o:Episode) RETURN o.id", f=r["fact_id"]
    ) == [[eid]]


def test_too_many_origins_is_rejected_before_anything_is_written(client, graph, svc):
    eng, lin, scope, src, _ = svc
    with pytest.raises(ValueError):
        eng.assert_fact("S", "p", "v", scope, "a", derived_from=[f"x{i}" for i in range(101)])
