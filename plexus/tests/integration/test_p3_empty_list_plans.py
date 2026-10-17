"""FIX-P3: plan-shape regression for ``x.id IN $list`` with an EMPTY list.

On FalkorDB 6.0.2 ``OPTIONAL MATCH (x:L) WHERE x.id IN $list`` with ``$list = []`` is planned as a Node By
Index Scan over the WHOLE ``L.id`` index (every node of the label is read); a non-empty list is a seek. The
queries use ``UNWIND CASE WHEN size($l) = 0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})``
instead, which seeks for both.

PROFILE really executes the write queries, so everything runs on one throw-away graph with ``N`` nodes per
touched label (indexed on ``id``); each test uses fresh ids for what it writes.
"""

from __future__ import annotations

import itertools

import pytest
from tests.plan_util import profile_ops

from plexus.graph.tenancy import test_graph_name

N = 3000  # nodes per label: the broken plan reads all N
LABELS = ("Artifact", "Fact", "Task", "Decision", "Handoff", "Scope", "Source", "Episode")
LIMIT = 50  # an index seek reads a handful of entries, never the whole index
_seq = itertools.count()


def _scan_records(ops):
    """Max records over the id-index operations (empty when the plan has none)."""
    return max((o.records for o in ops if "Index Scan" in o.name), default=0)


@pytest.fixture(scope="module")
def g(client):
    name = test_graph_name()
    gr = client.graph(name)
    for lab in LABELS:
        gr.query(f"CREATE INDEX FOR (n:{lab}) ON (n.id)")
        for start in range(0, N, 1000):
            gr.query(
                f"UNWIND range($a, $b) AS i CREATE (:{lab} {{id: '{lab[0]}' + toString(i), created_at: 1}})",
                {"a": start, "b": start + 999},
            )
    gr.query(
        "CREATE (:Agent {id: 'a1', name: 'a1'}), (:Agent {id: 'a2', name: 'a2'}), (:Step {id: 'S1', at: 5})"
    )
    gr.query("CREATE INDEX FOR (n:Agent) ON (n.id)")
    gr.query("CREATE INDEX FOR (n:Step) ON (n.id)")
    gr.query("CREATE INDEX FOR (n:Scope) ON (n.kind)")
    yield name
    client.delete_graph(name)


def claimed_task(client, g) -> str:
    tid = f"CT{next(_seq)}"
    client.graph(g).query(
        "CREATE (:Task {id: $id, status: 'claimed', claimed_by: 'a1', version: 3, lease_until: 0,"
        " done_at: 0})",
        {"id": tid},
    )
    return tid


def art(i):
    return {"id": i, "kind": "k", "uri": "u", "hash": "", "summary": ""}


def fresh(prefix="N") -> str:
    return f"{prefix}{next(_seq)}_new"


# -- param builders: (empty-list params, non-empty seek params) ---------------------------------------------


def finish_params(client, g, *, empty: bool, fail: bool = False):
    tid = claimed_task(client, g)
    aid = [] if empty else ["A5"]
    p = {"agent": "a1", "task": tid, "expected_version": 3, "artifacts": [], "artifact_ids": aid, "now": 10}
    return {**p, "reason": "r"} if fail else p


def create_tasks_params(client, g, *, empty: bool):
    t = fresh("T")
    edges = [] if empty else [{"i": 0, "j": -1, "dep": "T5"}]
    return {
        "tasks": [{"id": t, "title": "t", "priority": 0, "seq": 0}],
        "edges": edges,
        "ids": [t],
        "ext_dep_ids": [] if empty else ["T5"],
        "now": 10,
    }


def handoff_params(client, g, *, empty: bool):
    t = claimed_task(client, g)
    return {
        "id": fresh("H"),
        "from_agent": "a1",
        "to_agent": "a2",
        "task": t,
        "note": "n",
        "artifact_ids": [] if empty else ["A5"],
        "fact_ids": [] if empty else ["F5"],
        "step_id": "",
        "now": 10,
    }


def decision_params(client, g, *, empty: bool):
    t = claimed_task(client, g)
    return {
        "id": fresh("D"),
        "agent": "a1",
        "task": t,
        "text": "x",
        "fact_ids": [] if empty else ["F5"],
        "step_id": "",
        "now": 10,
    }


def link_step_params(client, g, *, empty: bool):
    return {
        "step_id": "S1",
        "read_ids": [] if empty else ["F5"],
        "wrote_ids": [] if empty else ["F6", "D7", "H8", "T9"],
        "via": "recall",
    }


def recall_params(client, g, *, empty: bool):
    return {
        "recall_id": fresh("R"),
        "agent_id": "a1",
        "step_id": "",
        "query": "q",
        "scope_id": "",
        "k": 5,
        "now": 10,
        "fact_ids": [] if empty else ["F5"],
        "results": [],
        "entities": [],
        "separation": False,
    }


def derive_params(client, g, *, empty: bool):
    return {"fact_id": "F1", "from_ids": [] if empty else ["S5", "E6", "F7"]}


def scope_params(client, g, *, empty: bool):
    return {
        "kind": "project",
        "name": fresh("scope"),
        "scope_id": fresh("SC"),
        "inherits": [] if empty else ["S5", "S6"],
        "now": 10,
    }


def fail_params(client, g, *, empty: bool):
    return finish_params(client, g, empty=empty, fail=True)


CASES = {
    "relay/complete_task": finish_params,
    "relay/fail_task": fail_params,
    "relay/create_tasks": create_tasks_params,
    "relay/handoff": handoff_params,
    "relay/record_decision": decision_params,
    "lineage/link_step": link_step_params,
    "lineage/record_recall": recall_params,
    "lineage/link_derived": derive_params,
    "engram/create_scope": scope_params,
}


@pytest.mark.parametrize("query", CASES)
def test_empty_list_does_not_scan_the_id_index(client, g, query):
    ops = profile_ops(client, g, query, CASES[query](client, g, empty=True))
    worst = _scan_records(ops)
    assert worst < LIMIT, f"{query}: empty list scans the index ({worst} records)\n" + "\n".join(
        map(str, ops)
    )


@pytest.mark.parametrize("query", CASES)
def test_non_empty_list_is_still_a_seek(client, g, query):
    ops = profile_ops(client, g, query, CASES[query](client, g, empty=False))
    worst = _scan_records(ops)
    assert worst < LIMIT, f"{query}: non-empty list scans the index ({worst} records)\n" + "\n".join(
        map(str, ops)
    )


# -- behaviour is unchanged ---------------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["relay/complete_task", "relay/fail_task"])
def test_finish_with_no_artifacts_still_completes_and_bad_guard_rejects(client, g, query):
    fail = query == "relay/fail_task"
    p = finish_params(client, g, empty=True, fail=fail)
    rows = client.rw(g, query, p)
    assert len(rows) == 1 and rows[0]["version"] == 4
    # an artifact id that already exists rejects the whole call
    p = finish_params(client, g, empty=False, fail=fail)
    assert len(client.rw(g, query, p)) == 0


def test_finish_with_new_artifact_ids_writes_them(client, g):
    p = finish_params(client, g, empty=True)
    p["artifacts"] = [art(fresh("A")), art(fresh("A"))]
    p["artifact_ids"] = [a["id"] for a in p["artifacts"]]
    res = client.rw(g, "relay/complete_task", p)
    assert len(res) == 1
    assert res.stats.get("nodes_created") == 2


def test_create_tasks_without_external_deps_still_creates(client, g):
    res = client.rw(g, "relay/create_tasks", create_tasks_params(client, g, empty=True))
    assert res.stats.get("nodes_created") == 1


def test_create_tasks_with_existing_external_dep_creates_the_edge(client, g):
    res = client.rw(g, "relay/create_tasks", create_tasks_params(client, g, empty=False))
    assert res.stats.get("nodes_created") == 1 and res.stats.get("relationships_created") == 1


def test_create_tasks_bad_external_dep_or_existing_id_writes_nothing(client, g):
    p = create_tasks_params(client, g, empty=False)
    p["ext_dep_ids"], p["edges"][0]["dep"] = ["nope"], "nope"
    assert client.rw(g, "relay/create_tasks", p).stats.get("nodes_created", 0) == 0
    p = create_tasks_params(client, g, empty=True)
    p["ids"] = ["T5"]  # already exists
    assert client.rw(g, "relay/create_tasks", p).stats.get("nodes_created", 0) == 0


def test_handoff_with_only_facts_or_nothing_writes_and_bad_id_rejects(client, g):
    p = handoff_params(client, g, empty=True)
    assert len(client.rw(g, "relay/handoff", p)) == 1
    p = handoff_params(client, g, empty=True)
    p["fact_ids"] = ["F5", "F6"]
    res = client.rw(g, "relay/handoff", p)
    assert len(res) == 1 and res.stats.get("relationships_created") == 5  # FROM TO FOR + 2 CARRIES
    p = handoff_params(client, g, empty=True)
    p["fact_ids"] = ["F5", "nope"]
    assert len(client.rw(g, "relay/handoff", p)) == 0
    p = handoff_params(client, g, empty=True)
    p["artifact_ids"] = ["nope"]
    assert len(client.rw(g, "relay/handoff", p)) == 0


def test_handoff_unknown_step_is_best_effort(client, g):
    p = handoff_params(client, g, empty=True)
    p["step_id"] = "no-such-step"
    res = client.rw(g, "relay/handoff", p)
    assert (
        len(res) == 1 and res.stats.get("nodes_created") == 1 and res.stats.get("relationships_created") == 3
    )


def test_record_decision_with_no_facts_writes_and_bad_fact_rejects(client, g):
    assert len(client.rw(g, "relay/record_decision", decision_params(client, g, empty=True))) == 1
    p = decision_params(client, g, empty=False)
    res = client.rw(g, "relay/record_decision", p)
    assert len(res) == 1 and res.stats.get("relationships_created") == 3  # DECIDED FOR BASED_ON
    p["fact_ids"], p["id"] = ["F5", "nope"], fresh("D")
    assert len(client.rw(g, "relay/record_decision", p)) == 0


def test_record_decision_unknown_step_is_best_effort(client, g):
    p = decision_params(client, g, empty=True)
    p["step_id"] = "no-such-step"
    res = client.rw(g, "relay/record_decision", p)
    assert len(res) == 1 and res.stats.get("relationships_created") == 2


def test_link_step_empty_wrote_ids_links_reads_and_bad_id_rejects(client, g):
    p = link_step_params(client, g, empty=True)
    p["read_ids"] = ["F11", "F12"]
    res = client.rw(g, "lineage/link_step", p)
    assert res[0]["n_read"] == 2 and res[0]["n_wrote"] == 0
    p["wrote_ids"] = ["F13", "D14", "H15", "T16"]
    res = client.rw(g, "lineage/link_step", p)
    assert res[0]["n_read"] == 2 and res[0]["n_wrote"] == 4
    for bad in (
        {"read_ids": ["F11", "nope"], "wrote_ids": []},
        {"read_ids": [], "wrote_ids": ["F13", "nope"]},
    ):
        assert len(client.rw(g, "lineage/link_step", {**p, **bad})) == 0
    res = client.rw(g, "lineage/link_step", {**p, "read_ids": [], "wrote_ids": []})
    assert res[0]["n_read"] == 0 and res[0]["n_wrote"] == 0


def test_record_recall_empty_facts_writes_and_bad_id_rejects(client, g):
    assert client.rw(g, "lineage/record_recall", recall_params(client, g, empty=True))[0]["returned"] == 0
    p = recall_params(client, g, empty=False)
    assert client.rw(g, "lineage/record_recall", p)[0]["returned"] == 1
    p["fact_ids"], p["recall_id"] = ["F5", "nope"], fresh("R")
    assert len(client.rw(g, "lineage/record_recall", p)) == 0


def test_link_derived_links_and_bad_id_rejects(client, g):
    p = derive_params(client, g, empty=False)
    assert client.rw(g, "lineage/link_derived", p)[0]["linked"] == 3
    assert len(client.rw(g, "lineage/link_derived", {**p, "from_ids": ["S5", "nope"]})) == 0
    assert len(client.rw(g, "lineage/link_derived", {**p, "fact_id": "nope"})) == 0
    # the service never passes an empty list; the query still behaves (links nothing, returns the fact)
    assert client.rw(g, "lineage/link_derived", {**p, "from_ids": []})[0]["linked"] == 0


def test_create_scope_without_parents_still_creates_and_bad_parent_rejects(client, g):
    p = scope_params(client, g, empty=True)
    assert len(client.rw(g, "engram/create_scope", p)) == 1
    p = scope_params(client, g, empty=False)
    res = client.rw(g, "engram/create_scope", p)
    assert len(res) == 1 and res.stats.get("relationships_created") == 2
    p = scope_params(client, g, empty=False)
    p["inherits"] = ["S5", "nope"]
    assert len(client.rw(g, "engram/create_scope", p)) == 0
