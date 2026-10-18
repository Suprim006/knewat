from tinytasks.api import archive_task, create_task, get_overdue_tasks
from tinytasks.storage import load_all
from tinytasks.text import normalize_title


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


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
    t = create_task("late", due_in_seconds=-10)
    create_task("late too", due_in_seconds=-10)
    archive_task(t.id)
    assert [x.title for x in get_overdue_tasks()] == ["late too"]


def test_normalize_title():
    assert normalize_title("  a " + chr(9) + " b" + chr(10)*2 + " c  ") == "a b c"
    assert len(normalize_title("x" * 200)) == 80
    assert normalize_title("") == ""


def test_create_task_does_not_normalize(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert create_task("  raw   title ", 1).title == "  raw   title "
