"""P12 fix 1(e): recall embeds the query with BGE's retrieval instruction; stored facts as before."""

from __future__ import annotations

from plexus.embed.fastembed_embedder import BGE_QUERY_PREFIX, FastEmbedder, query_prefix
from plexus.mcp.embedding import CheckedEmbedder


class _Fake(FastEmbedder):
    def __init__(self):
        super().__init__()
        self.seen: list[str] = []

    def embed(self, texts):
        self.seen.extend(texts)
        return [[0.0] * 384 for _ in texts]


def test_query_prefix_only_for_bge_and_switchable(monkeypatch):
    assert query_prefix("BAAI/bge-small-en-v1.5") == BGE_QUERY_PREFIX
    assert query_prefix("sentence-transformers/all-MiniLM-L6-v2") == ""
    monkeypatch.setenv("PLEXUS_BGE_QUERY_PREFIX", "off")
    assert query_prefix("BAAI/bge-small-en-v1.5") == ""


def test_embed_query_prefixes_and_embed_does_not():
    f = _Fake()
    f.embed(["fact text"])
    f.embed_query(["billing cycle S07"])
    assert f.seen == ["fact text", BGE_QUERY_PREFIX + "billing cycle S07"]


def test_checked_embedder_forwards_the_query_form():
    f = _Fake()
    c = CheckedEmbedder(f)
    assert len(c.embed_query(["q"])[0]) == 384
    assert f.seen == [BGE_QUERY_PREFIX + "q"]


def test_engram_uses_the_query_form_only_for_recall_queries():
    from plexus.engram.service import Engram

    f = _Fake()
    eng = Engram(client=None, graph="g", embedder=f)  # type: ignore[arg-type]
    eng._embed_query("which database")
    eng._embed(["Acme database: postgres"])
    assert f.seen == [BGE_QUERY_PREFIX + "which database", "Acme database: postgres"]
