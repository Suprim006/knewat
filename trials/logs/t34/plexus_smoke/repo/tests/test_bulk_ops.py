import sys

from tinytasks import cli
from tinytasks.api import create_task, remove_tasks, rename_task
from tinytasks.storage import load_all


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["tinytasks", *argv])
    cli.main()


def test_remove_tasks_archives_given_ids(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", 10)
    b = create_task("b", 10)
    c = create_task("c", 10)
    assert remove_tasks([a.id, c.id, 999]) == 2
    tasks = load_all()
    assert len(tasks) == 3  # soft-delete: records kept
    assert {t.title for t in tasks if t.archived} == {"a", "c"}
    assert remove_tasks([a.id]) == 0
    assert not [t for t in tasks if t.id == b.id][0].archived


def test_rm_cli(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", 10)
    b = create_task("b", 10)
    _run(monkeypatch, "rm", str(a.id), str(b.id))
    assert capsys.readouterr().out.strip() == "2"
    assert all(t.archived for t in load_all())


def test_rename_task(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", 10)
    assert rename_task(t.id, "new") is True
    assert load_all()[0].title == "new"
    assert rename_task(999, "x") is False


def test_rename_cli_normalizes(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", 10)
    _run(monkeypatch, "rename", str(t.id), "  new   title ")
    assert capsys.readouterr().out.strip() == "renamed"
    assert load_all()[0].title == "new title"
    _run(monkeypatch, "rename", "999", "x")
    assert capsys.readouterr().out.strip() == "no such task"
