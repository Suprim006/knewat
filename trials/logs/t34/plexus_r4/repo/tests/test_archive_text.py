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


def test_archive_task_missing_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert archive_task(99) is False


def test_normalize_title():
    assert normalize_title("  a \t b\n\nc  ") == "a b c"
    assert len(normalize_title("x" * 200)) == 80
    assert normalize_title("   ") == ""


def test_create_task_keeps_raw_title(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert create_task("  raw   title ", 1).title == "  raw   title "
