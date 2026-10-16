"""P9-d: ``plexus migrate entities`` (PRODUCT_FIXES_ANALYSIS C.5): backfill tok/num_key, duplicate report."""

from __future__ import annotations

import json
import random
import uuid

import pytest

from plexus.cli import main
from plexus.embed import HashEmbedder
from plexus.engram import Engram
from plexus.engram.migrate import BATCH, backfill_entity_keys, duplicate_names, near_duplicates, run
from plexus.graph.schema import apply_schema
from plexus.graph.tenancy import graph_name


def _vec(seed: int, wobble: float = 0.0) -> list[float]:
    rng = random.Random(seed)
    v = [rng.gauss(0, 1) for _ in range(384)]
    if wobble:
        r2 = random.Random(seed + 1000)
        v = [x + wobble * r2.gauss(0, 1) for x in v]
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


def legacy(client, graph, rows) -> None:
    """Entities as P5-P8 wrote them (no tok / num_key). rows: (id, name, kind, created_at, seed, wobble)."""
    g = client.graph(graph)
    for eid, name, kind, ts, seed, wob in rows:
        g.query(
            "CREATE (:Entity {id: $id, name: $name, norm_name: $norm, kind: $kind, created_at: $ts,"
            " embedding: vecf32($v)})",
            {
                "id": eid,
                "name": name,
                "norm": " ".join(name.split()).casefold(),
                "kind": kind,
                "ts": ts,
                "v": _vec(seed, wob),
            },
        )


def props(client, graph, eid):
    q = "MATCH (e:Entity {id: $id}) RETURN e.tok, e.num_key"
    return client.graph(graph).ro_query(q, {"id": eid}).result_set[0]


@pytest.fixture
def lg(client, graph):
    """A graph with the schema and six legacy entities."""
    legacy(
        client,
        graph,
        [
            ("e1", "auth gateway", "service", 10, 1, 0),
            ("e2", "auth gateway service", "service", 20, 2, 0),  # full-text near-duplicate of e1 (2/3)
            ("e3", "PostgreSQL", "tech", 30, 3, 0),
            ("e4", "Postgres", "tech", 40, 3, 0.02),  # vector near-duplicate of e3, no shared token
            ("e5", "Service 1", "service", 50, 5, 0),
            ("e6", "Service 2", "service", 60, 5, 0.01),  # vector-near but the numbers differ: not reported
        ],
    )
    return graph


# -- backfill ---------------------------------------------------------------------------------------------


def test_dry_run_writes_nothing(client, lg):
    rep = backfill_entity_keys(client, lg, dry_run=True)
    assert (rep["total"], rep["missing"], rep["updated"]) == (6, 6, 0)
    assert props(client, lg, "e1") == [None, None]


def test_backfill_sets_tok_and_num_key_and_is_idempotent(client, lg):
    rep = backfill_entity_keys(client, lg)
    assert (rep["total"], rep["missing"], rep["updated"]) == (6, 6, 6)
    assert props(client, lg, "e2") == [["auth", "gateway", "service"], ""]
    assert props(client, lg, "e5") == [["1", "service"], "1"]
    again = backfill_entity_keys(client, lg)
    assert (again["missing"], again["updated"]) == (0, 0)


def test_backfill_runs_in_bounded_batches(client, graph):
    n = BATCH * 2 + 50
    legacy(client, graph, [(f"id{i:04d}", f"widget {i}", "thing", i, i, 0) for i in range(n)])
    calls = []
    real = client.rw

    def spy(g, name, params=None, **kw):
        calls.append((name, len(params["rows"])))
        return real(g, name, params, **kw)

    client.rw = spy
    try:
        rep = backfill_entity_keys(client, graph)
    finally:
        client.rw = real
    assert rep["updated"] == n
    assert [c[1] for c in calls] == [BATCH, BATCH, 50]
    assert {c[0] for c in calls} == {"engram/backfill_entity_keys"}


def test_new_resolver_only_sees_legacy_entities_after_the_backfill(client, lg):
    eng = Engram(client, lg, HashEmbedder())
    before = eng.resolve_entity_ex("Auth-Gateway Service", "service")  # e2 has no keys yet: not a candidate
    assert before["created"] is True
    backfill_entity_keys(client, lg)
    hit = eng.resolve_entity_ex("auth gateway  service!", "service")  # same tokens as e2 (norm differs)
    assert hit["matched_by"] == "fulltext" and hit["id"] in ("e2", before["id"])
    assert hit["id"] == "e2"  # e2 is the older one


# -- reports ----------------------------------------------------------------------------------------------


def test_duplicate_norm_names_are_listed(client, empty_graph):
    g = client.graph(empty_graph)
    g.query("CREATE INDEX FOR (n:Entity) ON (n.norm_name)")
    g.query(
        "CREATE (:Entity {id: '1', norm_name: 'x'}), (:Entity {id: '2', norm_name: 'x'}),"
        " (:Entity {id: '3', norm_name: 'y'})"
    )
    assert duplicate_names(client, empty_graph) == [{"norm_name": "x", "n": 2}]


def test_near_duplicate_report(client, lg):
    pairs = near_duplicates(client, lg)
    got = {(p["younger_id"], p["older_id"]): p for p in pairs}
    assert set(got) == {("e2", "e1"), ("e4", "e3")}
    assert got[("e2", "e1")]["how"] == "fulltext" and round(got[("e2", "e1")]["jaccard"], 2) == 0.67
    assert got[("e4", "e3")]["how"] == "vector" and got[("e4", "e3")]["distance"] < 0.1
    assert {p["kind"] for p in pairs} == {"service", "tech"}  # Service 1 / Service 2 are not reported


def test_report_is_read_only(client, lg):
    near_duplicates(client, lg)
    assert props(client, lg, "e1") == [None, None]


def test_run_combines_backfill_report_and_constraint(client, lg):
    rep = run(client, lg, dry_run=False)
    assert rep["backfill"]["updated"] == 6
    assert rep["duplicate_names"] == [] and len(rep["near_duplicates"]) == 2
    assert rep["constraint"] == "OPERATIONAL"
    dry = run(client, lg, dry_run=True)
    assert dry["backfill"]["updated"] == 0 and dry["backfill"]["missing"] == 0  # already migrated


# -- CLI --------------------------------------------------------------------------------------------------


@pytest.fixture
def cli_env(client, monkeypatch):
    monkeypatch.setenv("FALKORDB_HOST", client.host)
    monkeypatch.setenv("FALKORDB_PORT", str(client.port))


@pytest.fixture
def tenant(client, cli_env):
    t = f"migr_{uuid.uuid4().hex[:10]}"
    g = graph_name(t)
    apply_schema(client, g)
    legacy(
        client,
        g,
        [("e1", "auth gateway", "service", 10, 1, 0), ("e2", "auth gateway service", "service", 20, 2, 0)],
    )
    yield t, g
    client.delete_graph(g)


def _run(*argv: str) -> int:
    with pytest.raises(SystemExit) as e:
        main(list(argv))
    return e.value.code


def test_cli_dry_run_then_apply(client, tenant, capsys):
    t, g = tenant
    assert _run("migrate", "entities", "--tenant", t, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "dry run" in out.lower() and "entities: 2" in out and "auth gateway service" in out
    assert props(client, g, "e1") == [None, None]
    assert _run("migrate", "entities", "--tenant", t, "--json") == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["backfill"]["updated"] == 2 and len(rep["near_duplicates"]) == 1
    assert props(client, g, "e1") == [["auth", "gateway"], ""]


def test_cli_requires_an_existing_tenant(cli_env):
    with pytest.raises(SystemExit) as e:
        main(["migrate", "entities", "--tenant", "no_such_tenant_zz"])
    assert "no_such_tenant_zz" in str(e.value)
    with pytest.raises(SystemExit):
        main(["migrate", "entities"])  # --tenant is mandatory: no default tenant for a migration


def test_cli_exits_nonzero_when_norm_names_collide(client, cli_env, capsys):
    t = f"migr_{uuid.uuid4().hex[:10]}"
    g = graph_name(t)
    try:
        c = client.graph(g)
        c.query("CREATE INDEX FOR (n:Entity) ON (n.norm_name)")
        c.query(
            "CREATE (:Entity {id: '1', norm_name: 'x', name: 'x', kind: 'thing'}),"
            " (:Entity {id: '2', norm_name: 'x', name: 'x', kind: 'thing'})"
        )
        assert _run("migrate", "entities", "--tenant", t) == 2
        assert "2 entities share the name 'x'" in capsys.readouterr().out
    finally:
        client.delete_graph(g)
