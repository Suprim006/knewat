import random

from plexus.graph.schema import UNIQUE_LABELS, apply_schema, wait_for_constraints

ALL_LABELS = [
    "Agent", "Scope", "Session", "Episode", "Entity", "Fact", "Source", "Procedure",
    "Run", "Task", "Handoff", "Artifact", "Decision", "Step", "ToolCall", "Recall",
]  # fmt: skip

EXPECTED_RANGE = {(label, "id") for label in ALL_LABELS} | {
    ("Fact", "subject_id"),
    ("Fact", "predicate"),
    ("Fact", "valid_to"),
    ("Fact", "status"),
    ("Task", "status"),
    ("Step", "n"),
    ("ToolCall", "at"),
    ("Entity", "norm_name"),
    # P5 review Q4: MERGE keys / hot filters that used to fall back to label scans
    ("Step", "agent_id"),
    ("Source", "uri"),
    ("Scope", "name"),
    ("Procedure", "task_type"),
}
EXPECTED_FULLTEXT = {("Entity", "name"), ("Fact", "value"), ("Episode", "text")}
EXPECTED_VECTOR = {("Entity", "embedding"), ("Fact", "embedding"), ("Episode", "embedding")}


def _index_set(client, graph) -> dict[str, set[tuple[str, str]]]:
    found: dict[str, set[tuple[str, str]]] = {"RANGE": set(), "FULLTEXT": set(), "VECTOR": set()}
    for row in client.ro(graph, "schema/list_indexes"):
        for prop in row["properties"]:
            for kind in row["types"][prop]:
                found[kind].add((row["label"], prop))
        assert row["status"] == "OPERATIONAL"
    return found


def _constraints(client, graph) -> dict[str, str]:
    rows = client.ro(graph, "schema/list_constraints")
    return {r["label"]: r["status"] for r in rows if r["type"] == "UNIQUE" and r["properties"] == ["id"]}


def test_apply_schema_twice_is_idempotent(client, empty_graph):
    apply_schema(client, empty_graph)
    first = (_index_set(client, empty_graph), _constraints(client, empty_graph))
    apply_schema(client, empty_graph)  # must not raise
    second = (_index_set(client, empty_graph), _constraints(client, empty_graph))
    assert first == second


def test_all_five_constraints_operational(client, graph):
    assert set(UNIQUE_LABELS) == {"Task", "Fact", "Agent", "Decision", "Handoff"}
    status = _constraints(client, graph)
    assert status == {label: "OPERATIONAL" for label in UNIQUE_LABELS}
    wait_for_constraints(client, graph)  # already satisfied: returns immediately


def test_unique_constraint_actually_enforced(client, graph):
    import pytest
    from redis.exceptions import ResponseError

    g = client.graph(graph)
    g.query("CREATE (:Task {id: 'T1'})")
    with pytest.raises(ResponseError, match="(?i)unique|constraint"):
        g.query("CREATE (:Task {id: 'T1'})")
    g.query("CREATE (:Source {id: 'S1'}), (:Source {id: 'S1'})")  # Source is not constrained


def test_indexes_present(client, graph):
    found = _index_set(client, graph)
    assert EXPECTED_RANGE <= found["RANGE"]
    assert EXPECTED_FULLTEXT <= found["FULLTEXT"]
    assert EXPECTED_VECTOR <= found["VECTOR"]


def test_vector_indexes_are_384d_cosine(client, graph):
    vec = {}
    for row in client.ro(graph, "schema/list_indexes"):
        if "embedding" in row["options"]:
            vec[row["label"]] = row["options"]["embedding"]
    assert set(vec) == {"Entity", "Fact", "Episode"}
    for opts in vec.values():
        assert opts["dimension"] == 384 and opts["similarityFunction"] == "cosine"


def _unit_vec(rng: random.Random) -> list[float]:
    v = [rng.gauss(0, 1) for _ in range(384)]
    norm = sum(x * x for x in v) ** 0.5
    return [x / norm for x in v]


def test_vecf32_roundtrip_and_nearest_first_is_score_asc(client, graph):
    rng = random.Random(42)
    target, other1, other2 = _unit_vec(rng), _unit_vec(rng), _unit_vec(rng)
    g = client.graph(graph)
    for eid, vec in (("target", target), ("o1", other1), ("o2", other2)):
        g.query("CREATE (:Entity {id: $id, name: $id, embedding: vecf32($v)})", {"id": eid, "v": vec})

    stored = g.ro_query("MATCH (e:Entity {id: 'target'}) RETURN e.embedding AS v").result_set[0][0]
    assert len(stored) == 384
    assert max(abs(a - b) for a, b in zip(stored, target, strict=True)) < 1e-6  # float32 round-trip

    rows = g.ro_query(
        "CALL db.idx.vector.queryNodes('Entity', 'embedding', 3, vecf32($q)) YIELD node, score "
        "RETURN node.id AS id, score ORDER BY score ASC",
        {"q": target},
    ).result_set
    assert [r[0] for r in rows][0] == "target"
    assert rows[0][1] < 1e-4  # identical vector => cosine distance ~ 0 (so lower = nearer => ASC)
    assert all(r[1] > 0.1 for r in rows[1:])
    assert [r[1] for r in rows] == sorted(r[1] for r in rows)
