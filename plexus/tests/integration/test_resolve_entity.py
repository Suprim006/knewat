"""P9-d: the atomic ``engram/resolve_entity`` statement and ``Engram.resolve_entity_ex`` on top of it.

The probe tests at the top re-verify, with the real 384-d bge-small model, the FalkorDB 6.0.2 behaviours the
statement relies on (PRODUCT_FIXES_ANALYSIS C.2 used 4-d toy vectors).
"""

from __future__ import annotations

import pytest

from plexus.common import normalize
from plexus.embed import FastEmbedder, HashEmbedder
from plexus.engram import Engram
from plexus.engram.service import ENTITY_NEAR, FULLTEXT_JACCARD, _tokens, token_key


@pytest.fixture(scope="module")
def fast() -> FastEmbedder:
    return FastEmbedder()


@pytest.fixture
def feng(client, graph, fast) -> Engram:
    return Engram(client, graph, fast)


def _count(client, graph, cypher="MATCH (e:Entity) RETURN count(e)", params=None) -> int:
    return client.graph(graph).ro_query(cypher, params or {}).result_set[0][0]


def _stmt(eng: Engram, name: str, kind: str = "thing", *, k: int = 5, thr: float = ENTITY_NEAR) -> dict:
    """Run the raw statement (no Python pre-read) so the tests exercise the query itself."""
    tok = sorted(set(_tokens(name)))
    rows = eng.client.rw(
        eng.graph,
        "engram/resolve_entity",
        {
            "norm": normalize(name),
            "name": " ".join(name.split()),
            "kind": kind,
            "tok": tok,
            "num_key": token_key(name),
            "q": "|".join(tok) or "plexusnomatchtoken",
            "emb": eng._embed([name])[0],
            "entity_id": f"id-{normalize(name)}",
            "jac": FULLTEXT_JACCARD,
            "thr": thr,
            "k": k,
            "now": 1000,
        },
    )
    assert len(rows) == 1, "the statement must always return exactly one row"
    return rows[0]


# -- C.2 quirks, real 384-d embedder ---------------------------------------------------------------


@pytest.mark.slow
def test_probe_empty_graph_create_path_keeps_the_row(feng, client, graph):
    """Both lookups return nothing (empty indexes): a bare CALL would drop the row and create nothing."""
    r = _stmt(feng, "Payment Service")
    assert (r["how"], r["id"], r["name"], r["kind"]) == (
        "new",
        "id-payment service",
        "Payment Service",
        "thing",
    )
    assert _count(client, graph) == 1


@pytest.mark.slow
def test_probe_exact_fulltext_and_vector_paths(feng, client, graph):
    _stmt(feng, "Payment Service")
    assert _stmt(feng, "Payment Service")["how"] == "exact"
    r = _stmt(feng, "payment-service")  # other spelling, same tokens
    assert (r["how"], r["id"], r["name"]) == ("fulltext", "id-payment service", "Payment Service")
    _stmt(feng, "PostgreSQL", "tech")
    r = _stmt(feng, "Postgres", "tech")  # no shared token: only the embedding can find it
    assert (r["how"], r["id"]) == ("vector", "id-postgresql")
    assert _count(client, graph) == 2


@pytest.mark.slow
def test_probe_create_then_continue_with_the_bound_variable(feng, client, graph):
    """A node MERGEd in the statement is what the statement returns, and a second call finds it."""
    a = _stmt(feng, "Billing Gateway")
    b = _stmt(feng, "billing gateway")
    assert a["how"] == "new" and b["how"] == "exact" and a["id"] == b["id"]
    stored = (
        client.graph(graph)
        .ro_query(
            "MATCH (e:Entity) RETURN e.id, e.tok, e.num_key, e.kind, e.created_at, e.embedding IS NOT NULL"
        )
        .result_set
    )
    assert stored == [["id-billing gateway", ["billing", "gateway"], "", "thing", 1000, True]]


# -- candidate rules ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "first,second", [("auth gateway", "auth gateway service"), ("auth gateway service", "auth gateway")]
)
def test_fulltext_is_independent_of_creation_order(eng, client, graph, first, second):
    """AND-ing the tokens missed 'auth gateway' for 'auth gateway service' (Jaccard 2/3): now OR + Jaccard."""
    a = _stmt(eng, first)
    b = _stmt(eng, second)
    assert a["how"] == "new" and b["how"] == "fulltext" and b["id"] == a["id"]
    assert _count(client, graph) == 1


def test_fulltext_below_jaccard_creates_a_new_entity(eng, client, graph):
    _stmt(eng, "auth gateway")
    assert _stmt(eng, "auth gateway service beta")["how"] == "new"  # 2/4 = 0.5 < 0.6
    assert _count(client, graph) == 2


def test_kind_and_numbers_guard_every_lookup(eng, client, graph):
    _stmt(eng, "Billing Service 1", "service")
    assert _stmt(eng, "Billing Service 2", "service")["how"] == "new"  # different num_key
    assert _stmt(eng, "billing-service 1", "person")["how"] == "new"  # different kind
    assert (
        _stmt(eng, "billing service-1", "service")["how"] == "fulltext"
    )  # new spelling, same kind and number
    assert _count(client, graph) == 3


def test_ties_resolve_to_the_oldest_entity(client, graph):
    """Equal candidates: the oldest (created_at, id) wins, whatever order the index returns them in."""
    eng = Engram(client, graph, HashEmbedder())
    g = client.graph(graph)
    for i, ts in (("b", 20), ("a", 20), ("c", 10)):
        g.query(
            "CREATE (:Entity {id: $i, norm_name: $n, name: $n, kind: 'thing', num_key: '',"
            " tok: ['x', 'y', $i],"
            " created_at: $t, embedding: vecf32($e)})",
            {"i": i, "n": f"x y {i}", "t": ts, "e": eng._embed(["unrelated " + i])[0]},
        )
    r = _stmt(eng, "x y")  # tok x,y vs x,y,<i>: Jaccard 2/3 for all three -> oldest created_at (c), then id
    assert (r["how"], r["id"]) == ("fulltext", "c")


@pytest.mark.parametrize("name", ["!!!", "the", "a", "...-..."])
def test_degenerate_names_still_create_one_row(eng, client, graph, name):
    """No usable full-text token (punctuation, stop words): the lookup must not error or drop the row."""
    r = _stmt(eng, name)
    assert r["how"] == "new"
    assert _stmt(eng, name)["how"] == "exact"
    assert _count(client, graph) == 1


# -- the Python wrapper ------------------------------------------------------------------------------


def test_resolve_entity_ex_result_shape_and_stored_keys(eng, client, graph):
    a = eng.resolve_entity_ex("Payment Service", "service", now=5)
    assert (a["created"], a["matched_by"], a["name"], a["kind"]) == (
        True,
        "new",
        "Payment Service",
        "service",
    )
    b = eng.resolve_entity_ex("  PAYMENT   service ", "service")
    assert (b["id"], b["created"], b["matched_by"]) == (a["id"], False, "exact")
    c = eng.resolve_entity_ex("payment-service", "service")
    assert (c["id"], c["created"], c["matched_by"], c["name"]) == (
        a["id"],
        False,
        "fulltext",
        "Payment Service",
    )
    row = client.graph(graph).ro_query("MATCH (e:Entity) RETURN e.tok, e.num_key, e.created_at").result_set
    assert row == [[["payment", "service"], "", 5]]


def test_exact_hit_is_write_free(eng, client, graph):
    """The hot path (the entity exists) must stay a single read, with no write statement."""
    eng.resolve_entity("Acme Notes API", "service")
    calls: list[str] = []
    real_rw = client.rw
    client.rw = lambda g, name, params=None, **kw: (calls.append(name), real_rw(g, name, params, **kw))[1]
    try:
        eng.resolve_entity("acme notes api", "service")
    finally:
        client.rw = real_rw
    assert calls == []


def test_rejected_references_create_no_entity(eng, client, graph, proj):
    """P5 Q8: a call with an unknown scope must not leave an orphan Entity behind."""
    from plexus.engram.errors import UnknownReference

    with pytest.raises(UnknownReference):
        eng.assert_fact("Ghost Service", "database", "pg", "no-such-scope", "a1", now=1)
    assert _count(client, graph) == 0


def test_empty_name_is_rejected(eng):
    with pytest.raises(ValueError):
        eng.resolve_entity("   ")
