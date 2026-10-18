from tinytasks.text import normalize_title


def test_normalize_title_strips_and_collapses_whitespace():
    assert normalize_title("  write \t the\n  report  ") == "write the report"


def test_normalize_title_truncates_to_80():
    assert len(normalize_title("x" * 200)) == 80
