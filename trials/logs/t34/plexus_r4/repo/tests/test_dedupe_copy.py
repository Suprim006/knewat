import sys

from tinytasks import cli
from tinytasks.api import copy_task, create_task, dedupe_tasks
from tinytasks.storage import load_all


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["tinytasks", *argv])
    cli.main()


def test_dedupe_keeps_earliest_due(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    late = create_task("x", 300)
    early = create_task("x", 100)
    mid = create_task("x", 200)
    other = create_task("y", 50)
    assert dedupe_tasks() == 2
    by_id = {t.id: t for t in load_all()}
    assert len(by_id) == 4  # soft-delete only
    assert not by_id[early.id].archived and not by_id[other.id].archived
    assert by_id[late.id].archived and by_id[mid.id].archived
    assert dedupe_tasks() == 0


def test_dedupe_exact_title_only(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("x", 100)
    create_task("X", 100)
    assert dedupe_tasks() == 0


def test_cli_dedupe(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    create_task("x", 100)
    create_task("x", 200)
    _run(monkeypatch, "dedupe")
    assert capsys.readouterr().out.strip() == "1"


def test_copy_task(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("orig", 100)
    new = copy_task(t.id, "orig (copy)")
    assert new.id != t.id and new.due_at == t.due_at and new.title == "orig (copy)"
    assert copy_task(999, "x") is None


def test_cli_copy(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    t = create_task("orig", 100)
    _run(monkeypatch, "copy", str(t.id))
    assert "orig (copy)" in capsys.readouterr().out
    tasks = load_all()
    assert tasks[1].title == "orig (copy)" and tasks[1].due_at == t.due_at
    _run(monkeypatch, "copy", "999")
    assert capsys.readouterr().out.strip() == "no such task"
