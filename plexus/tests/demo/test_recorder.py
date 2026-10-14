"""Recorder + replay: DUMP/RESTORE of a tenant graph round-trips, and the CLI wires it up."""

from __future__ import annotations

import json

import pytest

from plexus.demo.inventory import inventory
from plexus.demo.recorder import DUMP_NAME, META_NAME, list_recordings, record_run
from plexus.demo.replay import ReplayError, replay
from plexus.graph.tenancy import graph_name

from .conftest import rows


def test_record_then_replay_round_trips(client, scripted_run, demo_tenants, tmp_path):
    tenant, w = scripted_run
    meta = record_run(client, tenant, "unit-run", mode="scripted", world=w, root=tmp_path)
    assert (tmp_path / "unit-run" / DUMP_NAME).stat().st_size == meta["dump_bytes"] > 1000
    on_disk = json.loads((tmp_path / "unit-run" / META_NAME).read_text(encoding="utf-8"))
    assert on_disk["inventory"] == inventory(client, tenant)
    assert on_disk["steps"] == w.step and on_disk["faults"] == {"kill_builder": 15, "publish_v2": 20}
    assert [m["run"] for m in list_recordings(tmp_path)] == ["unit-run"]
    # the temporary rec_<run> copy is gone
    assert not client.db.connection.exists("rec_unit-run".replace("-", "_"))

    target = demo_tenants()
    res = replay(client, "unit-run", target, root=tmp_path)
    assert res["matches"] and res["inventory"] == on_disk["inventory"]

    # the restored graph is a working Plexus graph: same facts, edges, vectors and indexes
    q = "MATCH (f:Fact) RETURN f.predicate, f.value, f.status ORDER BY f.predicate, f.value"
    assert rows(client, target, q) == rows(client, tenant, q)
    assert rows(client, target, "MATCH (f:Fact) WHERE f.embedding IS NOT NULL RETURN count(f)")[0][0] > 0
    assert rows(client, target, "MATCH (:Task)-[:DEPENDS_ON]->(:Task) RETURN count(*)") == rows(
        client, tenant, "MATCH (:Task)-[:DEPENDS_ON]->(:Task) RETURN count(*)"
    )
    idx = client.graph(graph_name(target)).ro_query("CALL db.indexes()").result_set
    assert len(idx) == len(client.graph(graph_name(tenant)).ro_query("CALL db.indexes()").result_set) > 10


def test_replay_refuses_to_overwrite_without_reset(client, scripted_run, demo_tenants, tmp_path):
    tenant, w = scripted_run
    record_run(client, tenant, "again", world=w, root=tmp_path)
    target = demo_tenants()
    replay(client, "again", target, root=tmp_path)
    with pytest.raises(ReplayError):
        replay(client, "again", target, root=tmp_path)
    assert replay(client, "again", target, reset=True, root=tmp_path)["matches"]


def test_bad_run_names_are_rejected(client, tmp_path):
    with pytest.raises(ValueError):
        record_run(client, "x", "../evil", root=tmp_path)


def _committed_runs():
    from plexus.demo.scenario import recordings_dir

    return sorted(p.parent.name for p in recordings_dir().glob("*/meta.json"))


def test_committed_recordings_exist():
    runs = _committed_runs()
    assert "acme-scripted" in runs and "acme-claude-sonnet" in runs and "pilot-haiku" in runs


@pytest.mark.parametrize("run", _committed_runs())
def test_committed_recordings_replay_to_their_recorded_counts(client, demo_tenants, run):
    """Every recording shipped in demo_data/recordings restores on this FalkorDB and matches its meta.json."""
    from plexus.demo.recorder import load_meta

    meta = load_meta(run)
    tenant = demo_tenants()
    res = replay(client, run, tenant)
    assert res["matches"], (res["inventory"], meta["inventory"])
    assert res["inventory"]["total_nodes"] == meta["inventory"]["total_nodes"] > 0
    if meta["mode"] == "claude":
        assert meta["permission_denials"] == []
        assert not (meta["status"] == "aborted")
    # the restored graph answers the aha query: the builder is the claimer on the killed task, someone else reclaimed
    if run != "pilot-haiku":
        r = rows(
            client,
            tenant,
            "MATCH (a:Agent)-[c:CLAIMED]->(:Task {id:'t03-design-endpoints'}) RETURN a.id, c.reclaimed_from ORDER BY c.at",
        )
        assert r == [["builder", ""], ["researcher", "builder"]]
        assert rows(
            client,
            tenant,
            "MATCH (:Fact {predicate:'api_version', value:'v2'})-[:SUPERSEDES]->(o:Fact) RETURN o.value",
        ) == [["v1"]]
        assert rows(client, tenant, "MATCH (:Fact)-[:CONTRADICTS]->(:Fact) RETURN count(*)")[0][0] == 1
