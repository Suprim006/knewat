from tinytasks.text import normalize_title


def test_strip_and_collapse():
    assert normalize_title("  a \t b\n\nc  ") == "a b c"


def test_truncate_to_80():
    assert len(normalize_title("x" * 200)) == 80


def test_empty():
    assert normalize_title("   ") == ""
