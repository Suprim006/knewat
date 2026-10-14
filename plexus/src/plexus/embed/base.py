"""Embedder protocol shared by the local models."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

DIM = 384


@runtime_checkable
class Embedder(Protocol):
    """Turns texts into L2-normalised vectors of ``dim`` floats (cosine == dot product)."""

    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...
