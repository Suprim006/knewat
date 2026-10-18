import time

from tinytasks.api import archive_task, clear_overdue, copy_task, create_task, dedupe_tasks, delete_task, get_overdue_tasks, remove_tasks, rename_task
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
    assert [x.archived for x in load_all()] == [True]
    assert get_overdue_tasks() == []


def test_archive_task_unknown_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert archive_task(999) is False


def test_clear_overdue_archives_and_counts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("late1", due_in_seconds=-10)
    create_task("late2", due_in_seconds=-20)
    create_task("later", due_in_seconds=10000)
    assert clear_overdue() == 2
    tasks = load_all()
    assert len(tasks) == 3
    assert [t.title for t in tasks if t.archived] == ["late1", "late2"]
    assert clear_overdue() == 0


def test_cli_quick_add_normalizes_and_due_24h(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    from tinytasks import cli
    monkeypatch.setattr("sys.argv", ["tinytasks", "quick-add", "  buy   milk "])
    before = time.time()
    cli.main()
    t = load_all()[0]
    assert t.title == "buy milk"
    assert 86300 < t.due_at - before < 86500


def test_cli_clear_overdue_prints_count(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    from tinytasks import cli
    create_task("late", due_in_seconds=-10)
    monkeypatch.setattr("sys.argv", ["tinytasks", "clear-overdue"])
    cli.main()
    assert capsys.readouterr().out.strip() == "1"


def test_remove_tasks_archives_all_given(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", due_in_seconds=60)
    b = create_task("b", due_in_seconds=60)
    c = create_task("c", due_in_seconds=60)
    assert remove_tasks([a.id, c.id, 999]) == 2
    assert [(t.title, t.archived) for t in load_all()] == [("a", True), ("b", False), ("c", True)]


def test_rename_task(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", due_in_seconds=60)
    assert rename_task(t.id, "new") is True
    assert load_all()[0].title == "new"
    assert rename_task(999, "x") is False


def test_dedupe_keeps_earliest_due_and_archives_rest(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a = create_task("dup", due_in_seconds=300)
    b = create_task("dup", due_in_seconds=100)
    c = create_task("dup", due_in_seconds=200)
    d = create_task("unique", due_in_seconds=50)
    assert dedupe_tasks() == 2
    assert {t.id: t.archived for t in load_all()} == {a.id: True, b.id: False, c.id: True, d.id: False}
    assert dedupe_tasks() == 0


def test_dedupe_cli(tmp_path, monkeypatch, capsys):
    from tinytasks import cli
    _isolate(tmp_path, monkeypatch)
    create_task("x", due_in_seconds=10)
    create_task("x", due_in_seconds=20)
    monkeypatch.setattr("sys.argv", ["tinytasks", "dedupe"])
    cli.main()
    assert capsys.readouterr().out.strip() == "removed 1"
    assert len(load_all()) == 2


def test_copy_task_same_due_at(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("orig", due_in_seconds=60)
    new = copy_task(t.id, "orig (copy)")
    assert new.title == "orig (copy)" and new.due_at == t.due_at and new.id != t.id
    assert copy_task(999, "x") is None


def test_copy_cli(tmp_path, monkeypatch, capsys):
    from tinytasks import cli
    _isolate(tmp_path, monkeypatch)
    t = create_task("orig", due_in_seconds=60)
    monkeypatch.setattr("sys.argv", ["tinytasks", "copy", str(t.id)])
    cli.main()
    assert [x.title for x in load_all()] == ["orig", "orig (copy)"]
    monkeypatch.setattr("sys.argv", ["tinytasks", "copy", "999"])
    cli.main()
    assert capsys.readouterr().out.strip().endswith("no such task")
