from tinytasks.api import create_task
from tinytasks.text import normalize_title


def test_strips_and_collapses_whitespace():
    assert normalize_title("  a \t b\n\n c  ") == "a b c"


def test_truncates_to_80():
    assert len(normalize_title("x" * 200)) == 80


def test_create_task_keeps_raw_title(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYTASKS_DATA", str(tmp_path / "d.json"))
    assert create_task("  raw   title ", 1).title == "  raw   title "
