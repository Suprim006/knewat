from pathlib import Path

import pytest

from plexus.graph.queries import (
    MissingParam,
    MultiStatementError,
    QueryFormatError,
    QueryLibrary,
    UnexpectedParam,
    UnknownQuery,
)

GOOD = """\
// name: engram/assert_fact
// purpose: assert a fact
//   (continued purpose line)
// params: subject_id:str, predicate:str, tags:list[str]
// returns: id
// mode: rw
// A free comment line.
MATCH (n {id: $subject_id})
SET n.p = $predicate, n.tags = $tags
RETURN n.id AS id
"""


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def lib_root(tmp_path):
    write(tmp_path, "engram/assert_fact.cypher", GOOD)
    write(
        tmp_path,
        "schema/two.cypher",
        "// name: schema/two\n// purpose: p\n// params: none\n// returns: r\n// mode: ro\n"
        "// split: ;\nRETURN 1;\n// comment between\nRETURN 2;\n\n",
    )
    return tmp_path


def test_header_parsed(lib_root):
    q = QueryLibrary(lib_root).get("engram/assert_fact")
    assert q.name == "engram/assert_fact"
    assert q.purpose == "assert a fact (continued purpose line)"
    assert dict(q.params) == {"subject_id": "str", "predicate": "str", "tags": "list[str]"}
    assert q.returns == "id"
    assert q.mode == "rw"
    assert len(q.statements) == 1 and "A free comment" not in q.statements[0]


def test_names_are_paths_without_extension(lib_root):
    assert QueryLibrary(lib_root).names() == ["engram/assert_fact", "schema/two"]


def test_split_statements(lib_root):
    lib = QueryLibrary(lib_root)
    assert lib.get("schema/two").statements == ("RETURN 1", "RETURN 2")
    with pytest.raises(MultiStatementError):
        lib.render("schema/two").cypher  # noqa: B018


def test_render_ok(lib_root):
    rq = QueryLibrary(lib_root).render(
        "engram/assert_fact", {"subject_id": "s", "predicate": "p", "tags": []}
    )
    assert rq.mode == "rw" and rq.params["predicate"] == "p"
    assert "$subject_id" in rq.cypher  # values are never interpolated


def test_missing_param_rejected(lib_root):
    with pytest.raises(MissingParam) as e:
        QueryLibrary(lib_root).render("engram/assert_fact", {"subject_id": "s"})
    assert e.value.names == ["predicate", "tags"]
    assert isinstance(e.value, ValueError)


def test_unexpected_param_rejected(lib_root):
    with pytest.raises(UnexpectedParam) as e:
        QueryLibrary(lib_root).render(
            "engram/assert_fact", {"subject_id": "s", "predicate": "p", "tags": [], "evil": 1}
        )
    assert e.value.names == ["evil"]


def test_no_params_query_rejects_any(lib_root):
    lib = QueryLibrary(lib_root)
    lib.render("schema/two")
    with pytest.raises(UnexpectedParam):
        lib.render("schema/two", {"x": 1})


def test_unknown_query(lib_root):
    with pytest.raises(UnknownQuery):
        QueryLibrary(lib_root).render("nope/nothing")


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("// name: a/b\n// purpose: p\n// params: none\n// mode: ro\nRETURN 1", "returns"),
        (
            "// name: wrong\n// purpose: p\n// params: none\n// returns: r\n// mode: ro\nRETURN 1",
            "path-derived",
        ),
        ("// name: a/b\n// purpose: p\n// params: none\n// returns: r\n// mode: maybe\nRETURN 1", "mode"),
        ("// name: a/b\n// purpose: p\n// params: x\n// returns: r\n// mode: ro\nRETURN $x", "bad param"),
        ("// name: a/b\n// purpose: p\n// params: none\n// returns: r\n// mode: ro\nRETURN $x", "undeclared"),
        ("// name: a/b\n// purpose: p\n// params: x:int\n// returns: r\n// mode: ro\nRETURN 1", "unused"),
        ("// name: a/b\n// purpose: p\n// params: none\n// returns: r\n// mode: ro\n", "empty query body"),
        ("RETURN 1", "missing header"),
    ],
)
def test_malformed_file_fails_at_load(tmp_path, text, match):
    write(tmp_path, "a/b.cypher", text)
    with pytest.raises(QueryFormatError, match=match):
        QueryLibrary(tmp_path)


def test_missing_root():
    with pytest.raises(Exception, match="not found"):
        QueryLibrary("/definitely/not/here")


def test_real_library_loads_and_schema_queries_present():
    lib = QueryLibrary()
    for n in (
        "schema/indexes",
        "schema/fulltext",
        "schema/vector",
        "schema/list_indexes",
        "schema/list_constraints",
    ):
        assert n in lib
    assert lib.get("schema/list_indexes").mode == "ro"
    assert all(q.mode == "rw" for q in map(lib.get, ("schema/indexes", "schema/fulltext", "schema/vector")))
