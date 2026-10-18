"""L7 family G (multi-tenancy) at toy size. Integration tests need FalkorDB on KNEWAT_TEST_DB_PORT (family G's port is 6365).

The ACL test creates and deletes its own Redis users and only runs when the port is 6365 (the one server where ACLs may be changed).
"""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest
import redis

from knewat.crucible.l7 import g as fam
from knewat.crucible.l7 import g_gen
from knewat.crucible.l7.g_arms import FArm, SFileArm, SSharedArm, tenant_predicate_sites
from tests.conftest import TEST_DB_HOST, TEST_DB_PORT


@pytest.fixture
def root():
    with tempfile.TemporaryDirectory(prefix="l7g-test-") as d:
        yield Path(d)


# ------------------------------------------------------------------------------------------------ generator
def test_world_is_seeded_and_shaped():
    w0, w0b, w1 = g_gen.tenant_world(0), g_gen.tenant_world(0), g_gen.tenant_world(1)
    assert w0 == w0b
    c = g_gen.counts(w0)
    assert (c["agents"], c["sources"], c["facts"], c["steps"], c["decisions"], c["handoffs"], c["tasks"]) == (
        5,
        10,
        100,
        30,
        10,
        5,
        10,
    )
    assert g_gen.max_depth(w0) <= 4 and g_gen.max_depth(w1) <= 4
    assert len(w0["secret"]) == 32 and int(w0["secret"], 16) >= 0 and w0["secret"] != w1["secret"]
    assert w0["canary"] == "canary_g0000" and any(
        f["id"] == w0["canary"] and w0["secret"] in f["text"] for f in w0["facts"]
    )
    # ids collide, values do not
    assert g_gen.fact_value(w0, "f0001") != g_gen.fact_value(w1, "f0001")
    assert "g0000" in g_gen.fact_value(w0, "f0001") and "g0001" in g_gen.fact_value(w1, "f0001")
    assert all(1 <= len(s["reads"]) <= 4 for s in w0["steps"]) and all(
        1 <= len(d["based_on"]) <= 3 for d in w0["decisions"]
    )


def test_ground_truth_helpers():
    w = g_gen.tenant_world(3)
    fid = next(f["id"] for f in w["facts"] if len(f["parents"]) == 2)
    anc = g_gen.ancestors(w, fid)
    assert all(p in anc for p in next(f for f in w["facts"] if f["id"] == fid)["parents"])
    assert g_gen.decisions_on(w, w["canary"]) == {"d10"}


# ------------------------------------------------------------------------------------------------ SQLite arms (no server)
@pytest.mark.parametrize("cls", [SFileArm, SSharedArm])
def test_sqlite_arms_isolated_and_correct(cls, root):
    arm = cls(root / cls.name)
    for k in range(4):
        arm.create_schema(k)
        arm.load(k)
    for a, b in ((0, 1), (2, 3), (3, 0)):
        pr = arm.probe(a, b)
        assert pr["leaked_total"] == 0 and all(pr["control"].values()), pr
    w = arm.worlds[2]
    assert arm.norm("q1", arm.q1(2, "f0007")) == [g_gen.fact_value(w, "f0007")]
    assert arm.norm("q3", arm.q3(2, "f0090")) == sorted(g_gen.ancestors(w, "f0090"))
    assert arm.norm("q2", arm.q2(2, w["decisions"][0]["based_on"][0])) == sorted(
        g_gen.decisions_on(w, w["decisions"][0]["based_on"][0])
    )
    assert arm.q4(2, "wnew", "f0001") and arm.norm("q1", arm.q1(2, "wnew")) == ["written wnew"]
    arm.close()


def test_sfile_modes_and_raw_channels(root):
    arm = SFileArm(root / "f")
    for k in range(2):
        arm.create_schema(k)
        arm.load(k)
    arm.cached = False  # open-per-request
    assert arm.norm("q1", arm.q1(1, "f0001")) == [g_gen.fact_value(arm.worlds[1], "f0001")]
    arm.cached = True
    arm.open_all(2)
    assert len(arm.conns) == 2
    # raw SQL: ATTACH leaks without an authorizer and is blocked with one
    c = sqlite3.connect(arm.path(0), isolation_level=None)
    c.execute(f"ATTACH DATABASE '{arm.path(1)}' AS o")
    assert arm.worlds[1]["secret"] in repr(
        c.execute("SELECT value FROM o.facts WHERE id = ?", (arm.worlds[1]["canary"],)).fetchall()
    )
    c.close()
    c = sqlite3.connect(arm.path(0), isolation_level=None)
    c.set_authorizer(fam._auth_attacker_file())
    with pytest.raises(sqlite3.DatabaseError):
        c.execute(f"ATTACH DATABASE '{arm.path(1)}' AS o")
    c.close()
    arm.close()


def test_shared_views_and_authorizer(root):
    arm = SSharedArm(root / "s")
    for k in range(2):
        arm.load(k)
    c = sqlite3.connect(arm.p, isolation_level=None)
    for t in fam.SHARED_TABLES:
        c.execute(f"CREATE TEMP VIEW {t} AS SELECT * FROM main.{t} WHERE tenant_id = 'g0000'")
    c.set_authorizer(
        fam._auth_views(
            {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
        )
    )
    assert c.execute("SELECT count(*) FROM facts WHERE id = ?", (arm.worlds[1]["canary"],)).fetchone()[0] == 0
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("SELECT value FROM main.facts")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DROP VIEW temp.facts")
    c.close()
    arm.close()
    assert tenant_predicate_sites()["S-file_tenant_predicates"] == 0


# ------------------------------------------------------------------------------------------------ FalkorDB (product services)
@pytest.fixture
def tenants(client):
    """Three loaded F tenants with throwaway names (k = 810000..), dropped afterwards."""
    f = FArm(TEST_DB_HOST, TEST_DB_PORT)
    ks = [810_000 + i for i in range(3)]
    try:
        for k in ks:
            f.create_schema(k)
            f.load(k)
        yield f, ks
    finally:
        for k in ks:
            f.client.delete_graph(f.gname(k))
        f.client.close()


def test_falkor_probe_zero_leak_and_controls(tenants):
    f, ks = tenants
    for a, b in ((ks[0], ks[1]), (ks[2], ks[0])):
        pr = f.probe(a, b)
        assert pr["leaked_total"] == 0, pr
        assert pr["control"] == {"canary_found": True, "keyword_found": True}, (
            pr
        )  # the services do work on A's own data
    assert f.norm("q1", f.q1(ks[1], "f0001")) == [g_gen.fact_value(f.worlds[ks[1]], "f0001")]
    assert f.norm("q3", f.q3(ks[1], "f0090")) == sorted(g_gen.ancestors(f.worlds[ks[1]], "f0090"))
    assert f.norm("q2", f.q2(ks[2], "f0001")) == sorted(g_gen.decisions_on(f.worlds[ks[2]], "f0001"))


def test_falkor_loader_asserts_ledger_counts(tenants):
    f, ks = tenants
    assert f.read_counts(ks[0]) == g_gen.counts(f.worlds[ks[0]])


@pytest.mark.skipif(TEST_DB_PORT != 6365, reason="ACL users may only be created on knewat-db-65")
def test_acl_user_blocks_other_tenant(tenants):
    f, ks = tenants
    r = redis.Redis(host=TEST_DB_HOST, port=TEST_DB_PORT, decode_responses=True)
    a, b = ks[0], ks[1]
    user = f"l7g_test_{uuid.uuid4().hex[:6]}"
    r.execute_command(
        "ACL", "SETUSER", user, "reset", "on", ">pw", f"~{f.gname(a)}", "+graph.query", "+graph.ro_query"
    )
    try:
        c = redis.Redis(
            host=TEST_DB_HOST, port=TEST_DB_PORT, decode_responses=True, username=user, password="pw"
        )
        assert c.execute_command("GRAPH.RO_QUERY", f.gname(a), "RETURN 1")
        with pytest.raises(redis.exceptions.NoPermissionError):
            c.execute_command("GRAPH.RO_QUERY", f.gname(b), "MATCH (n:Fact) RETURN n.value LIMIT 1")
        c.close()
        # without ACL the default user reads any key
        assert f.client.graph(f.gname(b)).ro_query("MATCH (n:Fact {id: 'f0001'}) RETURN n.value").result_set
    finally:
        r.execute_command("ACL", "DELUSER", user)
    assert not [x for x in r.execute_command("ACL", "LIST") if user in str(x)]
