from __future__ import annotations

import pytest

from plexus.codescan.paths import absolute_canonical, anchor_id, canonical_path


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("C:/repo/app/x.py", "C:/repo/app/x.py"),
        ("c:\\repo\\app\\x.py", "C:/repo/app/x.py"),
        ("C:\\repo/app//x.py", "C:/repo/app/x.py"),
        ("c:/repo/app/", "C:/repo/app"),
        ("C:/repo/./app/../app/x.py", "C:/repo/app/x.py"),
        ("  C:/repo/x.py  ", "C:/repo/x.py"),
        ("/srv/repo/x.py", "/srv/repo/x.py"),
        ("//srv//repo/", "/srv/repo"),
        ("C:/", "C:/"),
    ],
)
def test_canonical_path(raw, want):
    assert canonical_path(raw) == want


@pytest.mark.parametrize("bad", ["", "   ", "repo/x.py", "./x.py", "x.py"])
def test_relative_or_empty_path_is_rejected(bad):
    with pytest.raises(ValueError):
        canonical_path(bad)


def test_canonical_path_is_idempotent():
    p = canonical_path("c:\\Repo\\a\\..\\b\\")
    assert canonical_path(p) == p == "C:/Repo/b"


def test_anchor_id_is_deterministic_and_symbol_sensitive():
    a = anchor_id("C:/r/x.py")
    assert a == anchor_id("C:/r/x.py") and a.startswith("anc:") and len(a) == 4 + 16
    assert anchor_id("C:/r/x.py", "f") != a
    assert anchor_id("C:/r/y.py") != a


def test_absolute_canonical_joins_a_relative_path_to_base(tmp_path):
    got = absolute_canonical("app/x.py", str(tmp_path))
    assert got == canonical_path(str(tmp_path / "app" / "x.py"))
    assert absolute_canonical("C:\\r\\x.py", str(tmp_path)) == "C:/r/x.py"
