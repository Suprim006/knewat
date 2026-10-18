import pytest

from knewat.relay import ClaimConflict, DuplicateArtifact, InvalidDag, UnknownReference

LEASE = 10_000


def _setup(relay, deps=False):
    relay.register_agent("a1", "A1", "builder", "test")
    relay.register_agent("a2", "A2", "builder", "test")
    tasks = [{"id": "t1", "title": "one"}]
    if deps:
        tasks.append({"id": "t2", "title": "two", "depends_on": ["t1"]})
    relay.create_tasks(tasks)
    return relay.claim_next_task("a1", LEASE)


def _art(client, graph, art_id=None):
    q = (
        "MATCH (x:Artifact)-[:PRODUCED_BY]->(a:Agent) "
        "RETURN x.id, x.kind, x.uri, x.hash, x.summary, x.task_id, a.id"
    )
    if art_id:
        q = q.replace("RETURN", "WHERE x.id = $id RETURN")
    return sorted(client.graph(graph).ro_query(q, {"id": art_id} if art_id else None).result_set)


def test_complete_marks_done_bumps_version_and_records_artifacts(relay, client, graph, clock):
    claim = _setup(relay)
    clock.advance(500)
    out = relay.complete_task(
        "a1", "t1", claim["version"],
        artifacts=[
            {"id": "x1", "kind": "file", "uri": "repo://src/app.py", "hash": "abc", "summary": "the app"},
            {"id": "x2", "kind": "note", "uri": "mem://n"},
        ],
    )  # fmt: skip
    assert out == {"id": "t1", "status": "done", "version": 2, "artifact_ids": ["x1", "x2"]}
    st = relay.task_status("t1")
    assert st["status"] == "done" and st["done_at"] == clock.t and st["version"] == 2
    assert _art(client, graph) == [
        ["x1", "file", "repo://src/app.py", "abc", "the app", "t1", "a1"],
        ["x2", "note", "mem://n", "", "", "t1", "a1"],
    ]


def test_complete_without_artifacts_and_generated_ids(relay, client, graph):
    claim = _setup(relay)
    out = relay.complete_task("a1", "t1", claim["version"])
    assert out["status"] == "done" and out["artifact_ids"] == []
    relay.register_agent("a3", "A3", "r", "t")
    relay.create_tasks([{"id": "t9", "title": "n"}])
    c2 = relay.claim_next_task("a3", LEASE)
    out2 = relay.complete_task("a3", "t9", c2["version"], artifacts=[{"kind": "k", "uri": "u"}])
    assert len(out2["artifact_ids"]) == 1 and len(_art(client, graph, out2["artifact_ids"][0])) == 1


def test_complete_unblocks_dependents(relay):
    claim = _setup(relay, deps=True)
    assert relay.claim_next_task("a2", LEASE) is None
    relay.complete_task("a1", "t1", claim["version"])
    assert relay.claim_next_task("a2", LEASE)["id"] == "t2"


def test_complete_with_stale_version_is_rejected_and_writes_nothing(relay, client, graph):
    claim = _setup(relay)
    with pytest.raises(ClaimConflict, match="stale version"):
        relay.complete_task(
            "a1", "t1", claim["version"] - 1, artifacts=[{"id": "x1", "kind": "k", "uri": "u"}]
        )
    st = relay.task_status("t1")
    assert st["status"] == "claimed" and st["version"] == claim["version"]
    assert _art(client, graph) == []


def test_complete_after_lease_reclaim_is_rejected_for_old_owner(relay, clock):
    claim = _setup(relay)
    clock.advance(LEASE + 1)
    second = relay.claim_next_task("a2", LEASE)
    assert second["reclaimed_from"] == "a1"
    with pytest.raises(ClaimConflict, match="claimed by a2"):
        relay.complete_task("a1", "t1", claim["version"])
    out = relay.complete_task("a2", "t1", second["version"])
    assert out["status"] == "done"


def test_complete_by_non_owner_and_double_complete_are_rejected(relay):
    claim = _setup(relay)
    with pytest.raises(ClaimConflict, match="claimed by a1"):
        relay.complete_task("a2", "t1", claim["version"])
    relay.complete_task("a1", "t1", claim["version"])
    with pytest.raises(ClaimConflict, match="not claimed"):
        relay.complete_task("a1", "t1", claim["version"] + 1)


def test_complete_open_or_unknown_task(relay):
    relay.register_agent("a1", "A1", "b", "t")
    relay.create_tasks([{"id": "t1", "title": "one"}])
    with pytest.raises(ClaimConflict, match="not claimed"):
        relay.complete_task("a1", "t1", 0)
    with pytest.raises(UnknownReference):
        relay.complete_task("a1", "nope", 0)


def test_duplicate_artifact_id_rejects_whole_call(relay, client, graph):
    claim = _setup(relay)
    relay.register_agent("a3", "A3", "r", "t")
    relay.create_tasks([{"id": "t9", "title": "n"}])
    c9 = relay.claim_next_task("a3", LEASE)
    relay.complete_task("a3", "t9", c9["version"], artifacts=[{"id": "x1", "kind": "k", "uri": "u"}])
    with pytest.raises(DuplicateArtifact):
        relay.complete_task("a1", "t1", claim["version"], artifacts=[{"id": "x1", "kind": "k", "uri": "u"}])
    assert relay.task_status("t1")["status"] == "claimed"
    with pytest.raises(InvalidDag):
        relay.complete_task(
            "a1", "t1", claim["version"], artifacts=[{"id": "d", "kind": "k"}, {"id": "d", "kind": "k"}]
        )


def test_fail_task_blocks_dependents_and_stores_reason(relay, client, graph):
    claim = _setup(relay, deps=True)
    out = relay.fail_task(
        "a1",
        "t1",
        claim["version"],
        artifacts=[{"id": "log1", "kind": "log", "uri": "file://l"}],
        reason="boom",
    )
    assert out["status"] == "failed" and out["version"] == 2
    st = relay.task_status("t1")
    assert st["status"] == "failed" and st["done_at"] > 0
    assert client.graph(graph).ro_query("MATCH (t:Task {id:'t1'}) RETURN t.fail_reason").result_set == [
        ["boom"]
    ]
    assert len(_art(client, graph)) == 1
    assert relay.claim_next_task("a2", LEASE) is None  # t2 is blocked by the failed t1
    assert relay.task_status("t2")["blocked_by"] == ["t1"]


def test_fail_task_stale_version_rejected(relay):
    claim = _setup(relay)
    with pytest.raises(ClaimConflict, match="stale version"):
        relay.fail_task("a1", "t1", 99)
    assert relay.task_status("t1")["status"] == "claimed" and claim["version"] == 1
