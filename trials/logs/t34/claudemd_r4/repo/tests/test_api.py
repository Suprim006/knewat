import time

from tinytasks.api import (
    archive_task,
    clear_overdue,
    copy_task,
    create_task,
    dedupe_tasks,
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
    t = create_task("keep me", due_in_seconds=-10)
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


def test_create_task_keeps_raw_title(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("  raw   title ", due_in_seconds=60)
    assert t.title == "  raw   title "


def test_normalize_title():
    assert normalize_title("  a  b   c  ") == "a b c"
    assert normalize_title(" a" + chr(9) + "b" + chr(10) * 2 + "c ") == "a b c"
    assert normalize_title("x" * 100) == "x" * 80


def test_clear_overdue_archives_and_counts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("late", due_in_seconds=-10)
    create_task("later", due_in_seconds=-5)
    create_task("future", due_in_seconds=10000)
    assert clear_overdue() == 2
    tasks = load_all()
    assert len(tasks) == 3
    assert [t.title for t in tasks if t.archived] == ["late", "later"]
    assert clear_overdue() == 0


def _run_cli(monkeypatch, *args):
    import sys
    from tinytasks.cli import main
    monkeypatch.setattr(sys, "argv", ["tinytasks", *args])
    main()


def test_cli_clear_overdue_prints_count(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    create_task("late", due_in_seconds=-10)
    _run_cli(monkeypatch, "clear-overdue")
    assert capsys.readouterr().out.strip() == "1"


def test_cli_quick_add_due_in_24h_and_normalizes(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    before = time.time()
    _run_cli(monkeypatch, "quick-add", "  buy   milk ")
    (t,) = load_all()
    assert t.title == "buy milk"
    assert abs(t.due_at - before - 86400) < 60


def test_remove_tasks_archives_given_ids(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", 60)
    b = create_task("b", 60)
    c = create_task("c", 60)
    assert remove_tasks([a.id, c.id, 999]) == 2
    by_id = {t.id: t for t in load_all()}
    assert len(by_id) == 3
    assert by_id[a.id].archived and by_id[c.id].archived
    assert not by_id[b.id].archived


def test_rename_task(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", 60)
    assert rename_task(t.id, "new") is True
    assert load_all()[0].title == "new"
    assert rename_task(999, "x") is False


def test_cli_rename_normalizes_title(tmp_path, monkeypatch):
    import sys
    from tinytasks.cli import main
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", 60)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "rename", str(t.id), "  a   b  "])
    main()
    assert load_all()[0].title == "a b"


def test_dedupe_archives_later_duplicates_keeping_earliest(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    late = create_task("dup", 300)
    early = create_task("dup", 100)
    other = create_task("unique", 500)
    assert dedupe_tasks() == 1
    by_id = {t.id: t for t in load_all()}
    assert len(by_id) == 3
    assert by_id[late.id].archived
    assert not by_id[early.id].archived and not by_id[other.id].archived
    assert dedupe_tasks() == 0


def test_cli_dedupe_prints_count(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    create_task("x", 10)
    create_task("x", 20)
    _run_cli(monkeypatch, "dedupe")
    assert capsys.readouterr().out.strip() == "archived 1"


def test_copy_task_keeps_due_at(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("orig", 60)
    c = copy_task(t.id, "orig (copy)")
    assert c.due_at == t.due_at and c.id != t.id
    assert copy_task(999, "x") is None


def test_cli_copy_titles_and_missing(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    t = create_task("  messy   title ", 60)
    _run_cli(monkeypatch, "copy", str(t.id))
    tasks = load_all()
    assert tasks[1].title == "messy title (copy)"
    assert tasks[1].due_at == t.due_at
    capsys.readouterr()
    _run_cli(monkeypatch, "copy", "999")
    assert capsys.readouterr().out.strip() == "no such task"
