import sys
import time

from tinytasks import cli
from tinytasks.api import clear_overdue, create_task
from tinytasks.storage import load_all


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


def test_clear_overdue_archives_and_counts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("late", due_in_seconds=-10)
    create_task("later", due_in_seconds=-5)
    create_task("future", due_in_seconds=3600)
    assert clear_overdue() == 2
    tasks = load_all()
    assert [(t.title, t.archived) for t in tasks] == [
        ("late", True), ("later", True), ("future", False)]
    assert clear_overdue() == 0


def test_cli_clear_overdue_prints_count(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    create_task("late", due_in_seconds=-10)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "clear-overdue"])
    cli.main()
    assert capsys.readouterr().out.strip() == "1"


def test_cli_quick_add_due_in_24h_and_normalized(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "quick-add", "  buy   milk "])
    before = time.time()
    cli.main()
    (t,) = load_all()
    assert t.title == "buy milk"
    assert abs(t.due_at - (before + 86400)) < 5
    assert "created task" in capsys.readouterr().out
