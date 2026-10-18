import time

from tinytasks.api import (
    archive_task,
    create_task,
    delete_task,
    get_overdue_tasks,
    remove_tasks,
    rename_task,
)
from tinytasks.storage import load_all


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


def test_archive_task_keeps_record_and_hides_from_overdue(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("late", due_in_seconds=-10)
    assert archive_task(t.id) is True
    tasks = load_all()
    assert len(tasks) == 1 and tasks[0].archived is True
    assert get_overdue_tasks() == []


def test_archive_task_unknown_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert archive_task(999) is False


def test_clear_overdue_archives_and_returns_count(tmp_path, monkeypatch):
    from tinytasks.api import clear_overdue
    _isolate(tmp_path, monkeypatch)
    create_task("late1", due_in_seconds=-10)
    create_task("late2", due_in_seconds=-20)
    create_task("later", due_in_seconds=10000)
    assert clear_overdue() == 2
    tasks = load_all()
    assert len(tasks) == 3
    assert [t.title for t in tasks if not t.archived] == ["later"]
    assert clear_overdue() == 0


def test_cli_clear_overdue_prints_count(tmp_path, monkeypatch, capsys):
    import sys
    from tinytasks.cli import main
    _isolate(tmp_path, monkeypatch)
    create_task("late", due_in_seconds=-10)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "clear-overdue"])
    main()
    assert capsys.readouterr().out.strip() == "1"


def test_cli_quick_add_normalizes_and_sets_24h(tmp_path, monkeypatch):
    import sys
    from tinytasks.cli import main
    _isolate(tmp_path, monkeypatch)
    before = time.time()
    monkeypatch.setattr(sys, "argv", ["tinytasks", "quick-add", "  buy   milk  "])
    main()
    (t,) = load_all()
    assert t.title == "buy milk"
    assert 86300 < t.due_at - before < 86500


def test_remove_tasks_archives_all_given_ids(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", 60)
    b = create_task("b", 60)
    c = create_task("c", 60)
    assert remove_tasks([a.id, c.id, 999]) == 2
    tasks = {t.id: t for t in load_all()}
    assert len(tasks) == 3
    assert tasks[a.id].archived and tasks[c.id].archived
    assert not tasks[b.id].archived


def test_rename_task_changes_title(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", 60)
    assert rename_task(t.id, "new") is True
    assert load_all()[0].title == "new"
    assert rename_task(999, "x") is False


def test_cli_rename_normalizes_title(tmp_path, monkeypatch, capsys):
    import sys

    from tinytasks.cli import main

    _isolate(tmp_path, monkeypatch)
    t = create_task("old", 60)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "rename", str(t.id), "  a   b  "])
    main()
    assert load_all()[0].title == "a b"


def test_cli_rm_archives_multiple(tmp_path, monkeypatch, capsys):
    import sys

    from tinytasks.cli import main

    _isolate(tmp_path, monkeypatch)
    a = create_task("a", 60)
    b = create_task("b", 60)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "rm", str(a.id), str(b.id)])
    main()
    assert all(t.archived for t in load_all())


def _run(monkeypatch, *args):
    import sys

    from tinytasks.cli import main

    monkeypatch.setattr(sys, "argv", ["tinytasks", *args])
    main()


def test_cli_dedupe_keeps_earliest_due_and_archives_rest(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    late = create_task("dup", 500)
    early = create_task("dup", 100)
    other = create_task("unique", 300)
    _run(monkeypatch, "dedupe")
    by_id = {t.id: t for t in load_all()}
    assert len(by_id) == 3  # nothing hard-deleted
    assert by_id[late.id].archived
    assert not by_id[early.id].archived
    assert not by_id[other.id].archived


def test_cli_copy_keeps_due_at_and_normalizes(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    t = create_task("  spaced   title ", 60)
    _run(monkeypatch, "copy", str(t.id))
    tasks = load_all()
    assert len(tasks) == 2
    assert tasks[1].title == "spaced title (copy)"
    assert tasks[1].due_at == t.due_at


def test_cli_copy_missing_task(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    _run(monkeypatch, "copy", "99")
    assert "no such task" in capsys.readouterr().out
    assert load_all() == []
