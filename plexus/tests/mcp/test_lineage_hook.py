"""The embedder guard that wraps every embedder the MCP runtime uses."""

from __future__ import annotations

import pytest

from plexus.embed import HashEmbedder
from plexus.mcp.embedding import CheckedEmbedder


def test_embedder_guard_rejects_wrong_dimension():
    class Bad:
        dim = 384

        def embed(self, texts):
            return [[0.0] * 10 for _ in texts]

    with pytest.raises(ValueError, match="384"):
        CheckedEmbedder(Bad()).embed(["x"])
    assert len(CheckedEmbedder(HashEmbedder()).embed(["x"])[0]) == 384
