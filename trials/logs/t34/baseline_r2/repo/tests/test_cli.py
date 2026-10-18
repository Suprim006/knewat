import sys
import time

from tinytasks import cli
from tinytasks.api import clear_overdue, create_task, get_overdue_tasks
from tinytasks.storage import load_all


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


def _run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["tinytasks", *args])
    cli.main()


def test_clear_overdue_archives_and_counts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("late1", -10)
    create_task("late2", -20)
    create_task("later", 10000)
    assert clear_overdue() == 2
    assert get_overdue_tasks() == []
    tasks = load_all()
    assert len(tasks) == 3
    assert sum(t.archived for t in tasks) == 2
    assert clear_overdue() == 0


def test_clear_overdue_cli_prints_count(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    create_task("late", -10)
    _run(monkeypatch, "clear-overdue")
    assert capsys.readouterr().out.strip() == "1"


def test_quick_add_due_in_24h_and_normalized(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    from tinytasks.text import normalize_title
    raw = "  Buy   milk  "
    before = time.time()
    _run(monkeypatch, "quick-add", raw)
    (t,) = load_all()
    assert 86400 - 100 < t.due_at - before < 86400 + 100
    assert t.title == normalize_title(raw)


def test_rm_archives_all_given_ids(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", 60)
    b = create_task("b", 60)
    c = create_task("c", 60)
    _run(monkeypatch, "rm", str(a.id), str(b.id), "999")
    assert capsys.readouterr().out.strip() == "2"
    tasks = {t.id: t for t in load_all()}
    assert len(tasks) == 3
    assert tasks[a.id].archived and tasks[b.id].archived and not tasks[c.id].archived


def test_rename_cli_normalizes_title(tmp_path, monkeypatch, capsys):
    from tinytasks.text import normalize_title
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", 60)
    raw = "  New   title  "
    _run(monkeypatch, "rename", str(t.id), raw)
    assert capsys.readouterr().out.strip() == "renamed"
    assert load_all()[0].title == normalize_title(raw)
    _run(monkeypatch, "rename", "999", "x")
    assert capsys.readouterr().out.strip() == "no such task"


def test_dedupe_archives_later_duplicates(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    late = create_task("dup", 300)
    early = create_task("dup", 100)
    mid = create_task("dup", 200)
    other = create_task("Dup", 400)
    solo = create_task("solo", 50)
    _run(monkeypatch, "dedupe")
    assert capsys.readouterr().out.strip() == "2"
    tasks = {t.id: t for t in load_all()}
    assert len(tasks) == 5
    assert tasks[late.id].archived and tasks[mid.id].archived
    assert not tasks[early.id].archived
    assert not tasks[other.id].archived and not tasks[solo.id].archived
    _run(monkeypatch, "dedupe")
    assert capsys.readouterr().out.strip() == "0"


def test_copy_creates_task_with_same_due_at(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    src = create_task("Write report", 600)
    _run(monkeypatch, "copy", str(src.id))
    tasks = load_all()
    assert len(tasks) == 2
    assert tasks[1].title == "Write report (copy)"
    assert tasks[1].due_at == src.due_at
    assert tasks[1].id != src.id
    assert "created task" in capsys.readouterr().out


def test_copy_missing_task(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    _run(monkeypatch, "copy", "999")
    assert capsys.readouterr().out.strip() == "no such task"
    assert load_all() == []
