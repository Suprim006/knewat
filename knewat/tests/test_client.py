import pytest
from redis.exceptions import BusyLoadingError, RedisError, ResponseError

from knewat.graph.client import GraphClient, Rows
from knewat.graph.queries import QueryLibrary, ReadOnlyViolation
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


# ---------------------------------------------------------------- sync pool: waits instead of failing
def _threads(n: int, fn):
    """Run ``fn(i)`` in ``n`` threads released together; returns (results, errors)."""
    import threading

    barrier = threading.Barrier(n)
    results: list = [None] * n
    errors: list[BaseException] = []

    def go(i):
        try:
            barrier.wait(30)
            results[i] = fn(i)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    ts = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(120)
    return results, errors


def test_sync_client_survives_300_concurrent_threads(tmp_path, empty_graph):
    c = GraphClient(host=TEST_DB_HOST, port=TEST_DB_PORT, password="", library=_lib(tmp_path, LIB_FILES))
    try:
        c.rw(empty_graph, "t/put", {"id": "a", "n": 1})
        results, errors = _threads(300, lambda i: [c.ro(empty_graph, "t/get", {"id": "a"}) for _ in range(3)])
        assert errors == []
        assert all(r[-1] == [{"id": "a", "n": 1}] for r in results)
    finally:
        c.close()


def test_sync_client_small_pool_queues_callers(tmp_path, empty_graph):
    c = GraphClient(
        host=TEST_DB_HOST,
        port=TEST_DB_PORT,
        password="",
        library=_lib(tmp_path, LIB_FILES),
        max_connections=4,
    )
    try:
        assert c.pool.max_connections == 4
        c.rw(empty_graph, "t/put", {"id": "a", "n": 1})
        results, errors = _threads(60, lambda i: c.ro(empty_graph, "t/get", {"id": "a"}))
        assert errors == [] and all(r == [{"id": "a", "n": 1}] for r in results)
    finally:
        c.close()


def test_sync_pool_size_env_and_default(monkeypatch):
    monkeypatch.delenv("KNEWAT_DB_POOL", raising=False)
    c = GraphClient(host=TEST_DB_HOST, port=TEST_DB_PORT, password="")
    assert c.pool.max_connections == 256
    c.close()
    monkeypatch.setenv("KNEWAT_DB_POOL", "17")
    c = GraphClient(host=TEST_DB_HOST, port=TEST_DB_PORT, password="")
    assert c.pool.max_connections == 17
    c.close()


def test_sync_pool_timeout_raises_instead_of_hanging():
    c = GraphClient(host=TEST_DB_HOST, port=TEST_DB_PORT, password="", max_connections=1, pool_timeout=0.2)
    try:
        held = c.pool.get_connection()
        try:
            with pytest.raises(RedisError, match="(?i)connection"):
                c.ping()
        finally:
            c.pool.release(held)
    finally:
        c.close()


# ---------------------------------------------------------------- Redis still loading the AOF
class _FlakyGraph:
    def __init__(self, fails: int):
        self.fails = fails
        self.calls = 0

    def ro_query(self, statement, params=None, timeout=None):
        self.calls += 1
        if self.calls <= self.fails:
            raise BusyLoadingError("Redis is loading the dataset in memory")
        return type(
            "R",
            (),
            {"header": [], "result_set": [], "run_time_ms": 0.1, "cached_execution": False},
        )()


def test_busy_loading_is_retried_for_a_bounded_time(lib_client, empty_graph, monkeypatch):
    lib_client.loading_wait_s = 5.0
    g = _FlakyGraph(fails=2)
    monkeypatch.setattr(lib_client, "graph", lambda name: g)
    assert lib_client.ro(empty_graph, "t/get", {"id": "x"}) == []
    assert g.calls == 3

    lib_client.loading_wait_s = 0.5
    g = _FlakyGraph(fails=10_000)
    monkeypatch.setattr(lib_client, "graph", lambda name: g)
    with pytest.raises(BusyLoadingError):
        lib_client.ro(empty_graph, "t/get", {"id": "x"})
    assert 1 < g.calls < 10_000


def test_busy_loading_at_connect_is_retried(monkeypatch):
    import knewat.graph.client as mod

    attempts = {"n": 0}
    real = mod.FalkorDB

    def flaky(*a, **kw):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise BusyLoadingError("Redis is loading the dataset in memory")
        return real(*a, **kw)

    monkeypatch.setattr(mod, "FalkorDB", flaky)
    c = GraphClient(host=TEST_DB_HOST, port=TEST_DB_PORT, password="", loading_wait_s=5.0)
    try:
        assert attempts["n"] == 3 and c.ping()
    finally:
        c.close()
    attempts["n"] = -10_000  # never recovers: gives up after the bounded wait
    with pytest.raises(BusyLoadingError):
        GraphClient(host=TEST_DB_HOST, port=TEST_DB_PORT, password="", loading_wait_s=0.5)


def test_sync_pool_speaks_resp2_like_falkordb_does(lib_client):
    """RESP3 would change reply shapes for callers that use the raw connection (MODULE LIST)."""
    mods = lib_client.db.connection.execute_command("MODULE", "LIST")
    assert isinstance(mods[0], list)
