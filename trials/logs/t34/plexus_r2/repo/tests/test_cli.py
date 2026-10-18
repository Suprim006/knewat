import sys
import time

from tinytasks.api import clear_overdue, create_task, get_overdue_tasks
from tinytasks.cli import main
from tinytasks.storage import load_all


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


def test_clear_overdue_archives_and_counts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("late1", due_in_seconds=-10)
    create_task("late2", due_in_seconds=-20)
    create_task("later", due_in_seconds=10000)
    assert clear_overdue() == 2
    tasks = load_all()
    assert len(tasks) == 3  # soft-delete only
    assert [t.title for t in tasks if not t.archived] == ["later"]
    assert get_overdue_tasks() == []
    assert clear_overdue() == 0


def test_cli_clear_overdue_prints_count(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    create_task("late", due_in_seconds=-10)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "clear-overdue"])
    main()
    assert capsys.readouterr().out.strip() == "1"


def test_cli_quick_add_due_in_24h_and_normalized(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    before = time.time()
    monkeypatch.setattr(sys, "argv", ["tinytasks", "quick-add", "  buy   milk "])
    main()
    (t,) = load_all()
    assert t.title == "buy milk"
    assert 86400 - 100 < t.due_at - before < 86400 + 100


def test_cli_rm_multiple_ids(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", due_in_seconds=60)
    b = create_task("b", due_in_seconds=60)
    c = create_task("c", due_in_seconds=60)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "rm", str(a.id), str(b.id)])
    main()
    assert capsys.readouterr().out.strip() == "2"
    assert [t.title for t in load_all() if not t.archived] == ["c"]
    assert len(load_all()) == 3


def test_cli_rename_normalizes_title(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", due_in_seconds=60)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "rename", str(t.id), "  new   name "])
    main()
    assert capsys.readouterr().out.strip() == "renamed"
    assert load_all()[0].title == "new name"


def test_cli_dedupe_prints_count(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    create_task("a", due_in_seconds=10)
    create_task("a", due_in_seconds=20)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "dedupe"])
    main()
    assert capsys.readouterr().out.strip() == "1"
    assert len([t for t in load_all() if not t.archived]) == 1


def test_cli_copy_keeps_due_at(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    t = create_task("buy milk", due_in_seconds=60)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "copy", str(t.id)])
    main()
    copy = load_all()[1]
    assert copy.title == "buy milk (copy)"
    assert copy.due_at == t.due_at


def test_cli_copy_missing(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "copy", "5"])
    main()
    assert capsys.readouterr().out.strip() == "no such task"
