"""Deterministic, model-free 384-d hashed bag-of-words embedder. Test-only: no semantics beyond word overlap."""

from __future__ import annotations

import hashlib
import math
import re

from plexus.embed.base import DIM

_TOKEN = re.compile(r"[a-z0-9]+")


class HashEmbedder:
    """Signed feature hashing of lower-cased word tokens, then L2 normalisation.

    Identical token multisets give identical vectors; texts sharing no tokens are (almost) orthogonal.
    Empty input maps to a fixed unit vector so the cosine distance is always defined.
    """

    def __init__(self, dim: int = DIM):
        self.dim = dim

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = hashlib.md5(tok.encode("utf-8"), usedforsecurity=False).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            vec[idx] += 1.0 if h[4] & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            vec[0] = 1.0
            return vec
        return [x / norm for x in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]
