import pytest

from knewat.relay import UnknownReference

LEASE = 10_000


def _agents(relay, *names):
    for n in names:
        relay.register_agent(n, n.upper(), "builder", "test")


def _claimed_edges(client, graph, task_id):
    q = "MATCH (a:Agent)-[c:CLAIMED]->(:Task {id: $id}) RETURN a.id, c.at, c.lease_until, c.reclaimed_from"
    return sorted(client.graph(graph).ro_query(q, {"id": task_id}).result_set)


def test_claim_sets_fields_creates_edge_and_bumps_version(relay, client, graph, clock):
    _agents(relay, "a1")
    relay.create_tasks([{"id": "t1", "title": "one"}])
    got = relay.claim_next_task("a1", LEASE)
    assert got == {
        "id": "t1", "title": "one", "priority": 0, "version": 1,
        "lease_until": clock.t + LEASE, "claimed_by": "a1", "reclaimed_from": "",
    }  # fmt: skip
    st = relay.task_status("t1")
    assert st["status"] == "claimed" and st["claimed_by"] == "a1" and st["version"] == 1
    assert _claimed_edges(client, graph, "t1") == [["a1", clock.t, clock.t + LEASE, ""]]


def test_claim_returns_none_when_nothing_ready(relay):
    _agents(relay, "a1")
    assert relay.claim_next_task("a1", LEASE) is None
    relay.create_tasks([{"id": "t1", "title": "one"}])
    assert relay.claim_next_task("a1", LEASE)["id"] == "t1"
    assert relay.claim_next_task("a1", LEASE) is None  # already claimed, lease still valid


def test_claim_unknown_agent_raises(relay):
    relay.create_tasks([{"id": "t1", "title": "one"}])
    with pytest.raises(UnknownReference):
        relay.claim_next_task("ghost", LEASE)
    assert relay.task_status("t1")["status"] == "open"


def test_claim_order_priority_then_creation_time(relay, clock):
    _agents(relay, "a1")
    relay.create_tasks([{"id": "low", "title": "l", "priority": 1}])
    clock.advance(10)
    relay.create_tasks([{"id": "hi_late", "title": "h", "priority": 9}])
    clock.advance(10)
    relay.create_tasks([{"id": "hi_later", "title": "h", "priority": 9}])
    order = [relay.claim_next_task("a1", LEASE)["id"] for _ in range(3)]
    assert order == ["hi_late", "hi_later", "low"]


def test_task_with_unfinished_dependency_is_never_claimed(relay, client, graph):
    _agents(relay, "a1", "a2")
    relay.create_tasks(
        [
            {"id": "a", "title": "a", "priority": 1},
            {"id": "b", "title": "b", "priority": 100, "depends_on": ["a"]},  # higher priority but blocked
        ]
    )
    assert [t["id"] for t in relay.ready_tasks()] == ["a"]
    assert relay.claim_next_task("a1", LEASE)["id"] == "a"
    # a is claimed (not done): b stays blocked, nothing for a2
    assert relay.claim_next_task("a2", LEASE) is None
    assert relay.task_status("b")["blocked_by"] == ["a"]
    # mark a done directly (complete_task has its own tests) -> b becomes ready
    client.graph(graph).query("MATCH (t:Task {id:'a'}) SET t.status = 'done'")
    assert [t["id"] for t in relay.ready_tasks()] == ["b"]
    assert relay.claim_next_task("a2", LEASE)["id"] == "b"


def test_failed_dependency_blocks_forever(relay, client, graph):
    _agents(relay, "a1")
    relay.create_tasks([{"id": "a", "title": "a"}, {"id": "b", "title": "b", "depends_on": ["a"]}])
    client.graph(graph).query("MATCH (t:Task {id:'a'}) SET t.status = 'failed'")
    assert relay.claim_next_task("a1", LEASE) is None
    assert relay.ready_tasks() == []


def test_diamond_dag_claim_order(relay, client, graph):
    _agents(relay, "a1")
    relay.create_tasks(
        [
            {"id": "root", "title": "r"},
            {"id": "l", "title": "l", "depends_on": ["root"]},
            {"id": "r", "title": "r", "depends_on": ["root"]},
            {"id": "join", "title": "j", "depends_on": ["l", "r"]},
        ]
    )
    done = client.graph(graph)
    assert relay.claim_next_task("a1", LEASE)["id"] == "root"
    done.query("MATCH (t:Task {id:'root'}) SET t.status = 'done'")
    first = relay.claim_next_task("a1", LEASE)["id"]
    second = relay.claim_next_task("a1", LEASE)["id"]
    assert {first, second} == {"l", "r"}
    assert relay.claim_next_task("a1", LEASE) is None  # join still blocked: l, r are claimed, not done
    done.query("MATCH (t:Task) WHERE t.id IN ['l','r'] SET t.status = 'done'")
    assert relay.claim_next_task("a1", LEASE)["id"] == "join"


def test_expired_lease_is_reclaimed_by_another_agent(relay, client, graph, clock):
    _agents(relay, "a1", "a2")
    relay.create_tasks([{"id": "t1", "title": "one"}])
    first = relay.claim_next_task("a1", LEASE)
    assert first["reclaimed_from"] == ""
    clock.advance(LEASE)  # lease_until == now: not yet expired (strictly less-than)
    assert relay.claim_next_task("a2", LEASE) is None
    clock.advance(1)
    second = relay.claim_next_task("a2", LEASE)
    assert second["id"] == "t1" and second["claimed_by"] == "a2"
    assert second["reclaimed_from"] == "a1" and second["version"] == 2
    edges = _claimed_edges(client, graph, "t1")
    assert [(e[0], e[3]) for e in edges] == [("a1", ""), ("a2", "a1")]
    # the old owner can no longer heartbeat it
    assert relay.heartbeat("a1", "t1", LEASE) is False


def test_heartbeat_extends_lease_for_owner_only(relay, clock):
    _agents(relay, "a1", "a2")
    relay.create_tasks([{"id": "t1", "title": "one"}])
    relay.claim_next_task("a1", LEASE)
    assert relay.heartbeat("a2", "t1", LEASE) is False  # non-owner rejected
    assert relay.task_status("t1")["lease_until"] == clock.t + LEASE
    clock.advance(LEASE - 1)
    assert relay.heartbeat("a1", "t1", LEASE) is True
    assert relay.task_status("t1")["lease_until"] == clock.t + LEASE
    clock.advance(LEASE - 1)  # past the original lease but within the extended one
    assert relay.claim_next_task("a2", LEASE) is None


def test_heartbeat_on_unclaimed_or_unknown_task_is_false(relay):
    _agents(relay, "a1")
    relay.create_tasks([{"id": "t1", "title": "one"}])
    assert relay.heartbeat("a1", "t1", LEASE) is False  # open, not claimed
    assert relay.heartbeat("a1", "nope", LEASE) is False


def test_task_status_unknown_is_none(relay):
    assert relay.task_status("nope") is None


def test_lease_ms_must_be_positive(relay):
    _agents(relay, "a1")
    with pytest.raises(ValueError):
        relay.claim_next_task("a1", 0)
    with pytest.raises(ValueError):
        relay.heartbeat("a1", "t", -5)
