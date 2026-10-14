"""Docs that must follow the code: queries.md lists every query; graph-model.md matches the schema files."""

from __future__ import annotations

import re
from pathlib import Path

from plexus.graph.queries import QueryLibrary

ROOT = Path(__file__).resolve().parents[2]
QUERIES_MD = (ROOT / "docs" / "queries.md").read_text(encoding="utf-8")
MODEL_MD = (ROOT / "docs" / "graph-model.md").read_text(encoding="utf-8")


def test_every_query_in_the_library_is_listed_in_docs_queries_md():
    missing = [n for n in QueryLibrary().names() if f"`{n}`" not in QUERIES_MD]
    assert not missing, f"add a row to docs/queries.md for: {missing}"


def test_docs_queries_md_names_no_query_that_does_not_exist():
    real = set(QueryLibrary().names())
    first_cells = [ln.split("|")[1] for ln in QUERIES_MD.splitlines() if ln.startswith("| `")]
    listed = {m for cell in first_cells for m in re.findall(r"`([a-z0-9_]+/[a-z0-9_]+)`", cell)}
    assert listed, "no query rows found in docs/queries.md"
    stale = sorted(listed - real)
    assert not stale, f"docs/queries.md lists queries that no longer exist: {stale}"


def test_graph_model_mentions_every_indexed_label_and_property():
    idx = (ROOT / "plexus" / "queries" / "schema" / "indexes.cypher").read_text(encoding="utf-8")
    pairs = re.findall(r"CREATE INDEX FOR \(n:(\w+)\) ON \(n\.(\w+)\)", idx)
    assert len(pairs) >= 44
    assert [lab for lab in {lab for lab, _ in pairs} if lab not in MODEL_MD] == []
    # a property is documented either as `Label.prop` or in a row that says it is on every label
    undocumented = [
        f"{lab}.{prop}"
        for lab, prop in pairs
        if f"{lab}.{prop}" not in MODEL_MD and not re.search(rf"`{prop}` on \*\*every\*\* label", MODEL_MD)
    ]
    assert not undocumented, f"docs/graph-model.md does not mention these indexes: {undocumented}"
