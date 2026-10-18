"""Local embedding models. ``get_embedder()`` picks one via env ``KNEWAT_EMBEDDER`` (fastembed | hash)."""

from __future__ import annotations

import os

from knewat.embed.base import DIM, Embedder, EmbeddingDimensionError, check_dim, embed_checked
from knewat.embed.hash_embedder import HashEmbedder

__all__ = [
    "DIM",
    "Embedder",
    "EmbeddingDimensionError",
    "FastEmbedder",
    "HashEmbedder",
    "check_dim",
    "embed_checked",
    "get_embedder",
]

_singletons: dict[str, Embedder] = {}


def __getattr__(name: str):  # FastEmbedder imports lazily so `import knewat.embed` stays light
    if name == "FastEmbedder":
        from knewat.embed.fastembed_embedder import FastEmbedder

        return FastEmbedder
    raise AttributeError(name)


def get_embedder(kind: str | None = None) -> Embedder:
    """Process-wide embedder for ``kind`` (default: env ``KNEWAT_EMBEDDER``, else ``fastembed``)."""
    kind = (kind or os.environ.get("KNEWAT_EMBEDDER") or "fastembed").lower()
    if kind not in _singletons:
        if kind == "hash":
            _singletons[kind] = HashEmbedder()
        elif kind == "fastembed":
            from knewat.embed.fastembed_embedder import FastEmbedder

            _singletons[kind] = FastEmbedder()
        else:
            raise ValueError(f"unknown embedder '{kind}' (expected 'fastembed' or 'hash')")
    return _singletons[kind]
