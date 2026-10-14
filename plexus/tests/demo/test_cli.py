"""The ``plexus demo`` CLI, driven in-process against the test database."""

from __future__ import annotations

import pytest

from plexus.cli import main
from plexus.demo.recorder import list_recordings
from plexus.graph.tenancy import graph_name

from ..conftest import TEST_DB_HOST, TEST_DB_PORT
from .conftest import rows


@pytest.fixture
def cli_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FALKORDB_HOST", TEST_DB_HOST)
    monkeypatch.setenv("FALKORDB_PORT", str(TEST_DB_PORT))
    monkeypatch.setattr("plexus.demo.recorder.recordings_dir", lambda: tmp_path)
    return tmp_path


def _run(*argv: str) -> int:
    with pytest.raises(SystemExit) as e:
        main(list(argv))
    return e.value.code


def test_seed_live_inventory_record_replay(client, cli_env, demo_tenants, capsys):
    t1, t2 = demo_tenants(), demo_tenants()
    assert _run("demo", "seed", "--tenant", t1) == 0
    assert (
        rows(client, t1, "MATCH (s:Source) RETURN count(s)")[0][0] == 5
    )  # v2 guide + forum post arrive mid-run
    assert (
        _run(
            "demo",
            "live",
            "--scripted",
            "--tenant",
            t1,
            "--reset",
            "--speed",
            "0",
            "--embedder",
            "hash",
            "--lease-ms",
            "300",
            "--record",
            "cli-run",
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "kill_builder" in out and "publish_v2" in out and "scripted run finished: 67 tool calls" in out
    assert [m["run"] for m in list_recordings(cli_env)] == ["cli-run"]

    assert _run("demo", "inventory", "--tenant", t1) == 0
    assert "Task" in capsys.readouterr().out
    assert _run("demo", "replay", "cli-run", "--tenant", t2) == 0
    assert "matches meta.json: True" in capsys.readouterr().out
    assert _run("demo", "list") == 0


def test_live_refuses_a_tenant_with_data(client, cli_env, demo_tenants):
    t = demo_tenants()
    assert _run("demo", "seed", "--tenant", t) == 0
    with pytest.raises(SystemExit) as e:
        main(["demo", "live", "--scripted", "--tenant", t, "--speed", "0", "--embedder", "hash"])
    assert "already has data" in str(e.value)
    assert client.ro(graph_name(t), "view/inventory_nodes")
