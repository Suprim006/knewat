from tinytasks.text import normalize_title


def test_strips_and_collapses_whitespace():
    assert normalize_title("  write \t the\n  report  ") == "write the report"


def test_truncates_to_80_chars():
    assert normalize_title("a" * 100) == "a" * 80
