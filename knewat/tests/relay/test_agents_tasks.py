import pytest

from plexus.relay import DuplicateTask, InvalidDag, UnknownReference


def _labels(client, graph, label):
    return client.graph(graph).ro_query(f"MATCH (n:{label}) RETURN count(n)").result_set[0][0]


def _edges(client, graph):
    q = "MATCH (a:Task)-[:DEPENDS_ON]->(b:Task) RETURN a.id, b.id"
    return sorted(tuple(r) for r in client.graph(graph).ro_query(q).result_set)


def test_register_agent_is_idempotent_and_updates(relay, client, graph):
    a = relay.register_agent("a1", "Planner", "planner", "claude-code")
    assert a == {"id": "a1", "name": "Planner", "role": "planner", "harness": "claude-code"}
    b = relay.register_agent("a1", "Planner 2", "lead", "hermes")
    assert b["name"] == "Planner 2" and b["harness"] == "hermes"
    assert _labels(client, graph, "Agent") == 1


def test_create_tasks_dag_defaults_and_edges(relay, client, graph):
    ids = relay.create_tasks(
        [
            {"id": "t1", "title": "design", "priority": 5},
            {"id": "t2", "title": "build", "depends_on": ["t1"]},
            {"id": "t3", "title": "test", "depends_on": ["t1", "t2"]},
        ]
    )
    assert ids == ["t1", "t2", "t3"]
    assert _edges(client, graph) == [("t2", "t1"), ("t3", "t1"), ("t3", "t2")]
    row = (
        client.graph(graph)
        .ro_query(
            "MATCH (t:Task {id:'t1'}) RETURN t.status, t.version, t.lease_until, t.claimed_by, t.priority, "
            "t.created_at, t.title"
        )
        .result_set[0]
    )
    assert row == ["open", 0, 0, "", 5, 1_000_000, "design"]


def test_create_tasks_generates_ids_and_allows_no_dependencies(relay, client, graph):
    ids = relay.create_tasks([{"title": "a"}, {"title": "b"}])
    assert len(ids) == 2 and len(set(ids)) == 2
    assert _labels(client, graph, "Task") == 2 and _edges(client, graph) == []


def test_create_tasks_can_depend_on_existing_task(relay, client, graph):
    relay.create_tasks([{"id": "root", "title": "r"}])
    relay.create_tasks([{"id": "leaf", "title": "l", "depends_on": ["root"]}])
    assert _edges(client, graph) == [("leaf", "root")]


def test_create_tasks_empty_is_noop(relay):
    assert relay.create_tasks([]) == []


@pytest.mark.parametrize(
    "tasks",
    [
        [{"id": "a", "title": "a", "depends_on": ["b"]}, {"id": "b", "title": "b", "depends_on": ["a"]}],
        [{"id": "a", "title": "a", "depends_on": ["a"]}],
        [
            {"id": "a", "title": "a", "depends_on": ["c"]},
            {"id": "b", "title": "b", "depends_on": ["a"]},
            {"id": "c", "title": "c", "depends_on": ["b"]},
        ],
        [{"id": "a", "title": "x"}, {"id": "a", "title": "y"}],
    ],
)
def test_create_tasks_rejects_cycles_and_duplicates_without_writing(relay, client, graph, tasks):
    with pytest.raises(InvalidDag):
        relay.create_tasks(tasks)
    assert _labels(client, graph, "Task") == 0


def test_create_tasks_rejects_more_than_500(relay, client, graph):
    with pytest.raises(InvalidDag):
        relay.create_tasks([{"title": str(i)} for i in range(501)])
    assert _labels(client, graph, "Task") == 0


def test_create_tasks_500_in_one_call(relay, client, graph):
    tasks = [{"id": f"t{i}", "title": "x", "depends_on": [f"t{i - 1}"] if i else []} for i in range(500)]
    relay.create_tasks(tasks)
    assert _labels(client, graph, "Task") == 500 and len(_edges(client, graph)) == 499


def test_create_tasks_existing_id_is_rejected_atomically(relay, client, graph):
    relay.create_tasks([{"id": "t1", "title": "one"}])
    with pytest.raises(DuplicateTask) as ei:
        relay.create_tasks([{"id": "n1", "title": "new"}, {"id": "t1", "title": "dup"}])
    assert ei.value.ids == ["t1"]
    assert _labels(client, graph, "Task") == 1  # n1 was not created


def test_create_tasks_unknown_dependency_is_rejected_atomically(relay, client, graph):
    with pytest.raises(UnknownReference) as ei:
        relay.create_tasks([{"id": "n1", "title": "new", "depends_on": ["ghost"]}])
    assert ei.value.ids == ["ghost"]
    assert _labels(client, graph, "Task") == 0
