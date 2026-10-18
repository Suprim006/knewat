"""L7 family I (atomic multi-entity writes) at toy size.

Integration tests need FalkorDB on KNEWAT_TEST_DB_PORT (family I's own port is 6368); nothing here kills a container.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from knewat.crucible.l7 import i as fam
from knewat.crucible.l7 import i_arms as arms
from knewat.crucible.l7 import i_conc
from knewat.graph.tenancy import graph_name
from tests.conftest import TEST_DB_HOST, TEST_DB_PORT


def _closeouts(
    name: str, n: int, root: str, stale_every: int = 4
) -> tuple[arms.Arm, dict[str, str], dict[str, set[str]], list[str]]:
    run = uuid.uuid4().hex[:6]
    arm = fam.new_world(name, TEST_DB_HOST, TEST_DB_PORT, root, run)
    arm.connect()
    intents: dict[str, dict] = {}
    stale: list[str] = []
    for i in range(n):
        co = f"{arms.SLUG[name]}{run}.{i}"
        task, v = arm.new_task(co)
        intents[co] = {"task": task, "v": v}
        is_stale = i % stale_every == stale_every - 1
        if is_stale:
            stale.append(co)
        assert arm.closeout(co, task, v, v - 1 if is_stale else v) is (not is_stale)
    states, items = arm.states(arms.SLUG[name] + run, intents)
    return arm, states, items, stale


@pytest.fixture
def root():
    d = tempfile.mkdtemp(prefix="l7i-test-")
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------------------------------------ pure / SQLite
def test_classify_and_flags():
    assert arms.classify(set(arms.ITEMS)) == "complete"
    assert arms.classify(set()) == "absent"
    assert arms.classify({"fact"}) == "partial"
    assert arms.stale_flags(7, 100) == arms.stale_flags(7, 100)
    assert 10 < sum(arms.stale_flags(7, 100)) < 40


def test_statement_files():
    stmts = arms.sql_statements()
    assert len(stmts) == 11 and all(s.strip() for s in stmts)
    assert "UPDATE tasks" in stmts[7]  # the version guard
    for n in ("f_1stmt_first.cypher", "f_1stmt_last.cypher", "f_step.cypher", "f_task_err.cypher"):
        assert arms.query_text(n).strip()
    assert "1 / 0" in arms.query_text("f_1stmt_last.cypher")


@pytest.mark.parametrize("name,partial", [("S-txn", 0), ("S-auto", 1)])
def test_sqlite_arms_stale_version(name, partial, root):
    arm, states, items, stale = _closeouts(name, 8, root)
    assert sum(1 for s in states.values() if s == "complete") == 6
    assert sum(1 for co in stale if states[co] == "partial") == partial * len(stale)
    assert sum(1 for co in stale if states[co] == "absent") == (len(stale) if name == "S-txn" else 0)
    assert all(
        "task_done" not in items[co] for co in stale
    )  # the guard never lets a stale close-out change the task


def test_i1_sqlite_kill_protocol_smoke(root):
    """A real writer process is hard-killed: the transactional arm shows no partial close-out."""
    res = fam.run_i1_arm("S-txn", 3, TEST_DB_HOST, TEST_DB_PORT, root, 20261016)
    assert res["acknowledged"] > 0 and res["partial"] == 0 and res["lost_acknowledged"] == 0, res
    assert res["entities_without_intent"] == 0


def test_i2_sqlite_arm(root):
    txn = fam.run_i2_arm("S-txn", 20, TEST_DB_HOST, TEST_DB_PORT, root, 5)
    auto = fam.run_i2_arm("S-auto", 20, TEST_DB_HOST, TEST_DB_PORT, root, 5)
    assert txn["stale"] > 0 and txn["stale_partial"] == 0 and txn["stale_absent"] == txn["stale"]
    assert auto["stale_partial"] == auto["stale"]
    assert txn["fresh_complete"] == txn["fresh"] == auto["fresh_complete"]


def test_i4_sqlite_modes(root):
    a = {m: i_conc.i4a_sqlite(m, 4, 5, root) for m in i_conc.A_MODES}
    assert (
        a["atomic"]["lost_acked"] == 0 and a["cas"]["lost_acked"] == 0 and a["pessimistic"]["lost_acked"] == 0
    )
    assert a["naive"]["final"] <= a["naive"]["acked"]
    one = i_conc.i4b_run("SQLite", "one statement", 20, 0, TEST_DB_HOST, TEST_DB_PORT, root)
    imm = i_conc.i4b_run("SQLite", "BEGIN IMMEDIATE", 20, 0, TEST_DB_HOST, TEST_DB_PORT, root)
    assert one["violations"] == 0 and imm["violations"] == 0 and imm["errors"] == 0
    dfd = i_conc.i4b_run("SQLite", "BEGIN DEFERRED", 20, 0, TEST_DB_HOST, TEST_DB_PORT, root)
    assert dfd["violations"] == 0


def test_report_renders():
    doc = {
        "scale": "dev", "run": {"id": "x-i"},
        "parts": {"I1": {"arms": {"S-txn": {"kills": 1, "started": 2, "acknowledged": 1, "partial": 0, "lost_acknowledged": 0,
                                            "inflight_at_kill": 1, "inflight_complete": 1, "inflight_partial": 0,
                                            "inflight_absent": 0, "partial_rate_per_acknowledged": 0.0}}}},
    }  # fmt: skip
    assert "S-txn" in fam.report_md(doc)


# ------------------------------------------------------------------------------------------------ FalkorDB
@pytest.fixture
def drops(client):
    names: list[str] = []
    yield names
    for n in names:
        client.delete_graph(n)


@pytest.mark.parametrize(
    "name,stale_state",
    [
        ("F-multi", "partial"), ("F-multi-cas-first", "absent"), ("F-multiexec", "partial"),
        ("F-multiexec-err", "partial"), ("F-1stmt-first", "absent"), ("F-1stmt-last", "absent"),
    ],
)  # fmt: skip
def test_falkor_arms_stale_version(name, stale_state, root, drops):
    arm, states, items, stale = _closeouts(name, 8, root)
    drops.append(graph_name(arm.tenant))
    assert sum(1 for s in states.values() if s == "complete") == 6, states
    assert stale and all(states[co] == stale_state for co in stale), (states, items)
    if stale_state == "partial":
        assert all("task_done" not in items[co] for co in stale)  # entities written, task untouched
    arm.close()


def test_falkor_product_arm_partial_on_stale(root, drops):
    arm, states, items, stale = _closeouts("F-product", 4, root, stale_every=4)
    drops.append(graph_name(arm.tenant))
    assert sum(1 for s in states.values() if s == "complete") == 3, states
    assert all(
        states[co] == "partial" for co in stale
    )  # assert_fact + record_decision happened, complete_task refused
    arm.close()


def test_multiexec_accepts_graph_query_and_does_not_roll_back(client, drops):
    """Capability facts the pre-registration relies on (re-verified on every run)."""
    name = f"test_{uuid.uuid4().hex}"
    drops.append(name)
    g = client.graph(name)
    g.query("CREATE (:T {id: 't'})")
    pipe = client.db.connection.pipeline(transaction=True)
    pipe.execute_command("GRAPH.QUERY", name, "CREATE (:A {id: 'before'})")
    pipe.execute_command("GRAPH.QUERY", name, "RETURN 1 / 0")
    pipe.execute_command("GRAPH.QUERY", name, "CREATE (:A {id: 'after'})")
    res = pipe.execute(raise_on_error=False)
    assert isinstance(res[1], Exception)
    assert g.ro_query("MATCH (a:A) RETURN count(a)").result_set[0][0] == 2  # both neighbours applied
    with pytest.raises(Exception, match="(?i)zero"):  # a runtime error inside ONE statement undoes its CREATE
        g.query(
            "CREATE (:B {id: 'b'}) WITH 1 AS x MATCH (t:T) WITH t, CASE WHEN t.id = 'zz' THEN 1 ELSE 1 / 0 END AS boom RETURN boom"
        )
    assert g.ro_query("MATCH (b:B) RETURN count(b)").result_set[0][0] == 0


def test_i4_falkor_modes(root):
    a = {m: i_conc.i4a_falkor(m, 4, 5, TEST_DB_HOST, TEST_DB_PORT) for m in i_conc.A_MODES}
    assert (
        a["atomic"]["lost_acked"] == 0 and a["cas"]["lost_acked"] == 0 and a["pessimistic"]["lost_acked"] == 0
    ), a
    one = i_conc.i4b_run("FalkorDB", "one statement", 15, 0, TEST_DB_HOST, TEST_DB_PORT, root)
    watch = i_conc.i4b_run("FalkorDB", "WATCH+MULTI/EXEC", 15, 0, TEST_DB_HOST, TEST_DB_PORT, root)
    assert one["violations"] == 0 and watch["violations"] == 0


def test_i5_runs(root):
    res = fam.run_i5(5, TEST_DB_HOST, TEST_DB_PORT, root, None, None)
    assert res["lines_statement_text"]["F-1stmt"] > 0 and res["statements_per_closeout"]["S-txn"] == 13
    assert res["F-1stmt"]["writers_1"]["errors"] == 0 and res["S-txn"]["writers_8"]["errors"] == 0
    assert Path(arms.QDIR / "f_1stmt_first.cypher").exists()
