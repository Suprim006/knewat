from tinytasks.text import normalize_title


def test_strips_and_collapses_whitespace():
    assert normalize_title("  write \t the\n  report  ") == "write the report"


def test_truncates_to_80_chars():
    assert len(normalize_title("a" * 200)) == 80


def test_short_title_unchanged():
    assert normalize_title("ok") == "ok"
