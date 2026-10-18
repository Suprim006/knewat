"""``plexus demo ablation``: copy a tenant, cut the edges in the copy, probe both side by side."""

from __future__ import annotations

import json

import pytest

from plexus.cli import main
from plexus.demo.ablation import STRIPPED, run_ablation
from plexus.demo.inventory import inventory
from plexus.graph.tenancy import graph_name


def _run(*argv: str) -> int:
    with pytest.raises(SystemExit) as e:
        main(list(argv))
    return e.value.code


@pytest.fixture
def cli_env(monkeypatch):
    from ..conftest import TEST_DB_HOST, TEST_DB_PORT

    monkeypatch.setenv("FALKORDB_HOST", TEST_DB_HOST)
    monkeypatch.setenv("FALKORDB_PORT", str(TEST_DB_PORT))


@pytest.fixture
def ablated_cleanup(client):
    made: list[str] = []
    yield made
    for t in made:
        client.delete_graph(graph_name(t))


def edges(client, tenant: str) -> dict[str, int]:
    return inventory(client, tenant)["edges"]


def test_ablation_breaks_the_edge_features_and_nothing_else(client, scripted_run, ablated_cleanup, capsys):
    tenant, _ = scripted_run
    ablated_cleanup.append(tenant + "_ablated")
    before = inventory(client, tenant)

    rep = run_ablation(client, tenant, log=lambda _m: None)

    # the original tenant was not written
    assert inventory(client, tenant) == before and rep.original_untouched
    # the copy lost exactly the four edge types, and only those
    abl = edges(client, tenant + "_ablated")
    for t in STRIPPED:
        assert abl.get(t, 0) == 0
        assert rep.edges_deleted[t] == before["edges"].get(t, 0) > 0
    for t, n in before["edges"].items():
        if t not in STRIPPED:
            assert abl.get(t, 0) == n, t
    assert inventory(client, tenant + "_ablated")["nodes"] == before["nodes"]
    # scratch copies are gone
    assert not [g for g in client.db.list_graphs() if g.startswith(graph_name(tenant)) and "_abl_" in g]
    # the verdicts
    by = {r.feature: r for r in rep.rows}
    assert {r.feature for r in rep.needing if r.broken} == {
        "why(decision)",
        "knew_at(agent, step)",
        "who_knew(fact)",
        "dependency-aware claim",
        "blocked_by_failure(task)",
        "forget by source (cascade)",
    }
    assert {r.feature for r in rep.controls} == {"exclusive claims", "supersession history"}
    assert all(r.intact_ok for r in rep.rows) and all(r.ablated_ok for r in rep.controls)
    assert "0 with unmet dependencies" in by["dependency-aware claim"].intact
    assert "11 with unmet dependencies" in by["dependency-aware claim"].ablated  # 12 tasks, one root
    assert not by["dependency-aware claim"].ablated_ok
    assert rep.as_expected
    out = capsys.readouterr().out
    assert out == ""  # run_ablation prints nothing itself: the CLI does


def test_forget_cascade_is_not_applied_to_the_real_tenant(client, scripted_run, ablated_cleanup):
    tenant, _ = scripted_run
    ablated_cleanup.append(tenant + "_ablated")
    g = client.graph(graph_name(tenant))
    forgotten = "MATCH (f:Fact {status: 'forgotten'}) RETURN count(f)"
    open_tasks = "MATCH (t:Task) WHERE t.status <> 'done' RETURN count(t)"
    f0, t0 = g.ro_query(forgotten).result_set[0][0], g.ro_query(open_tasks).result_set[0][0]
    run_ablation(client, tenant, log=lambda _m: None)
    assert g.ro_query(forgotten).result_set[0][0] == f0
    assert g.ro_query(open_tasks).result_set[0][0] == t0 == 0  # every task is still done


def test_cli_prints_the_side_by_side_table(client, scripted_run, ablated_cleanup, cli_env, capsys):
    tenant, _ = scripted_run
    ablated_cleanup.append(tenant + "_ablated")
    assert _run("demo", "ablation", "--tenant", tenant) == 0
    out = capsys.readouterr().out
    assert "why(decision)" in out and "BROKEN" in out and "works" in out
    assert "6 of 6 edge-dependent features break; 2 of 2 controls are unaffected" in out
    assert f"stays as tenant '{tenant}_ablated'" in out
    # the copy is browsable
    assert client.db.select_graph(graph_name(tenant + "_ablated")).ro_query("MATCH (n) RETURN count(n)")


def test_cli_drop_and_json(client, scripted_run, cli_env, capsys):
    tenant, _ = scripted_run
    assert _run("demo", "ablation", "--tenant", tenant, "--drop", "--json") == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["as_expected"] and doc["original_untouched"] and doc["ablated_tenant"] == tenant + "_ablated"
    assert sum(r["broken"] for r in doc["rows"]) == 6
    assert graph_name(tenant + "_ablated") not in client.db.list_graphs()


def test_empty_tenant_is_refused_with_a_hint(client, demo_tenants, cli_env):
    with pytest.raises(SystemExit) as e:
        main(["demo", "ablation", "--tenant", demo_tenants()])
    assert "plexus demo replay" in str(e.value)


def test_tenant_name_too_long_for_the_copy(client):
    with pytest.raises(ValueError, match="too long"):
        run_ablation(client, "x" * 45, log=lambda _m: None)
