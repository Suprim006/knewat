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


def test_archive_task_unknown_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert archive_task(999) is False


def test_overdue_skips_archived(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("late but archived", due_in_seconds=-10)
    archive_task(t.id)
    assert get_overdue_tasks() == []


def test_remove_tasks_archives_and_counts(tmp_path, monkeypatch):
    from tinytasks.api import remove_tasks
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", 60)
    b = create_task("b", 60)
    assert remove_tasks([a.id, b.id, 999]) == 2
    assert all(t.archived for t in load_all())
    assert remove_tasks([a.id]) == 0


def test_rename_task_keeps_raw_title(tmp_path, monkeypatch):
    from tinytasks.api import rename_task
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", 60)
    assert rename_task(t.id, " Raw  ") is True
    assert load_all()[0].title == " Raw  "
    assert rename_task(999, "x") is False
