import pytest

from plexus.relay import InvalidDag, UnknownReference

LEASE = 10_000


def _fact(client, graph, fid):
    client.graph(graph).query("CREATE (:Fact {id: $id, value: 'v', created_at: 1})", {"id": fid})


def _count(client, graph, label):
    return client.graph(graph).ro_query(f"MATCH (n:{label}) RETURN count(n)").result_set[0][0]


def _rels(client, graph, rel):
    return client.graph(graph).ro_query(f"MATCH ()-[r:{rel}]->() RETURN count(r)").result_set[0][0]


@pytest.fixture
def world(relay, client, graph):
    for a in ("planner", "builder", "reviewer"):
        relay.register_agent(a, a, a, "test")
    relay.create_tasks([{"id": "t1", "title": "spec"}, {"id": "t2", "title": "build", "depends_on": ["t1"]}])
    claim = relay.claim_next_task("planner", LEASE)
    done = relay.complete_task(
        "planner",
        "t1",
        claim["version"],
        artifacts=[
            {"id": "x1", "kind": "doc", "uri": "doc://spec"},
            {"id": "x2", "kind": "doc", "uri": "d2"},
        ],
    )
    _fact(client, graph, "f1")
    _fact(client, graph, "f2")
    return done


def test_handoff_creates_node_edges_and_carries(relay, client, graph, world, clock):
    hid = relay.handoff("planner", "builder", "t2", "spec is ready", ["x1", "x2"], ["f1"])
    q = (
        "MATCH (h:Handoff {id: $id})-[:FROM]->(f:Agent), (h)-[:TO]->(to:Agent), (h)-[:FOR]->(t:Task) "
        "OPTIONAL MATCH (h)-[:CARRIES]->(c) "
        "RETURN h.note, h.at, f.id, to.id, t.id, collect(c.id)"
    )
    note, at, frm, to, task, carried = client.graph(graph).ro_query(q, {"id": hid}).result_set[0]
    assert (note, at, frm, to, task) == ("spec is ready", clock.t, "planner", "builder", "t2")
    assert sorted(carried) == ["f1", "x1", "x2"]


def test_handoff_without_payload_and_duplicate_ids_collapse(relay, client, graph, world):
    relay.handoff("planner", "builder", "t2", "just a note")
    relay.handoff("planner", "builder", "t2", "dups", ["x1", "x1"], ["f1", "f1"])
    assert _count(client, graph, "Handoff") == 2 and _rels(client, graph, "CARRIES") == 2


@pytest.mark.parametrize(
    ("kwargs", "kind"),
    [
        ({"artifact_ids": ["x1", "ghost"]}, "artifact"),
        ({"fact_ids": ["f1", "ghost"]}, "fact"),
        ({"to_agent": "ghost"}, "agent"),
        ({"task_id": "ghost"}, "task"),
    ],
)
def test_handoff_with_unknown_reference_writes_nothing(relay, client, graph, world, kwargs, kind):
    args = {"from_agent": "planner", "to_agent": "builder", "task_id": "t2", "note": "n", **kwargs}
    with pytest.raises(UnknownReference) as ei:
        relay.handoff(**args)
    assert ei.value.kind == kind
    assert _count(client, graph, "Handoff") == 0 and _rels(client, graph, "CARRIES") == 0


def test_verify_artifact_records_edge_and_flags_self_verification(relay, client, graph, world):
    out = relay.verify_artifact("reviewer", "x1")
    assert out == {"artifact": "x1", "agent": "reviewer", "independent": True}
    relay.verify_artifact("reviewer", "x1")  # idempotent
    assert _rels(client, graph, "VERIFIED_BY") == 1
    assert relay.verify_artifact("planner", "x1")["independent"] is False  # planner produced x1
    assert _rels(client, graph, "VERIFIED_BY") == 2
    with pytest.raises(UnknownReference):
        relay.verify_artifact("reviewer", "ghost")
    with pytest.raises(UnknownReference):
        relay.verify_artifact("ghost", "x1")


def test_record_decision_based_on_facts(relay, client, graph, world, clock):
    did = relay.record_decision("builder", "t2", "use FastAPI", ["f1", "f2"])
    q = (
        "MATCH (a:Agent)-[:DECIDED]->(d:Decision {id: $id})-[:FOR]->(t:Task) "
        "OPTIONAL MATCH (d)-[:BASED_ON]->(f:Fact) RETURN a.id, t.id, d.text, d.at, collect(f.id)"
    )
    agent, task, text, at, facts = client.graph(graph).ro_query(q, {"id": did}).result_set[0]
    assert (agent, task, text, at) == ("builder", "t2", "use FastAPI", clock.t)
    assert sorted(facts) == ["f1", "f2"]


def test_record_decision_without_facts(relay, client, graph, world):
    relay.record_decision("builder", "t2", "no evidence needed")
    assert _count(client, graph, "Decision") == 1 and _rels(client, graph, "BASED_ON") == 0


def test_decision_with_unknown_fact_creates_no_decision_node(relay, client, graph, world):
    with pytest.raises(UnknownReference) as ei:
        relay.record_decision("builder", "t2", "x", ["f1", "ghost-1", "ghost-2"])
    assert ei.value.kind == "fact" and ei.value.ids == ["ghost-1", "ghost-2"]
    assert _count(client, graph, "Decision") == 0
    assert _rels(client, graph, "BASED_ON") == 0 and _rels(client, graph, "DECIDED") == 0
    for_edges = client.graph(graph).ro_query("MATCH (n)-[r:FOR]->() RETURN labels(n)[0], count(r)").result_set
    assert [r for r in for_edges if r[0] != "Artifact"] == []  # no Decision/Handoff -[:FOR]-> edge either


def test_decision_with_unknown_agent_or_task(relay, client, graph, world):
    with pytest.raises(UnknownReference) as ei:
        relay.record_decision("ghost", "t2", "x", ["f1"])
    assert ei.value.kind == "agent"
    with pytest.raises(UnknownReference) as ei:
        relay.record_decision("builder", "ghost", "x", ["f1"])
    assert ei.value.kind == "task"
    assert _count(client, graph, "Decision") == 0


def test_reference_lists_are_bounded(relay, world):
    with pytest.raises(InvalidDag):
        relay.record_decision("builder", "t2", "x", [f"f{i}" for i in range(101)])


def test_blocked_by_failure_three_level_dag(relay):
    relay.register_agent("a1", "a1", "b", "t")
    relay.create_tasks(
        [
            {"id": "root", "title": "r", "priority": 9},
            {"id": "mid1", "title": "m1", "depends_on": ["root"]},
            {"id": "mid2", "title": "m2", "depends_on": ["root"]},
            {"id": "leaf", "title": "l", "depends_on": ["mid1", "mid2"]},  # diamond: two paths to root
            {"id": "other_root", "title": "o"},
            {"id": "other_leaf", "title": "ol", "depends_on": ["other_root"]},
        ]
    )
    claim = relay.claim_next_task("a1", LEASE)
    assert claim["id"] == "root"  # highest priority
    relay.fail_task("a1", "root", claim["version"], reason="broken")
    assert relay.blocked_by_failure("root") == ["mid1", "mid2", "leaf"]
    assert relay.blocked_by_failure("mid1") == ["leaf"]
    assert relay.blocked_by_failure("leaf") == []
    assert relay.blocked_by_failure("other_root") == ["other_leaf"]
    assert relay.blocked_by_failure("ghost") == []


def test_blocked_by_failure_excludes_done_tasks(relay, client, graph):
    relay.create_tasks(
        [
            {"id": "a", "title": "a"},
            {"id": "b", "title": "b", "depends_on": ["a"]},
            {"id": "c", "title": "c", "depends_on": ["b"]},
        ]
    )
    client.graph(graph).query("MATCH (t:Task {id:'b'}) SET t.status = 'done'")
    assert relay.blocked_by_failure("a") == ["c"]
