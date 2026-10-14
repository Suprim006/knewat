"""Server-side embedder: S2 settings (threads=1, batch_size=16) with a length guard.

FalkorDB silently accepts wrong-dimension vectors on write, so every vector that leaves the embedder is checked
for ``len == 384`` here. ``PLEXUS_EMBEDDER=hash`` (tests) keeps the hash embedder, still behind the guard.
"""

from __future__ import annotations

import os

from plexus.embed import DIM, Embedder, get_embedder
from plexus.embed.fastembed_embedder import MODEL_NAME, FastEmbedder

BATCH_SIZE = 16


class ServerFastEmbedder(FastEmbedder):
    """FastEmbedder with ``threads`` (default 1: CPU-limited containers) and small ONNX batches."""

    def __init__(self, threads: int | None = None, batch_size: int = BATCH_SIZE):
        cache = os.environ.get("PLEXUS_EMBED_CACHE") or os.environ.get("FASTEMBED_CACHE_PATH") or None
        super().__init__(MODEL_NAME, cache_dir=cache)
        self.threads = threads if threads is not None else int(os.environ.get("PLEXUS_EMBED_THREADS", "1"))
        self.batch_size = batch_size

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(
                        model_name=self.model_name, cache_dir=self.cache_dir, threads=self.threads
                    )
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        with self._lock:
            return [[float(x) for x in v] for v in model.embed(list(texts), batch_size=self.batch_size)]


class CheckedEmbedder:
    """Wraps an embedder and rejects any vector whose length is not 384."""

    dim = DIM

    def __init__(self, inner: Embedder):
        self.inner = inner

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = self.inner.embed(texts)
        if len(vecs) != len(texts) or any(len(v) != DIM for v in vecs):
            raise ValueError(f"embedder returned vectors that are not {DIM}-dimensional; refusing to write")
        return vecs


def make_embedder() -> Embedder:
    kind = (os.environ.get("PLEXUS_EMBEDDER") or "fastembed").lower()
    inner: Embedder = ServerFastEmbedder() if kind == "fastembed" else get_embedder(kind)
    return CheckedEmbedder(inner)
