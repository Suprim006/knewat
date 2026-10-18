import sys

from tinytasks import cli
from tinytasks.api import copy_task, create_task, dedupe_tasks
from tinytasks.storage import load_all


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "data.json"))


def test_dedupe_keeps_earliest_due_and_archives_rest(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    late = create_task("x", 300)
    early = create_task("x", 100)
    mid = create_task("x", 200)
    other = create_task("y", 50)
    assert dedupe_tasks() == 2
    state = {t.id: t.archived for t in load_all()}
    assert state == {late.id: True, early.id: False, mid.id: True, other.id: False}
    assert dedupe_tasks() == 0


def test_copy_task(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("orig", 60)
    c = copy_task(t.id, "orig (copy)")
    assert (c.title, c.due_at) == ("orig (copy)", t.due_at)
    assert len(load_all()) == 2
    assert copy_task(999, "x") is None


def test_cli_dedupe_and_copy(tmp_path, monkeypatch, capsys):
    _isolate(tmp_path, monkeypatch)
    a = create_task("same", 100)
    create_task("same", 200)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "dedupe"])
    cli.main()
    assert capsys.readouterr().out.strip() == "1"
    monkeypatch.setattr(sys, "argv", ["tinytasks", "copy", str(a.id)])
    cli.main()
    assert "same (copy)" in capsys.readouterr().out
    assert load_all()[-1].due_at == a.due_at
    monkeypatch.setattr(sys, "argv", ["tinytasks", "copy", "999"])
    cli.main()
    assert capsys.readouterr().out.strip() == "no such task"


def test_cli_copy_long_title_keeps_suffix(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    t = create_task("z" * 80, 60)
    monkeypatch.setattr(sys, "argv", ["tinytasks", "copy", str(t.id)])
    cli.main()
    new = load_all()[-1].title
    assert len(new) <= 80 and new.endswith(" (copy)")
