from __future__ import annotations

import os
import subprocess
import sys

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
        ("///srv//repo/", "/srv/repo"),
        ("//srv//repo/", "//srv/repo"),
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


# -- P7-06 ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("\\\\server\\share\\dir\\a.py", "//server/share/dir/a.py"),
        ("//server/share/dir/../a.py", "//server/share/a.py"),
        ("\\\\?\\UNC\\server\\share\\a.py", "//server/share/a.py"),
        ("\\\\?\\c:\\repo\\a.py", "C:/repo/a.py"),
    ],
)
def test_unc_paths_keep_their_host(raw, want):
    assert canonical_path(raw) == want
    assert canonical_path(want) == want  # idempotent: the server canonicalises the client's answer again


def _dir_link(link, target) -> bool:
    """Make ``link`` a directory symlink (a junction on Windows when symlinks are not allowed)."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if sys.platform == "win32":
        cmd = ["cmd", "/c", "mklink", "/J", str(link), str(target)]
        return subprocess.run(cmd, capture_output=True, check=False).returncode == 0  # noqa: S603
    return False


def test_absolute_canonical_resolves_a_symlinked_or_junctioned_directory(tmp_path):
    real = tmp_path / "real_repo"
    real.mkdir()
    (real / "a.py").write_text("x = 1\n")
    link = tmp_path / "link_repo"
    if not _dir_link(link, real):
        pytest.skip("cannot create a directory symlink or junction here")
    via_link = absolute_canonical(str(link / "a.py"))
    assert via_link == absolute_canonical(str(real / "a.py"))
    assert via_link.endswith("/real_repo/a.py")
    # relative to a linked base, and a file that does not exist (deleted) under the linked directory
    assert absolute_canonical("a.py", str(link)) == via_link
    assert absolute_canonical(str(link / "gone.py")).endswith("/real_repo/gone.py")


def test_the_hook_path_and_the_git_scan_path_agree_under_a_linked_repo(tmp_path):
    from plexus.codescan import gitutil
    from plexus.codescan.workflow import relpath

    real = tmp_path / "real_repo"
    real.mkdir()
    subprocess.run(["git", "init", "-q", str(real)], check=True)  # noqa: S603, S607
    (real / "a.py").write_text("x = 1\n")
    link = tmp_path / "link_repo"
    if not _dir_link(link, real):
        pytest.skip("cannot create a directory symlink or junction here")
    top = gitutil.toplevel(str(link))
    assert top is not None
    hook_path = absolute_canonical(str(link / "a.py"))
    scan_path = absolute_canonical("a.py", top)
    assert hook_path == scan_path
    assert relpath(top, hook_path) == "a.py"
