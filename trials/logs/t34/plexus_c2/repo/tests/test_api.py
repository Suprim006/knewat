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
    assert archive_task(999) is False


def test_overdue_skips_archived(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("late", due_in_seconds=-10)
    archive_task(t.id)
    assert get_overdue_tasks() == []
