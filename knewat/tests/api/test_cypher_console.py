"""POST /api/{tenant}/cypher: read-only Cypher text, the text check, the row cap, error mapping."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from knewat.api import routes_cypher as R


def post(api, tenant, query, params=None):
    body = {"query": query} if params is None else {"query": query, "params": params}
    return api.post(f"/api/{tenant}/cypher", json=body)


# ---------------------------------------------------------------- the text check (no database)
@pytest.mark.parametrize(
    "text",
    [
        "LOAD CSV FROM 'file:///etc/passwd' AS r RETURN r",
        "load\ncsv from 'http://127.0.0.1:6379' as r return r",
        "RETURN 'http://x' LOAD CSV FROM 'file:///a' AS r RETURN r",  # a // inside a string is not a comment
        "MATCH (n) /* hi */ LOAD /* x */ CSV FROM 'a' AS r RETURN r",
        "CALL dbms.listConfig()",
        "CALL db.idx.fulltext.createNodeIndex('A', 'b')",
        "CALL/**/apoc.cypher.run('x', {})",
    ],
)
def test_forbidden_text_is_a_400(text):
    with pytest.raises(HTTPException) as e:
        R.check_text(text)
    assert e.value.status_code == 400


@pytest.mark.parametrize(
    "text",
    [
        "MATCH (n) RETURN n LIMIT 5",
        "CALL db.labels() YIELD label RETURN label",
        "CALL db.idx.vector.queryNodes('Fact', 'embedding', 3, vecf32([1.0])) YIELD node RETURN node",
        "CALL algo.pageRank('Fact', 'SUPERSEDES') YIELD node, score RETURN node, score",
        "MATCH (n) WHERE n.text = 'we LOAD CSV files and CALL apoc.x()' RETURN n",  # keywords inside a string
        "// LOAD CSV\nMATCH (n) RETURN n  /* CALL dbms.x() */",
    ],
)
def test_allowed_text_passes(text):
    R.check_text(text)


def test_overlong_text_is_a_413():
    with pytest.raises(HTTPException) as e:
        R.check_text("RETURN 1 " + " " * R.MAX_QUERY_CHARS)
    assert e.value.status_code == 413


def test_vectors_in_properties_are_summarised_but_returned_lists_are_not():
    class N:
        id, labels = 1, ["Fact"]
        properties = {"embedding": [0.1] * 384, "tags": [1, 2]}

    out = R.jsonable(N())
    assert out["properties"]["embedding"] == "<vector, 384 dims>"
    assert out["properties"]["tags"] == [1, 2]
    assert R.jsonable(list(range(1000))) == list(range(1000))
    assert R.jsonable(float("nan")) == "nan"


# ---------------------------------------------------------------- against a real graph
def test_nodes_edges_paths_and_scalars(api, seeded):
    t = seeded["tenant"]
    r = post(
        api,
        t,
        "MATCH p = (a:Fact)-[e:SUPERSEDES]->(b:Fact) RETURN a, e, p, a.id AS id, 1.5 AS x, null AS nothing",
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["columns"] == ["a", "e", "p", "id", "x", "nothing"]
    assert body["row_count"] == len(body["rows"]) >= 1 and body["truncated"] is False
    a, e, p, fid, x, nothing = body["rows"][0]
    assert a["_type"] == "node" and "Fact" in a["labels"] and a["properties"]["id"] == fid
    assert e["_type"] == "edge" and e["type"] == "SUPERSEDES" and isinstance(e["src"], int)
    assert p["_type"] == "path" and len(p["nodes"]) == 2 and len(p["edges"]) == 1
    assert (x, nothing) == (1.5, None)
    assert body["run_time_ms"] >= 0 and body["tenant"] == t


def test_stored_embeddings_do_not_flood_the_response(api, seeded):
    body = post(api, seeded["tenant"], "MATCH (f:Fact) RETURN f LIMIT 1").json()
    props = body["rows"][0][0]["properties"]
    assert all(not (isinstance(v, list) and len(v) >= R.VECTOR_MIN_DIMS) for v in props.values())


def test_params_are_passed(api, seeded):
    r = post(api, seeded["tenant"], "MATCH (f:Fact {id: $id}) RETURN f.id AS id", {"id": seeded["f2"]})
    assert r.json()["rows"] == [[seeded["f2"]]]


def test_call_procedures_run(api, seeded):
    r = post(api, seeded["tenant"], "CALL db.labels() YIELD label RETURN label")
    assert "Fact" in {row[0] for row in r.json()["rows"]}


@pytest.mark.parametrize(
    "query",
    [
        "CREATE (:Hacked)",
        "MATCH (f:Fact) SET f.value = 'x'",
        "MATCH (f:Fact) DETACH DELETE f",
        "MERGE (:Hacked {id: 1})",
        "MATCH (f:Fact) REMOVE f.value",
    ],
)
def test_writes_are_rejected_and_change_nothing(api, seeded, query):
    t = seeded["tenant"]
    before = post(api, t, "MATCH (n) RETURN count(n) AS n").json()["rows"]
    r = post(api, t, query)
    assert r.status_code == 400 and "read-only" in r.json()["detail"]
    assert post(api, t, "MATCH (n) RETURN count(n) AS n").json()["rows"] == before


def test_syntax_errors_carry_the_database_message(api, seeded):
    r = post(api, seeded["tenant"], "MATCH (n RETURN n")
    assert r.status_code == 400 and r.json()["detail"]


def test_rows_are_capped_and_flagged(api, seeded):
    r = post(api, seeded["tenant"], f"UNWIND range(1, {R.MAX_ROWS + 25}) AS i RETURN i")
    body = r.json()
    assert body["row_count"] == R.MAX_ROWS == len(body["rows"]) and body["truncated"] is True


def test_runaway_query_times_out_with_a_408(api, seeded, monkeypatch):
    monkeypatch.setattr(R, "TIMEOUT_MS", 200)
    r = post(
        api, seeded["tenant"], "UNWIND range(1, 100000) AS a UNWIND range(1, 100000) AS b RETURN count(*)"
    )
    assert r.status_code == 408, r.text


def test_unknown_and_invalid_tenants(api):
    assert post(api, "apit_nosuchtenant", "RETURN 1").status_code == 404
    assert post(api, "Bad-Tenant", "RETURN 1").status_code == 404


def test_validation_and_load_over_http(api, seeded):
    t = seeded["tenant"]
    assert api.post(f"/api/{t}/cypher", json={}).status_code == 422
    assert post(api, t, "").status_code == 422
    assert post(api, t, "LOAD CSV FROM 'file:///etc/passwd' AS r RETURN r").status_code == 400
    assert post(api, t, "RETURN " + "1+" * 3000 + "1").status_code == 413
    assert post(api, t, "RETURN 1", {"k": "x" * (R.MAX_PARAMS_BYTES + 1)}).status_code == 413


def test_a_client_socket_timeout_is_also_a_408_not_a_503(api, seeded, monkeypatch):
    from redis.exceptions import TimeoutError as RedisTimeout

    def boom(*_a, **_k):
        raise RedisTimeout("Timeout reading from socket")

    monkeypatch.setattr(api.app.state.ro, "cypher", boom)
    assert post(api, seeded["tenant"], "RETURN 1").status_code == 408
