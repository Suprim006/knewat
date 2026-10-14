"""Unit tests for the helpers (percentiles, scope chain, the fact classifier, the inter-process file lock)."""

from __future__ import annotations

import subprocess
import sys
import threading

import pytest

from plexus.crucible.l4 import stats
from plexus.crucible.util import FileLock, classify, keyword_score, percentile, scope_chain, words


def test_percentile_nearest_rank():
    v = list(range(1, 101))
    assert (
        percentile(v, 50) == 50
        and percentile(v, 95) == 95
        and percentile(v, 99) == 99
        and percentile(v, 100) == 100
    )
    assert percentile([7], 99) == 7 and percentile([], 50) == 0.0
    s = stats([1.0, 2.0, 3.0, 4.0])
    assert s["n"] == 4 and s["p50_ms"] == 2.0 and s["max_ms"] == 4.0
    assert stats([]) == {"n": 0}


def test_scope_chain():
    assert scope_chain("global") == ["global"]
    assert scope_chain("project:x") == ["project:x", "global"]
    assert scope_chain("user:bob") == ["user:bob", "global"]
    for bad in ("team:x", "project:", "", "x"):
        if bad == "":
            assert scope_chain(bad) == ["global"]
        else:
            with pytest.raises(ValueError):
                scope_chain(bad)


def test_keyword_score():
    q = words("Acme API version")
    assert keyword_score(q, "acme api version v1") == 1.0
    assert keyword_score(q, "the api") == pytest.approx(1 / 3)
    assert keyword_score([], "x") == 0.0


def fact(i, value, agents, vf=0):
    return {"id": i, "norm_value": value, "asserted_by": agents, "valid_from": vf}


def test_classify_matches_the_assert_fact_rules():
    cur = [fact("f1", "a", ["x"], 10)]
    dup, closing, clashing, ts = classify(cur, "y", "a", False, 5)
    assert dup["id"] == "f1" and closing == [] and clashing == [] and ts == 5
    dup, closing, clashing, ts = classify(
        cur, "x", "b", False, 5
    )  # own belief changes: supersede, ts never before valid_from
    assert dup is None and [f["id"] for f in closing] == ["f1"] and clashing == [] and ts == 10
    dup, closing, clashing, ts = classify(cur, "y", "b", False, 50)  # another agent: contradiction
    assert dup is None and closing == [] and [f["id"] for f in clashing] == ["f1"] and ts == 50
    dup, closing, clashing, ts = classify(cur, "y", "b", True, 50)  # explicit supersede
    assert [f["id"] for f in closing] == ["f1"] and clashing == []
    dup, *_ = classify(cur, "y", "other", False, 5, is_dup=lambda f: f["id"] == "f1")  # semantic duplicate
    assert dup["id"] == "f1"


def test_file_lock_excludes_threads_and_processes(tmp_path):
    lock = FileLock(tmp_path / "x.lock")
    counter = tmp_path / "counter.txt"
    counter.write_text("0")

    def bump(n: int) -> None:
        for _ in range(n):
            with lock.hold():
                counter.write_text(str(int(counter.read_text()) + 1))

    threads = [threading.Thread(target=bump, args=(25,)) for _ in range(4)]
    code = (
        "import sys; from plexus.crucible.util import FileLock; from pathlib import Path;"
        "l=FileLock(sys.argv[1]); c=Path(sys.argv[2]);"
        "exec('for _ in range(25):\\n with l.hold():\\n  c.write_text(str(int(c.read_text())+1))')"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", code, str(tmp_path / "x.lock"), str(counter)])
        for _ in range(2)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    assert int(counter.read_text()) == 4 * 25 + 2 * 25, "lost updates: the lock does not exclude"
