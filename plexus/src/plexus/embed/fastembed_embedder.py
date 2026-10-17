"""Local CPU embeddings: fastembed bge-small-en-v1.5 (384-d). No key; offline after first download."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from plexus.embed.base import DIM

MODEL_NAME = "BAAI/bge-small-en-v1.5"
# BGE's retrieval instruction for queries against stored passages (model card: query instruction)
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def query_prefix(model_name: str) -> str:
    """The query instruction for ``model_name`` (``""`` for non-BGE models or
    ``PLEXUS_BGE_QUERY_PREFIX=off``)."""
    if os.environ.get("PLEXUS_BGE_QUERY_PREFIX", "on").strip().lower() in ("off", "0", "false", "no"):
        return ""
    return BGE_QUERY_PREFIX if "bge" in model_name.lower() else ""


def default_cache_dir() -> str:
    return os.environ.get("PLEXUS_EMBED_CACHE") or str(Path.home() / ".cache" / "plexus-fastembed")


class FastEmbedder:
    """Lazy-loads the ONNX model once per instance (thread-safe). Output is already L2-normalised."""

    dim = DIM

    def __init__(self, model_name: str = MODEL_NAME, cache_dir: str | None = None):
        self.model_name = model_name
        self.cache_dir = cache_dir or default_cache_dir()
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        with self._lock:  # onnx sessions are safe to share, but keep batches simple and ordered
            return [[float(x) for x in v] for v in model.embed(list(texts))]

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        """Recall queries (P12): BGE's retrieval instruction + the text; stored facts use :meth:`embed`."""
        prefix = query_prefix(self.model_name)
        return self.embed([prefix + t for t in texts])
