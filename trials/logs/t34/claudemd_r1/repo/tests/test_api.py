import time

from tinytasks import cli

from tinytasks.api import (
    archive_task,
    clear_overdue,
    create_task,
    delete_task,
    get_overdue_tasks,
    remove_tasks,
    rename_task,
)
from tinytasks.storage import load_all
from tinytasks.text import normalize_title


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


def test_create_task_sets_due_at_seconds_from_now(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    before = time.time()
    t = create_task("write report", due_in_seconds=3600)
    assert 3500 < t.due_at - before < 3700


def test_overdue_tasks_filters_by_due_at(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("already late", due_in_seconds=-10)
    create_task("not yet", due_in_seconds=10000)
    overdue = get_overdue_tasks()
    assert [t.title for t in overdue] == ["already late"]


def test_delete_task_removes_it(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("temp", due_in_seconds=60)
    assert delete_task(t.id) is True
    assert load_all() == []


def test_archive_task_keeps_record(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("keep me", due_in_seconds=60)
    assert archive_task(t.id) is True
    tasks = load_all()
    assert len(tasks) == 1 and tasks[0].archived is True


def test_archive_task_unknown_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert archive_task(999) is False


def test_overdue_skips_archived(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("late but archived", due_in_seconds=-10)
    archive_task(t.id)
    assert get_overdue_tasks() == []


def test_normalize_title():
    assert normalize_title("  a \t b\n\nc  ") == "a b c"
    assert len(normalize_title("x" * 200)) == 80


def test_create_task_keeps_raw_title(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert create_task("  raw   title ", due_in_seconds=1).title == "  raw   title "


def test_clear_overdue_archives_and_counts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("late", due_in_seconds=-10)
    create_task("later", due_in_seconds=10000)
    assert clear_overdue() == 1
    tasks = load_all()
    assert len(tasks) == 2
    assert [t.title for t in tasks if t.archived] == ["late"]
    assert clear_overdue() == 0


def test_cli_clear_overdue_prints_count(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    create_task("late", due_in_seconds=-10)
    monkeypatch.setattr("sys.argv", ["tinytasks", "clear-overdue"])
    cli.main()
    assert capsys.readouterr().out.strip() == "1"


def test_cli_quick_add_due_24h_and_normalized(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    before = time.time()
    monkeypatch.setattr("sys.argv", ["tinytasks", "quick-add", "  buy   milk "])
    cli.main()
    t = load_all()[0]
    assert t.title == "buy milk"
    assert 86300 < t.due_at - before < 86500


def test_remove_tasks_archives_all_given(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", due_in_seconds=60)
    b = create_task("b", due_in_seconds=60)
    c = create_task("c", due_in_seconds=60)
    assert remove_tasks([a.id, c.id, 999]) == 2
    tasks = load_all()
    assert len(tasks) == 3
    assert {t.title for t in tasks if t.archived} == {"a", "c"}


def test_rename_task(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", due_in_seconds=60)
    assert rename_task(t.id, "new") is True
    assert load_all()[0].title == "new"
    assert rename_task(999, "x") is False


def test_cli_rm_archives_multiple(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", due_in_seconds=60)
    b = create_task("b", due_in_seconds=60)
    monkeypatch.setattr("sys.argv", ["tinytasks", "rm", str(a.id), str(b.id)])
    cli.main()
    assert capsys.readouterr().out.strip() == "2"
    assert all(t.archived for t in load_all())


def test_cli_rename_normalizes_title(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", due_in_seconds=60)
    monkeypatch.setattr("sys.argv", ["tinytasks", "rename", str(t.id), "  new   name "])
    cli.main()
    assert load_all()[0].title == "new name"


def test_cli_dedupe_keeps_earliest_due(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    late = create_task("dup", due_in_seconds=300)
    early = create_task("dup", due_in_seconds=60)
    other = create_task("other", due_in_seconds=500)
    monkeypatch.setattr("sys.argv", ["tinytasks", "dedupe"])
    cli.main()
    assert capsys.readouterr().out.strip() == "1"
    by_id = {t.id: t for t in load_all()}
    assert len(by_id) == 3
    assert by_id[late.id].archived
    assert not by_id[early.id].archived
    assert not by_id[other.id].archived


def test_cli_copy_same_due_at_and_normalized_title(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    t = create_task("report", due_in_seconds=600)
    monkeypatch.setattr("sys.argv", ["tinytasks", "copy", str(t.id)])
    cli.main()
    tasks = load_all()
    assert len(tasks) == 2
    assert tasks[1].title == "report (copy)"
    assert tasks[1].due_at == t.due_at
    assert tasks[1].id != t.id


def test_cli_copy_missing_task(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.argv", ["tinytasks", "copy", "42"])
    cli.main()
    assert capsys.readouterr().out.strip() == "no such task"
    assert load_all() == []
