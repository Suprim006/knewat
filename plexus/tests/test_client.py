import asyncio

import pytest
from redis.exceptions import ResponseError

from plexus.graph.client import AsyncGraphClient, GraphClient, Rows
from plexus.graph.queries import QueryLibrary, ReadOnlyViolation
from tests.conftest import TEST_DB_HOST, TEST_DB_PORT


def _lib(tmp_path, files: dict[str, str]) -> QueryLibrary:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return QueryLibrary(tmp_path)


def _q(name: str, params: str, returns: str, mode: str, purpose: str, body: str) -> str:
    header = [f"// name: {name}", f"// purpose: {purpose}", f"// params: {params}"]
    header += [f"// returns: {returns}", f"// mode: {mode}"]
    return "\n".join([*header, body, ""])


LIB_FILES = {
    "t/put.cypher": _q(
        "t/put", "id:str, n:int", "id, n", "rw", "p",
        "CREATE (x:Thing {id: $id, n: $n}) RETURN x.id AS id, x.n AS n",
    ),
    "t/get.cypher": _q(
        "t/get", "id:str", "id, n", "ro", "p",
        "MATCH (x:Thing {id: $id}) RETURN x.id AS id, x.n AS n",
    ),
    "t/liar.cypher": _q(
        "t/liar", "none", "r", "ro", "declared ro but writes",
        "CREATE (:Thing {id: 'liar'}) RETURN 1 AS r",
    ),
}  # fmt: skip


@pytest.fixture
def lib_client(tmp_path):
    c = GraphClient(host=TEST_DB_HOST, port=TEST_DB_PORT, password="", library=_lib(tmp_path, LIB_FILES))
    yield c
    c.close()


def test_rw_then_ro_roundtrip_returns_dicts_and_run_time(lib_client, empty_graph):
    res = lib_client.rw(empty_graph, "t/put", {"id": "a", "n": 7})
    assert res == [{"id": "a", "n": 7}]
    assert isinstance(res, Rows)
    assert res.run_time_ms >= 0 and res.header == ["id", "n"]
    assert res.stats["nodes_created"] == 1

    got = lib_client.ro(empty_graph, "t/get", {"id": "a"})
    assert got == [{"id": "a", "n": 7}]
    assert got.run_time_ms >= 0
    assert lib_client.ro(empty_graph, "t/get", {"id": "zzz"}) == []


def test_ro_refuses_rw_query_and_runs_nothing(lib_client, empty_graph):
    with pytest.raises(ReadOnlyViolation):
        lib_client.ro(empty_graph, "t/put", {"id": "a", "n": 1})
    # Nothing was written (the graph may not even exist yet).
    lib_client.rw(empty_graph, "t/put", {"id": "probe", "n": 0})
    assert lib_client.ro(empty_graph, "t/get", {"id": "a"}) == []


def test_ro_uses_ro_query_server_side(lib_client, empty_graph):
    """A query mislabelled ``ro`` that writes is rejected by the server: ro() uses GRAPH.RO_QUERY."""
    lib_client.rw(empty_graph, "t/put", {"id": "seed", "n": 0})
    with pytest.raises(ResponseError, match="(?i)read.?only"):
        lib_client.ro(empty_graph, "t/liar")


def test_params_are_bound_not_interpolated(lib_client, empty_graph):
    evil = "x'}) MATCH (m) DETACH DELETE m //"
    lib_client.rw(empty_graph, "t/put", {"id": evil, "n": 1})
    assert lib_client.ro(empty_graph, "t/get", {"id": evil}) == [{"id": evil, "n": 1}]


def test_timeout_is_passed(lib_client, empty_graph):
    lib_client.rw(empty_graph, "t/put", {"id": "a", "n": 1}, timeout_ms=2000)
    assert lib_client.ro(empty_graph, "t/get", {"id": "a"}, timeout_ms=2000)


def test_env_defaults(monkeypatch):
    monkeypatch.setenv("FALKORDB_HOST", "127.0.0.1")
    monkeypatch.setenv("FALKORDB_PORT", str(TEST_DB_PORT))
    monkeypatch.setenv("FALKORDB_PASSWORD", "")
    c = GraphClient()
    try:
        assert (c.host, c.port) == ("127.0.0.1", TEST_DB_PORT)
        assert c.ping()
    finally:
        c.close()


def test_delete_graph_missing_is_ok(client):
    client.delete_graph("test_does_not_exist_ever")


@pytest.fixture
async def aclient(tmp_path):
    c = AsyncGraphClient(
        host=TEST_DB_HOST,
        port=TEST_DB_PORT,
        password="",
        library=_lib(tmp_path, LIB_FILES),
        max_connections=8,
    )
    yield c
    await c.aclose()


async def test_async_client_rw_ro_and_concurrency(aclient, empty_graph):
    first = await aclient.rw(empty_graph, "t/put", {"id": "a", "n": 1})
    assert first == [{"id": "a", "n": 1}] and first.run_time_ms >= 0
    with pytest.raises(ReadOnlyViolation):
        await aclient.ro(empty_graph, "t/put", {"id": "b", "n": 2})

    # 40 concurrent reads over a pool of 8: the blocking pool queues instead of failing.
    rows = await asyncio.gather(*(aclient.ro(empty_graph, "t/get", {"id": "a"}) for _ in range(40)))
    assert all(r == [{"id": "a", "n": 1}] for r in rows)
    assert aclient.pool.max_connections == 8

    await aclient.delete_graph("test_does_not_exist_ever")
