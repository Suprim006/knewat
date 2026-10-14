"""Embedder protocol shared by the local models, plus the dimension guard used before any vector is written."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

DIM = 384


class EmbeddingDimensionError(ValueError):
    """A vector does not have the 384 floats the vector indexes expect (FalkorDB would store it silently)."""


@runtime_checkable
class Embedder(Protocol):
    """Turns texts into L2-normalised vectors of ``dim`` floats (cosine == dot product)."""

    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def check_dim(vectors: Sequence[Sequence[float]], dim: int = DIM) -> list[list[float]]:
    """Return ``vectors`` unchanged if every one has exactly ``dim`` floats, else raise.

    FalkorDB 6.0.2 accepts a wrong-length ``vecf32`` on a vector-indexed property without an error and then
    never returns that node from the index, so a mismatch has to be caught before the write.
    """
    for i, v in enumerate(vectors):
        if len(v) != dim:
            raise EmbeddingDimensionError(f"embedding {i} has {len(v)} dimensions, expected {dim}")
    return vectors  # type: ignore[return-value]


def embed_checked(embedder: Embedder, texts: list[str], dim: int = DIM) -> list[list[float]]:
    """``embedder.embed(texts)`` validated with :func:`check_dim` (use this for every vector that is stored)."""
    return check_dim(embedder.embed(texts), dim)
