from __future__ import annotations

from plexus.codescan.entries import MAX_ENTRIES, chunk_entries, file_entries
from plexus.codescan.hashing import hash_bytes

P = "C:/r/app/pay.py"
OLD = b"def f():\n    return 1\n\n\ndef g():\n    return 2\n"
NEW = b"def f():\n    return 10\n\n\ndef g():\n    return 2\n"


def test_a_python_file_has_one_file_entry_and_one_per_symbol():
    e = file_entries(P, NEW, OLD)
    assert [(x.get("symbol", ""), x["kind"] if "kind" in x else "file") for x in e] == [
        ("", "file"),
        ("f", "function"),
        ("g", "function"),
    ]
    assert e[0] == {"path": P, "new_hash": hash_bytes(NEW), "old_hash": hash_bytes(OLD)}
    f, g = e[1], e[2]
    assert f["new_hash"] != f["old_hash"] and g["new_hash"] == g["old_hash"]


def test_without_old_content_there_are_no_old_hashes():
    e = file_entries(P, NEW)
    assert all(x["old_hash"] == "" for x in e)


def test_a_deleted_file_and_its_symbols_have_empty_new_hashes():
    e = file_entries(P, None, OLD)
    assert e[0]["new_hash"] == "" and e[0]["old_hash"] == hash_bytes(OLD)
    assert [(x["symbol"], x["new_hash"] == "") for x in e[1:]] == [("f", True), ("g", True)]


def test_a_removed_symbol_is_reported_as_gone():
    e = file_entries(P, b"def g():\n    return 2\n", OLD)
    gone = next(x for x in e if x.get("symbol") == "f")
    assert gone["new_hash"] == "" and gone["old_hash"] != ""


def test_non_python_files_and_unparseable_python_are_file_level_only():
    assert len(file_entries("C:/r/README.md", b"# hi\n")) == 1
    assert len(file_entries(P, b"def broken(:\n", OLD)) == 1
    assert len(file_entries(P, NEW, symbols=False)) == 1


def test_a_file_with_too_many_symbols_is_file_level_only():
    src = "".join(f"def f{i}():\n    pass\n\n\n" for i in range(MAX_ENTRIES)).encode()
    assert len(file_entries(P, src)) == 1


def test_chunks_never_split_a_file_and_respect_the_limit():
    groups = [
        [{"path": f"C:/r/{i}.py", "new_hash": "h"}] + [{"path": f"C:/r/{i}.py", "symbol": "s"}] * 59
        for i in range(7)
    ]
    chunks = list(chunk_entries(groups))
    assert [len(c) for c in chunks] == [180, 180, 60]
    for c in chunks:
        assert len(c) <= MAX_ENTRIES
        assert len({x["path"] for x in c}) * 60 == len(c)
    big = [{"path": "C:/r/b.py", "new_hash": "h"}] + [
        {"path": "C:/r/b.py", "symbol": f"s{i}"} for i in range(300)
    ]
    assert list(chunk_entries([big])) == [[big[0]]]
