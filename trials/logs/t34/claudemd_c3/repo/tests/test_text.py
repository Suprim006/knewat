from tinytasks.text import normalize_title


def test_strips_and_collapses_whitespace():
    assert normalize_title("  hello \t  world\n again  ") == "hello world again"


def test_truncates_to_80():
    assert len(normalize_title("x" * 200)) == 80


def test_short_title_unchanged():
    assert normalize_title("ok") == "ok"
