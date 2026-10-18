"""FIX-P7 P7-05: a file that is too big to hash is skipped, not reported as deleted."""

from __future__ import annotations

from knewat.codescan import workflow
from knewat.codescan.paths import canonical_path
from knewat.codescan.workflow import FileTooLarge, read_working, working_groups


def test_read_working_tells_missing_from_oversize(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "MAX_FILE_BYTES", 10)
    small, big = tmp_path / "small.txt", tmp_path / "big.bin"
    small.write_bytes(b"12345")
    big.write_bytes(b"x" * 11)
    assert read_working(str(small)) == b"12345"
    assert read_working(str(tmp_path / "gone.txt")) is None  # deleted
    try:
        read_working(str(big))
    except FileTooLarge as exc:
        assert "big.bin" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an oversize file must not look like a missing one")


def test_working_groups_skips_an_oversize_file_and_still_reports_a_deleted_one(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(workflow, "MAX_FILE_BYTES", 10)
    (tmp_path / "big.bin").write_bytes(b"x" * 11)
    (tmp_path / "ok.txt").write_bytes(b"ok")
    paths = [str(tmp_path / n) for n in ("big.bin", "ok.txt", "gone.txt")]
    groups = working_groups(str(tmp_path), paths, baseline=True)
    by_path = {g[0]["path"]: g[0] for g in groups}
    assert set(by_path) == {canonical_path(paths[1]), canonical_path(paths[2])}  # big.bin is not there
    assert by_path[canonical_path(paths[1])]["new_hash"] != ""
    assert by_path[canonical_path(paths[2])]["new_hash"] == ""  # a real deletion is still a deletion
    err = capsys.readouterr().err
    assert "big.bin" in err and "too large" in err
