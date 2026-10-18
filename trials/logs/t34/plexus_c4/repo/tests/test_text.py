from tinytasks.text import normalize_title


def test_strips_and_collapses_whitespace():
    assert normalize_title("  a \t b\n\n c  ") == "a b c"


def test_truncates_to_80():
    assert normalize_title("x" * 100) == "x" * 80
