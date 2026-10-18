import sys

from tinytasks import cli
from tinytasks.api import create_task, remove_tasks, rename_task
from tinytasks.storage import load_all


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


def test_remove_tasks_archives_given_ids(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", 60)
    b = create_task("b", 60)
    c = create_task("c", 60)
    assert remove_tasks([a.id, c.id, 999]) == 2
    assert [(t.title, t.archived) for t in load_all()] == [
        ("a", True), ("b", False), ("c", True)]
    assert remove_tasks([a.id]) == 0


def test_rename_task(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", 60)
    assert rename_task(t.id, "new") is True
    assert load_all()[0].title == "new"
    assert rename_task(999, "x") is False


def test_cli_rm_and_rename(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", 60)
    b = create_task("b", 60)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "rm", str(a.id), str(b.id)])
    cli.main()
    assert capsys.readouterr().out.strip() == "2"
    assert all(t.archived for t in load_all())
    monkeypatch.setattr(sys, "argv", ["tinytasks", "rename", str(a.id), "  new   name "])
    cli.main()
    assert capsys.readouterr().out.strip() == "renamed"
    assert load_all()[0].title == "new name"
