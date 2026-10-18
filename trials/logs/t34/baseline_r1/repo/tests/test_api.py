import time

from tinytasks.api import create_task, delete_task, get_overdue_tasks
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
    from tinytasks.api import archive_task
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", due_in_seconds=-10)
    assert archive_task(t.id) is True
    assert [x.archived for x in load_all()] == [True]
    assert get_overdue_tasks() == []


def test_archive_task_unknown_id(tmp_path, monkeypatch):
    from tinytasks.api import archive_task
    _isolate(tmp_path, monkeypatch)
    assert archive_task(99) is False


def test_normalize_title():
    from tinytasks.text import normalize_title
    assert normalize_title("  a \t b\n\n c  ") == "a b c"
    assert normalize_title("x" * 100) == "x" * 80


def test_create_task_keeps_raw_title(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert create_task("  raw   title ", 1).title == "  raw   title "


def test_clear_overdue_archives_and_counts(tmp_path, monkeypatch):
    from tinytasks.api import clear_overdue
    _isolate(tmp_path, monkeypatch)
    create_task("late1", -10)
    create_task("late2", -20)
    create_task("later", 10000)
    assert clear_overdue() == 2
    tasks = load_all()
    assert len(tasks) == 3
    assert [t.archived for t in tasks] == [True, True, False]
    assert clear_overdue() == 0


def test_cli_quick_add_normalizes_and_sets_24h(tmp_path, monkeypatch, capsys):
    from tinytasks import cli
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.argv", ["tinytasks", "quick-add", "  buy   milk "])
    before = time.time()
    cli.main()
    t = load_all()[0]
    assert t.title == "buy milk"
    assert abs(t.due_at - before - 86400) < 5


def test_cli_clear_overdue_prints_count(tmp_path, monkeypatch, capsys):
    from tinytasks import cli
    _isolate(tmp_path, monkeypatch)
    create_task("late", -10)
    monkeypatch.setattr("sys.argv", ["tinytasks", "clear-overdue"])
    cli.main()
    assert capsys.readouterr().out.strip() == "1"


def test_remove_tasks_archives_all_given_ids(tmp_path, monkeypatch):
    from tinytasks.api import remove_tasks
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", due_in_seconds=60)
    b = create_task("b", due_in_seconds=60)
    c = create_task("c", due_in_seconds=60)
    assert remove_tasks([a.id, c.id, 999]) == 2
    assert {t.id: t.archived for t in load_all()} == {a.id: True, b.id: False, c.id: True}


def test_rename_task(tmp_path, monkeypatch):
    from tinytasks.api import rename_task
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", due_in_seconds=60)
    assert rename_task(t.id, "new") is True
    assert load_all()[0].title == "new"
    assert rename_task(999, "x") is False


def test_cli_rename_normalizes_title(tmp_path, monkeypatch):
    import sys
    from tinytasks.cli import main
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", due_in_seconds=60)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "rename", str(t.id), "  a   b  "])
    main()
    assert load_all()[0].title == "a b"


def test_dedupe_archives_later_duplicates_keeps_earliest(tmp_path, monkeypatch, capsys):
    import sys
    from tinytasks.cli import main
    _isolate(tmp_path, monkeypatch)
    create_task("dup", 300)
    first = create_task("dup", 100)
    create_task("dup", 200)
    create_task("Dup", 50)
    create_task("solo", 10)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "dedupe"])
    main()
    assert capsys.readouterr().out.strip() == "removed 2 duplicate(s)"
    tasks = load_all()
    assert len(tasks) == 5
    active = [t for t in tasks if not t.archived]
    assert sorted(t.title for t in active) == ["Dup", "dup", "solo"]
    assert [t.id for t in active if t.title == "dup"] == [first.id]


def test_dedupe_ignores_archived_and_is_idempotent(tmp_path, monkeypatch):
    from tinytasks.api import archive_task, dedupe_tasks
    _isolate(tmp_path, monkeypatch)
    early = create_task("x", 1)
    later = create_task("x", 2)
    archive_task(early.id)
    assert dedupe_tasks() == 0
    assert [t.archived for t in load_all()] == [True, False]


def test_cli_copy_same_due_at_and_normalized_title(tmp_path, monkeypatch):
    import sys
    from tinytasks.cli import main
    _isolate(tmp_path, monkeypatch)
    t = create_task("  spaced   out ", 500)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "copy", str(t.id)])
    main()
    tasks = load_all()
    assert len(tasks) == 2
    assert tasks[1].title == "spaced out (copy)"
    assert tasks[1].due_at == t.due_at
    assert tasks[1].id != t.id


def test_cli_copy_unknown_id(tmp_path, monkeypatch, capsys):
    import sys
    from tinytasks.cli import main
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "copy", "42"])
    main()
    assert capsys.readouterr().out.strip() == "no such task"
    assert load_all() == []
