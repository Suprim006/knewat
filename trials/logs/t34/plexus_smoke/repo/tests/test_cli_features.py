import sys
import time

from tinytasks import cli
from tinytasks.api import clear_overdue, create_task, get_overdue_tasks
from tinytasks.storage import load_all


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["tinytasks", *argv])
    cli.main()


def test_clear_overdue_archives_and_counts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("late1", -10)
    create_task("late2", -5)
    create_task("later", 10000)
    assert clear_overdue() == 2
    assert get_overdue_tasks() == []
    tasks = load_all()
    assert len(tasks) == 3  # soft-delete: records kept
    assert [t.title for t in tasks if t.archived] == ["late1", "late2"]
    assert clear_overdue() == 0


def test_clear_overdue_cli_prints_count(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    create_task("late", -10)
    _run(monkeypatch, "clear-overdue")
    assert capsys.readouterr().out.strip() == "1"


def test_quick_add_due_in_24h_and_normalized(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    before = time.time()
    _run(monkeypatch, "quick-add", "  buy milk  ")
    t = load_all()[0]
    assert 86300 < t.due_at - before < 86500
    from tinytasks.text import normalize_title
    assert t.title == normalize_title("  buy milk  ")
