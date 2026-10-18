import time

from tinytasks.text import normalize_title

from tinytasks.api import archive_task, clear_overdue, create_task, delete_task, get_overdue_tasks, remove_tasks, rename_task
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
    t = create_task("old", due_in_seconds=-10)
    assert archive_task(t.id) is True
    stored = load_all()
    assert len(stored) == 1 and stored[0].archived is True
    assert get_overdue_tasks() == []


def test_archive_task_unknown_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("x", due_in_seconds=60)
    assert archive_task(999) is False


def test_create_task_keeps_raw_title(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert create_task("  a   b ", due_in_seconds=1).title == "  a   b "


def test_normalize_title():
    assert normalize_title("  hello \t  world\n") == "hello world"
    assert normalize_title("x" * 100) == "x" * 80
    assert normalize_title("") == ""


def test_clear_overdue_archives_and_counts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    create_task("late1", due_in_seconds=-10)
    create_task("late2", due_in_seconds=-5)
    create_task("later", due_in_seconds=10000)
    assert clear_overdue() == 2
    stored = load_all()
    assert len(stored) == 3
    assert [t.title for t in stored if t.archived] == ["late1", "late2"]
    assert clear_overdue() == 0


def test_cli_clear_overdue_prints_count(tmp_path, monkeypatch, capsys):
    from tinytasks import cli
    _isolate(tmp_path, monkeypatch)
    create_task("late", due_in_seconds=-10)
    monkeypatch.setattr("sys.argv", ["tinytasks", "clear-overdue"])
    cli.main()
    assert capsys.readouterr().out.strip() == "1"


def test_cli_quick_add_due_in_24h_and_normalized(tmp_path, monkeypatch):
    from tinytasks import cli
    _isolate(tmp_path, monkeypatch)
    before = time.time()
    monkeypatch.setattr("sys.argv", ["tinytasks", "quick-add", "  Buy   milk  "])
    cli.main()
    (t,) = load_all()
    assert t.title == normalize_title("  Buy   milk  ")
    assert 86300 < t.due_at - before < 86500


def test_remove_tasks_archives_all_given(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", 60)
    b = create_task("b", 60)
    c = create_task("c", 60)
    assert remove_tasks([a.id, c.id, 999]) == 2
    stored = load_all()
    assert len(stored) == 3
    assert [t.archived for t in stored] == [True, False, True]
    assert remove_tasks([a.id]) == 0


def test_rename_task(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("old", 60)
    assert rename_task(t.id, "  new  ") is True
    assert load_all()[0].title == "  new  "
    assert rename_task(999, "x") is False


def test_cli_rm_and_rename(tmp_path, monkeypatch, capsys):
    from tinytasks import cli
    _isolate(tmp_path, monkeypatch)
    a = create_task("a", 60)
    b = create_task("b", 60)
    monkeypatch.setattr("sys.argv", ["tinytasks", "rm", str(a.id), str(b.id)])
    cli.main()
    assert capsys.readouterr().out.strip() == "2"
    monkeypatch.setattr("sys.argv", ["tinytasks", "rename", str(a.id), "  hi   there "])
    cli.main()
    assert capsys.readouterr().out.strip() == "renamed"
    assert load_all()[0].title == "hi there"


def test_dedupe_keeps_earliest_due_and_archives_rest(tmp_path, monkeypatch):
    from tinytasks.api import dedupe_tasks
    _isolate(tmp_path, monkeypatch)
    create_task("dup", 300)
    b = create_task("dup", 100)
    create_task("dup", 200)
    create_task("unique", 50)
    create_task("Dup", 10)
    assert dedupe_tasks() == 2
    stored = load_all()
    assert len(stored) == 5
    assert [t.archived for t in stored] == [True, False, True, False, False]
    assert stored[1].id == b.id
    assert dedupe_tasks() == 0


def test_cli_dedupe_prints_count(tmp_path, monkeypatch, capsys):
    from tinytasks import cli
    _isolate(tmp_path, monkeypatch)
    create_task("x", 10)
    create_task("x", 20)
    monkeypatch.setattr("sys.argv", ["tinytasks", "dedupe"])
    cli.main()
    assert capsys.readouterr().out.strip() == "1"


def test_cli_copy_same_due_at_and_title_suffix(tmp_path, monkeypatch, capsys):
    from tinytasks import cli
    _isolate(tmp_path, monkeypatch)
    orig = create_task("report", 500)
    monkeypatch.setattr("sys.argv", ["tinytasks", "copy", str(orig.id)])
    cli.main()
    stored = load_all()
    assert len(stored) == 2
    assert stored[1].title == "report (copy)"
    assert stored[1].due_at == orig.due_at
    assert stored[0].title == "report"


def test_cli_copy_unknown_id(tmp_path, monkeypatch, capsys):
    from tinytasks import cli
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.argv", ["tinytasks", "copy", "42"])
    cli.main()
    assert capsys.readouterr().out.strip() == "no such task"
    assert load_all() == []
