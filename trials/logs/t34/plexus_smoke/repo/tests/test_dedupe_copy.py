import sys

from tinytasks import cli
from tinytasks.api import create_task
from tinytasks.storage import load_all


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["tinytasks", *argv])
    cli.main()


def test_dedupe_keeps_earliest_due_and_soft_deletes(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    create_task("a", 300)
    b = create_task("a", 100)
    create_task("a", 200)
    create_task("other", 50)
    _run(monkeypatch, "dedupe")
    assert capsys.readouterr().out.strip() == "2"
    tasks = load_all()
    assert len(tasks) == 4  # records kept
    assert [t.id for t in tasks if not t.archived and t.title == "a"] == [b.id]
    assert not [t for t in tasks if t.title == "other"][0].archived


def test_dedupe_no_duplicates(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    create_task("x", 1)
    create_task("y", 1)
    _run(monkeypatch, "dedupe")
    assert capsys.readouterr().out.strip() == "0"


def test_copy_same_due_at_and_title(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    t = create_task("report", 500)
    _run(monkeypatch, "copy", str(t.id))
    tasks = load_all()
    assert len(tasks) == 2
    assert tasks[1].title == "report (copy)"
    assert tasks[1].due_at == t.due_at
    assert "report (copy)" in capsys.readouterr().out


def test_copy_missing_task(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    _run(monkeypatch, "copy", "99")
    assert capsys.readouterr().out.strip() == "no such task"
    assert load_all() == []
