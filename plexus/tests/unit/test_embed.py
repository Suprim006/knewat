from __future__ import annotations

import math

import pytest

from plexus.embed import DIM, Embedder, HashEmbedder, get_embedder


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hash_embedder_shape_and_norm():
    e = HashEmbedder()
    vs = e.embed(["The quick brown fox", "", "x"])
    assert len(vs) == 3
    for v in vs:
        assert len(v) == DIM == e.dim
        assert math.isclose(_dot(v, v), 1.0, abs_tol=1e-9)


def test_hash_embedder_deterministic_and_word_overlap():
    e = HashEmbedder()
    a, a2, b, c = e.embed(["uses postgres 16", "Uses  Postgres 16!", "uses postgres", "unrelated words here"])
    assert a == a2
    assert _dot(a, b) > 0.7
    assert abs(_dot(a, c)) < 0.4


def test_protocol_and_factory(monkeypatch):
    assert isinstance(HashEmbedder(), Embedder)
    monkeypatch.setenv("PLEXUS_EMBEDDER", "hash")
    assert isinstance(get_embedder(), HashEmbedder)
    assert get_embedder() is get_embedder()
    with pytest.raises(ValueError):
        get_embedder("nope")


@pytest.mark.slow
def test_fastembed_semantic(tmp_path):
    from plexus.embed import FastEmbedder

    e = FastEmbedder()
    v = e.embed(["The database is PostgreSQL", "We use Postgres as our database", "I like hiking"])
    assert len(v[0]) == DIM
    assert _dot(v[0], v[1]) > _dot(v[0], v[2])
