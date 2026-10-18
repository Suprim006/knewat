# ruff: noqa: E501
"""``knewat code baseline | scan`` against a real server and a temp git repository."""

from __future__ import annotations

import time

import pytest

from knewat.cli import build_parser
from knewat.codescan.client import McpCallError, run_session
from knewat.codescan.paths import canonical_path

from .conftest import commit_all

V1 = """\
def add(a, b):
    return a + b


def sub(a, b):
    return a - b
"""
V2 = V1.replace("return a + b", "return a + b + 0")  # only `add` changes
README = "# Math\nadd adds, sub subtracts.\n"


def run(argv: list[str]) -> int:
    a = build_parser().parse_args(argv)
    return a.fn(a)


def mcp(live, fn, agent="alice"):
    return run_session(live.url, live.tenant, agent, fn)


@pytest.fixture
def world(live, repo, capsys):
    """A repo with app/math.py (add, sub) and README.md, committed; facts in the graph about each."""
    (repo / "app").mkdir()
    (repo / "app" / "math.py").write_text(V1, encoding="utf-8", newline="\n")
    (repo / "README.md").write_text(README, encoding="utf-8", newline="\n")
    c1 = commit_all(repo, "first")
    py, md = canonical_path(str(repo / "app" / "math.py")), canonical_path(str(repo / "README.md"))

    async def setup(s):
        src = (await s.call("add_source", title="README", uri=md, kind="doc"))["source_id"]
        ids = {}
        ids["readme_fact"] = (
            await s.call(
                "assert_fact", subject="Math", predicate="purpose", value="adds and subtracts", source_id=src
            )
        )["fact_id"]
        ids["add"] = (await s.call("assert_fact", subject="add", predicate="behaviour", value="sums"))[
            "fact_id"
        ]
        ids["sub"] = (await s.call("assert_fact", subject="sub", predicate="behaviour", value="differences"))[
            "fact_id"
        ]
        ids["file"] = (await s.call("assert_fact", subject="math.py", predicate="role", value="helpers"))[
            "fact_id"
        ]
        await s.call("anchor_fact", fact_id=ids["add"], path=py, symbol="add")
        await s.call("anchor_fact", fact_id=ids["sub"], path=py, symbol="sub")
        await s.call("anchor_fact", fact_id=ids["file"], path=py)
        return src, ids

    src, ids = mcp(live, setup)
    base = ["--repo", str(repo), "--tenant", live.tenant, "--url", live.url]
    assert run(["code", "baseline", *base, "--paths", "app/math.py", "README.md"]) == 0
    out = capsys.readouterr().out
    return {
        "repo": repo,
        "py": py,
        "md": md,
        "ids": ids,
        "src": src,
        "base": base,
        "c1": c1,
        "baseline_out": out,
    }


def _states(live):
    rows = live.rows("MATCH (f:Fact) RETURN f.id, coalesce(f.verify_state,'verified')")
    return dict(rows)


def test_baseline_marks_nothing_and_records_hashes(live, world):
    out = world["baseline_out"]
    assert "baseline" in out and "0 memories made suspect" in out
    assert set(_states(live).values()) == {"verified"}
    hashes = dict(live.rows("MATCH (a:CodeAnchor) RETURN a.symbol, a.hash"))
    assert set(hashes) == {"", "add", "sub"} and all(hashes.values())
    assert live.rows("MATCH (c:Change) RETURN count(c)") == [[0]]
    assert live.rows("MATCH (s:Source {uri:$u}) RETURN s.content_hash <> ''", u=world["md"]) == [[True]]


def test_scan_of_a_commit_marks_only_the_changed_function_and_file_level_facts(live, world, capsys):
    repo, ids = world["repo"], world["ids"]
    (repo / "app" / "math.py").write_text(V2, encoding="utf-8", newline="\n")
    c2 = commit_all(repo, "tweak add")
    capsys.readouterr()
    assert run(["code", "scan", *world["base"], "--commit", c2]) == 0
    out = capsys.readouterr().out
    st = _states(live)
    assert st[ids["add"]] == "suspect" and st[ids["file"]] == "suspect"
    assert st[ids["sub"]] == "verified" and st[ids["readme_fact"]] == "verified"
    assert "2 memories may be stale" in out and "add behaviour: sums" in out and f"changed in {c2}" in out
    (change,) = live.rows("MATCH (c:Change) RETURN c.commit, c.at")
    assert change[0] == c2


def test_scan_notices_a_changed_doc_through_its_source(live, world, capsys):
    repo, ids = world["repo"], world["ids"]
    (repo / "README.md").write_text(README + "More.\n", encoding="utf-8", newline="\n")
    c2 = commit_all(repo, "docs")
    assert run(["code", "scan", *world["base"], "--commit", c2]) == 0
    st = _states(live)
    assert st[ids["readme_fact"]] == "suspect"
    assert [v for k, v in st.items() if k != ids["readme_fact"]] == ["verified"] * 3


def test_scan_working_tree_paths(live, world, capsys):
    repo, ids = world["repo"], world["ids"]
    (repo / "app" / "math.py").write_text(V1.replace("a - b", "a - b - 0"), encoding="utf-8", newline="\n")
    assert run(["code", "scan", *world["base"], "--paths", "app/math.py"]) == 0
    st = _states(live)
    assert st[ids["sub"]] == "suspect" and st[ids["add"]] == "verified"
    assert live.rows("MATCH (c:Change) RETURN c.commit") == [[""]]  # a working-tree edit has no commit


def test_a_deleted_function_makes_its_facts_suspect(live, world):
    repo, ids = world["repo"], world["ids"]
    (repo / "app" / "math.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8", newline="\n"
    )
    c2 = commit_all(repo, "drop sub")
    assert run(["code", "scan", *world["base"], "--commit", c2]) == 0
    st = _states(live)
    assert st[ids["sub"]] == "suspect" and st[ids["add"]] == "verified"


def test_scan_of_a_repo_without_a_server_fails_cleanly(world, capsys):
    capsys.readouterr()
    code = run(
        [
            "code",
            "scan",
            "--repo",
            str(world["repo"]),
            "--tenant",
            "x",
            "--url",
            "http://127.0.0.1:9",
            "--paths",
            "README.md",
            "--timeout",
            "3",
        ]
    )
    assert code == 1
    assert "knewat code scan:" in capsys.readouterr().err


def test_end_to_end_verify_and_time_travel(live, world):
    """The manual gate scenario: edit one function, scan, only its facts are suspect, verify as changed, as_of."""
    repo, ids = world["repo"], world["ids"]
    time.sleep(1.1)  # git commit times have one-second resolution: the change must be later than the facts
    (repo / "app" / "math.py").write_text(V2, encoding="utf-8", newline="\n")
    c2 = commit_all(repo, "tweak add")
    assert run(["code", "scan", *world["base"], "--commit", c2]) == 0

    async def go(s):
        todo = await s.call("facts_to_verify")
        v = await s.call(
            "verify_fact", fact_id=ids["add"], still_true=False, new_value="sums and adds zero", commit=c2
        )
        after = await s.call("facts_to_verify")
        at = live.rows("MATCH (c:Change) RETURN c.at")[0][0]
        before = await s.call("as_of", subject="add", predicate="behaviour", t=at - 1)
        between = await s.call("as_of", subject="add", predicate="behaviour", t=at + 1)
        return todo, v, after, at, before, between

    todo, v, after, at, before, between = mcp(live, go, "bob")
    assert {f["fact_id"] for f in todo["facts"]} == {ids["add"], ids["file"]}
    assert v["outcome"] == "changed" and v["valid_to"] == at
    assert {f["fact_id"] for f in after["facts"]} == {ids["file"]}
    assert before["as_of"]["value"] == "sums"
    assert between["as_of"]["value"] == "sums and adds zero"


def test_baseline_can_list_the_tracked_files_from_the_database(live, repo, monkeypatch, capsys):
    from tests.conftest import TEST_DB_HOST, TEST_DB_PORT

    (repo / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8", newline="\n")
    (repo / "b.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    commit_all(repo, "files")
    a, b = canonical_path(str(repo / "a.py")), canonical_path(str(repo / "b.py"))

    async def setup(s):
        await s.call("add_source", title="a", uri=a)
        await s.call("add_source", title="web", uri="https://example.com/page")
        f = (await s.call("assert_fact", subject="S", predicate="p", value="v"))["fact_id"]
        await s.call("anchor_fact", fact_id=f, path=b)

    mcp(live, setup)
    monkeypatch.setenv("FALKORDB_HOST", TEST_DB_HOST)
    monkeypatch.setenv("FALKORDB_PORT", str(TEST_DB_PORT))
    capsys.readouterr()
    assert run(["code", "baseline", "--repo", str(repo), "--tenant", live.tenant, "--url", live.url]) == 0
    assert "2 files" in capsys.readouterr().out
    assert {r[0] for r in live.rows("MATCH (a:CodeAnchor {symbol:''}) RETURN a.path")} == {a, b}


def test_mcp_errors_are_reported_not_raised_as_tracebacks(live):
    async def go(s):
        return await s.call("anchor_fact", fact_id="nope", path="C:/x.py")

    with pytest.raises(McpCallError, match="nope"):
        mcp(live, go)
