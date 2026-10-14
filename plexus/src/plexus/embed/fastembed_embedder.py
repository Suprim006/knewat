"""Local CPU embeddings: fastembed ``BAAI/bge-small-en-v1.5`` (384-d). No key, no network after the first download."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from plexus.embed.base import DIM

MODEL_NAME = "BAAI/bge-small-en-v1.5"


def default_cache_dir() -> str:
    return os.environ.get("PLEXUS_EMBED_CACHE") or str(Path.home() / ".cache" / "plexus-fastembed")


class FastEmbedder:
    """Lazy-loads the ONNX model once per instance (thread-safe). bge-small output is already L2-normalised."""

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
