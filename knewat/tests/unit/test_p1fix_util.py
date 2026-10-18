from __future__ import annotations

import pytest

from knewat.embed import DIM, EmbeddingDimensionError, HashEmbedder, check_dim, embed_checked
from knewat.engram.service import numeric_tokens, token_key


def test_numeric_tokens_are_sorted_multiset():
    assert numeric_tokens("v1.2.3") == ["1.2.3"]
    assert numeric_tokens("Python 3.11 and 3.11 on port 8080") == ["3.11", "3.11", "8080"]
    assert numeric_tokens("no digits here") == []
    assert numeric_tokens("max 10 retries") != numeric_tokens("max 3 retries")
    assert token_key("b 2 a 1") == token_key("1 then 2") == "1 2"
    assert token_key("nothing") == ""


def test_numeric_tokens_ignore_trailing_dot_and_keep_versions_apart():
    assert numeric_tokens("Version 16.") == ["16"]
    assert token_key("PostgreSQL 15") != token_key("PostgreSQL 16")
    assert token_key("service-1") != token_key("service-2")
    assert token_key("Postgres version 16") == token_key("PostgreSQL 16")


def test_check_dim_accepts_384_and_rejects_others():
    assert check_dim([[0.0] * DIM]) == [[0.0] * DIM]
    with pytest.raises(EmbeddingDimensionError, match="384"):
        check_dim([[0.0] * 3])
    with pytest.raises(ValueError):  # EmbeddingDimensionError is a ValueError
        check_dim([[0.0] * DIM, [0.0] * (DIM + 1)])


def test_embed_checked_wraps_any_embedder():
    assert len(embed_checked(HashEmbedder(), ["a", "b"])) == 2

    class Bad:
        dim = 3

        def embed(self, texts):
            return [[1.0, 0.0, 0.0] for _ in texts]

    with pytest.raises(EmbeddingDimensionError):
        embed_checked(Bad(), ["x"])
