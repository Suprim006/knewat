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
