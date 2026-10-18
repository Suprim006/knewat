import time

from tinytasks.api import archive_task, create_task, delete_task, get_overdue_tasks
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


def test_archive_task_keeps_record(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("keep me", due_in_seconds=60)
    assert archive_task(t.id) is True
    tasks = load_all()
    assert len(tasks) == 1 and tasks[0].archived is True


def test_archive_task_missing_returns_false(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert archive_task(999) is False


def test_overdue_skips_archived(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("late but archived", due_in_seconds=-10)
    archive_task(t.id)
    assert get_overdue_tasks() == []


def test_remove_tasks_archives_all_given_ids(tmp_path, monkeypatch):
    from tinytasks.api import remove_tasks

    _isolate(tmp_path, monkeypatch)
    a = create_task("a", due_in_seconds=60)
    b = create_task("b", due_in_seconds=60)
    c = create_task("c", due_in_seconds=60)
    assert remove_tasks([a.id, c.id, 999]) == 2
    tasks = load_all()
    assert len(tasks) == 3  # soft-delete only
    assert [t.title for t in tasks if not t.archived] == ["b"]
    assert remove_tasks([a.id]) == 0


def test_rename_task(tmp_path, monkeypatch):
    from tinytasks.api import rename_task

    _isolate(tmp_path, monkeypatch)
    t = create_task("old", due_in_seconds=60)
    assert rename_task(t.id, "new") is True
    assert load_all()[0].title == "new"
    assert rename_task(999, "x") is False


def test_dedupe_archives_later_duplicates_keeps_earliest_due(tmp_path, monkeypatch):
    from tinytasks.api import dedupe_tasks
    _isolate(tmp_path, monkeypatch)
    create_task("a", due_in_seconds=300)
    keep = create_task("a", due_in_seconds=100)
    create_task("a", due_in_seconds=200)
    create_task("b", due_in_seconds=50)
    create_task("A", due_in_seconds=50)
    assert dedupe_tasks() == 2
    tasks = load_all()
    assert len(tasks) == 5
    assert [t.id for t in tasks if not t.archived and t.title == "a"] == [keep.id]
    assert dedupe_tasks() == 0


def test_copy_task_same_due_at(tmp_path, monkeypatch):
    from tinytasks.api import copy_task
    _isolate(tmp_path, monkeypatch)
    t = create_task("x", due_in_seconds=500)
    c = copy_task(t.id, "x (copy)")
    assert c.title == "x (copy)" and c.due_at == t.due_at and c.id != t.id
    assert copy_task(999, "n") is None
