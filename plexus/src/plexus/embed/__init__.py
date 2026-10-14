"""Local embedding models. ``get_embedder()`` picks one by env ``PLEXUS_EMBEDDER`` (``fastembed`` | ``hash``)."""

from __future__ import annotations

import os

from plexus.embed.base import DIM, Embedder
from plexus.embed.hash_embedder import HashEmbedder

__all__ = ["DIM", "Embedder", "FastEmbedder", "HashEmbedder", "get_embedder"]

_singletons: dict[str, Embedder] = {}


def __getattr__(name: str):  # FastEmbedder imports lazily so `import plexus.embed` stays light
    if name == "FastEmbedder":
        from plexus.embed.fastembed_embedder import FastEmbedder

        return FastEmbedder
    raise AttributeError(name)


def get_embedder(kind: str | None = None) -> Embedder:
    """Return the process-wide embedder for ``kind`` (default: env ``PLEXUS_EMBEDDER``, else ``fastembed``)."""
    kind = (kind or os.environ.get("PLEXUS_EMBEDDER") or "fastembed").lower()
    if kind not in _singletons:
        if kind == "hash":
            _singletons[kind] = HashEmbedder()
        elif kind == "fastembed":
            from plexus.embed.fastembed_embedder import FastEmbedder

            _singletons[kind] = FastEmbedder()
        else:
            raise ValueError(f"unknown embedder '{kind}' (expected 'fastembed' or 'hash')")
    return _singletons[kind]
