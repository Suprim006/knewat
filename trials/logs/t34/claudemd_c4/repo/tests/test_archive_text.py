from tinytasks.api import archive_task, create_task, get_overdue_tasks
from tinytasks.storage import load_all
from tinytasks.text import normalize_title


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


def test_archive_task_keeps_record_and_hides_from_overdue(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("late", due_in_seconds=-10)
    assert archive_task(t.id) is True
    assert [x.archived for x in load_all()] == [True]
    assert get_overdue_tasks() == []


def test_archive_task_missing_returns_false(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert archive_task(99) is False


def test_create_task_does_not_normalize(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert create_task("  a   b ", due_in_seconds=1).title == "  a   b "


def test_normalize_title():
    assert normalize_title("  a \t b\n\nc  ") == "a b c"
    assert normalize_title("x" * 100) == "x" * 80
