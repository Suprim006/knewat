import time

from tinytasks.api import (
    add_tags, archive_task, create_task, delete_task, export_tasks, get_overdue_tasks, reschedule_task,
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


def test_archive_task_keeps_the_record(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", due_in_seconds=60)
    assert archive_task(t.id) is True
    assert load_all()[0].archived is True


def test_reschedule_task_moves_due_at(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("move me", due_in_seconds=60)
    before = time.time()
    moved = reschedule_task(t.id, 7200)
    assert 7100 < moved.due_at - before < 7300


def test_add_tags_attaches_tags(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("tagged", due_in_seconds=60)
    add_tags(t.id, ["work", "home"])
    assert load_all()[0].tags == ["work", "home"]


def test_export_tasks_returns_dicts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("one", due_in_seconds=60)
    assert [d["title"] for d in export_tasks()] == ["one"]
