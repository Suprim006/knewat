import json
from datetime import datetime

from tasksync.cli import main
from tasksync.exporters import export_json
from tasksync.reader import load_tasks
from tasksync.timefmt import to_iso


def test_load_tasks_missing_file_is_empty(tmp_path):
    assert load_tasks(tmp_path / "nope.json") == []


def test_load_tasks_reads_list(data_file):
    assert [t["id"] for t in load_tasks(data_file)] == [1, 2, 3]


def test_to_iso_roundtrip():
    ts = 1791000000.0
    assert datetime.fromisoformat(to_iso(ts)).timestamp() == ts


def test_export_json_writes_all_tasks(data_file, tmp_path):
    out = tmp_path / "out.json"
    assert export_json(load_tasks(data_file), out) == 3
    body = json.loads(out.read_text(encoding="utf-8"))
    assert [t["id"] for t in body["tasks"]] == [1, 2, 3]
    assert body["count"] == 3
    assert all(isinstance(t["due"], str) for t in body["tasks"])


def test_cli_export_json(data_file, tmp_path, capsys):
    out = tmp_path / "out.json"
    main(["--data", str(data_file), "export-json", str(out)])
    assert "wrote 3 tasks" in capsys.readouterr().out
    assert len(json.loads(out.read_text(encoding="utf-8"))["tasks"]) == 3
