"""B2 Vector: retrieval-based memory (Mem0-style) with the same local embedding model as Plexus.

Honest statement of the hybrid: facts and episodes are stored as float32 vectors in SQLite (``fact_vec`` /
``episode_vec``) and searched by brute-force cosine in numpy; **claims, leases, tasks, decisions and handoffs
live in the same SQLite tables as B1** because a vector store cannot do atomic claims. What differs from B1:

* ``recall`` is semantic (cosine over fact text embeddings), not BM25;
* ``assert_fact`` treats a paraphrase as a duplicate when the *value* embedding is within the same distance
  threshold Plexus uses **and** the numeric tokens agree (so ``16`` is not ``15``);
* no steps / READ edges, so ``why`` and ``knew_at`` raise :class:`Unsupported`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Sequence
from typing import Any

import numpy as np

from plexus.crucible.api import Unsupported
from plexus.crucible.backends.base import MAX_RECALL_K, recall_hit
from plexus.crucible.backends.sqlite import SqliteBackend
from plexus.crucible.util import fact_text, token_key
from plexus.embed import Embedder, embed_checked, get_embedder
from plexus.engram.service import FACT_DUP

VEC_SCHEMA = """
CREATE TABLE IF NOT EXISTS fact_vec(fact_id TEXT PRIMARY KEY, text_emb BLOB NOT NULL, value_emb BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS episode_vec(id TEXT PRIMARY KEY, emb BLOB NOT NULL);
"""


def _blob(v: Sequence[float]) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def _vec(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


class VectorBackend(SqliteBackend):
    name = "B2"
    label = "Vector"
    capabilities = frozenset({"as_of", "semantic_dedupe", "contradictions", "forget_cascade", "dependencies"})
    isolation = "one SQLite database file (facts + vectors) per tenant; the tenant name is validated before it becomes a path"

    def __init__(self, tenant: str, root: str, embedder: Embedder | str | None = None):
        self.embedder: Embedder = embedder if isinstance(embedder, Embedder) else get_embedder(embedder)
        super().__init__(tenant, root)

    def _init_schema(self, c: sqlite3.Connection) -> None:
        c.executescript(VEC_SCHEMA)  # no FTS: recall is vector-only

    def _embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(embed_checked(self.embedder, texts), dtype=np.float32)

    # -- no provenance bookkeeping ----------------------------------------------------------------------------
    def _step(self, c: sqlite3.Connection, agent_id: str, at: int) -> int:
        return -1

    @staticmethod
    def _reads(c: sqlite3.Connection, step_id: int, fact_ids: Iterable[str]) -> None:
        return None

    @staticmethod
    def _wrote(c: sqlite3.Connection, step_id: int, node_id: str, label: str, summary: str) -> None:
        return None

    def _log_recall(self, agent_id: str, hits: Sequence[dict[str, Any]]) -> None:
        return None

    # -- embeddings -----------------------------------------------------------------------------------------------
    def _index_episode(self, c: sqlite3.Connection, eid: str, text: str) -> None:
        c.execute("INSERT INTO episode_vec(id, emb) VALUES(?,?)", (eid, _blob(self._embed([text])[0])))

    def _prepare_fact(self, entity_name: str, predicate: str, value: str) -> Any:
        text_emb, value_emb = self._embed([fact_text(entity_name, predicate, value), value])
        return text_emb, value_emb

    def _dup_predicate(self, prepared: Any, value: str) -> Callable[[dict[str, Any]], bool]:
        _, value_emb = prepared
        key = token_key(value)

        def is_dup(f: dict[str, Any]) -> bool:
            if f["tokens"] != key or f.get("value_emb") is None:
                return False
            return float(1.0 - np.dot(_vec(f["value_emb"]), value_emb)) <= FACT_DUP

        return is_dup

    def _current(
        self, c: sqlite3.Connection, entity: str, predicate: str, scope: str
    ) -> list[dict[str, Any]]:  # type: ignore[override]
        cur = SqliteBackend._current(c, entity, predicate, scope)
        for f in cur:
            row = c.execute("SELECT value_emb FROM fact_vec WHERE fact_id=?", (f["id"],)).fetchone()
            f["value_emb"] = row["value_emb"] if row else None
        return cur

    def _index_fact(self, c: sqlite3.Connection, fact_id: str, text: str, prepared: Any) -> None:
        text_emb, value_emb = prepared
        c.execute(
            "INSERT INTO fact_vec(fact_id, text_emb, value_emb) VALUES(?,?,?)",
            (fact_id, _blob(text_emb), _blob(value_emb)),
        )

    # -- recall -----------------------------------------------------------------------------------------------------
    def recall(
        self, agent_id: str, query: str, scope: str = "global", k: int = 8, as_of: int | None = None
    ) -> list[dict[str, Any]]:
        if k <= 0:
            return []
        k = min(k, MAX_RECALL_K)
        clause, args, _ = self._visible_clause(scope, as_of)
        q = self._embed([query])[0]
        with self._conn() as c:
            rows = c.execute(
                "SELECT f.id, f.entity_name, f.predicate, f.value, f.status, v.text_emb "
                f"FROM facts f JOIN fact_vec v ON v.fact_id = f.id WHERE {clause}",
                args,
            ).fetchall()
        if not rows:
            return []
        mat = np.stack([_vec(r["text_emb"]) for r in rows])
        dist = 1.0 - mat @ q
        order = np.lexsort((np.array([r["id"] for r in rows]), dist))[:k]
        hits = []
        for i in order:
            r = rows[int(i)]
            text = fact_text(r["entity_name"], r["predicate"], r["value"])
            hits.append(
                recall_hit(
                    r["id"],
                    text,
                    r["entity_name"],
                    r["predicate"],
                    r["value"],
                    r["status"],
                    float(dist[int(i)]),
                )
            )
        return hits

    def why(self, node_id: str) -> dict[str, Any]:
        raise Unsupported(
            "why: the vector arm stores no BASED_ON / ASSERTED_BY links; Layer 2 asks an LLM over top-k retrieval"
        )

    def knew_at(self, agent_id: str, step_n: int) -> dict[str, Any]:
        raise Unsupported(
            "knew_at: the vector arm records no per-step reads; Layer 2 asks an LLM over top-k retrieval"
        )
