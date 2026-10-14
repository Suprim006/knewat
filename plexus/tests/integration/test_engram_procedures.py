from __future__ import annotations


def test_best_procedure_ranks_by_success_rate_then_runs(eng, client, graph):
    # alpha: 3/4 = .75, beta: 2/2 = 1.0, gamma: 1/1 = 1.0 (fewer runs than beta), delta: other task type
    for ok in (True, True, True, False):
        eng.log_procedure_run("alpha", "deploy", "a1", ok)
    for _ in range(2):
        eng.log_procedure_run("beta", "deploy", "a1", True)
    eng.log_procedure_run("gamma", "deploy", "a2", True)
    eng.log_procedure_run("delta", "migrate", "a1", True)

    ranked = eng.best_procedure("deploy")
    assert [r["name"] for r in ranked] == ["beta", "gamma", "alpha"]
    assert [(r["runs"], r["successes"]) for r in ranked] == [(2, 2), (1, 1), (4, 3)]
    assert ranked[2]["success_rate"] == 0.75
    assert [r["name"] for r in eng.best_procedure("deploy", min_runs=2)] == ["beta", "alpha"]
    assert eng.best_procedure("unknown") == []
    assert [r["name"] for r in eng.best_procedure("migrate")] == ["delta"]


def test_run_nodes_edges_and_task_link(eng, client, graph):
    client.graph(graph).query("CREATE (:Task {id:'t1', title:'ship', status:'open'})")
    r1 = eng.log_procedure_run(
        "rollout", "deploy", "a1", False, task_id="t1", notes="timeout", steps=["build", "push"]
    )
    r2 = eng.log_procedure_run("rollout", "deploy", "a2", True, task_id="missing-task")
    g = client.graph(graph)
    assert g.ro_query("MATCH (p:Procedure) RETURN count(p)").result_set == [[1]]
    row = g.ro_query(
        "MATCH (p:Procedure {name:'rollout'})-[:USED_IN]->(r:Run {id:$r})-[:BY]->(a:Agent),"
        " (r)-[:FOR]->(t:Task) "
        "RETURN a.id, t.id, r.success, r.notes, p.steps_json",
        {"r": r1},
    ).result_set
    assert row == [["a1", "t1", False, "timeout", '["build", "push"]']]
    # unknown task: run is recorded, no FOR edge
    assert g.ro_query("MATCH (:Run {id:$r})-[f:FOR]->() RETURN count(f)", {"r": r2}).result_set == [[0]]
    assert g.ro_query("MATCH (:Run {id:$r})-[:BY]->(a:Agent) RETURN a.id", {"r": r2}).result_set == [["a2"]]
