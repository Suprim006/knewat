"""P5-fix Q4: lookups by Step.agent_id, Source.uri, Scope.name, Procedure.task_type must be indexed."""

from __future__ import annotations

from tests.plan_util import BIG, explain_lines, max_records, profile_ops, seed_steps


def _assert_small(ops, limit=BIG):
    worst = max_records(ops)
    assert worst.records < limit, "label-wide enumeration: " + str(worst) + "\n" + "\n".join(map(str, ops))


def _no_label_scan(client, graph, query, params, label):
    lines = explain_lines(client, graph, query, params)
    scans = [ln for ln in lines if ln.startswith("Node By Label Scan") and f":{label})" in ln]
    assert not scans, f"{query} scans every {label}:\n" + "\n".join(lines)


def test_q4_record_step_uses_agent_index(client, graph):
    seed_steps(client, graph)
    params = {"agent_id": "ag3", "step_id": "new", "n": -1, "at": 9}
    _assert_small(profile_ops(client, graph, "lineage/record_step", params), limit=100)  # 20 steps per agent


def test_q4_knew_at_uses_agent_index(client, graph):
    seed_steps(client, graph)
    params = {"agent_id": "ag3", "n": 50, "limit": 10}
    _assert_small(profile_ops(client, graph, "lineage/knew_at", params), limit=100)


def test_q4_create_source_uses_uri_index(client, graph):
    params = {"source_id": "x", "uri": "u", "kind": "doc", "trust": 0.5, "title": "", "text": "", "now": 1}
    _no_label_scan(client, graph, "lineage/create_source", params, "Source")


def test_q4_create_scope_uses_name_index(client, graph):
    params = {"kind": "user", "name": "n", "scope_id": "x", "inherits": [], "now": 1}
    _no_label_scan(client, graph, "engram/create_scope", params, "Scope")


def test_q4_procedure_lookups_use_an_index(client, graph):
    run = {
        "procedure_name": "n",
        "task_type": "t",
        "procedure_id": "p",
        "steps_json": "[]",
        "run_id": "r",
        "agent_id": "a",
        "task_id": "",
        "success": True,
        "notes": "",
        "now": 1,
    }
    _no_label_scan(client, graph, "engram/log_procedure_run", run, "Procedure")
    _no_label_scan(
        client, graph, "engram/best_procedure", {"task_type": "t", "min_runs": 1, "limit": 5}, "Procedure"
    )
