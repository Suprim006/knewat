"""Golden fixture for "forgetting off is byte-identical to today".

``build`` + ``QUERIES`` define a fixed world; ``orders`` returns the recall order for each query. The expected
orders in ``test_recall_off.py`` were captured by running ``orders`` against the code at main 4584219 (before
any P7-K change), via ``git archive``; see the test module.
"""

from __future__ import annotations

from typing import Any

FACTS = [
    ("Acme Notes API", "database", "PostgreSQL 16", "alice"),
    ("Acme Notes API", "cache", "Redis 7 with a 5 minute ttl", "alice"),
    ("Acme Notes API", "language", "Python 3.12", "bob"),
    ("Acme Notes API", "auth", "JWT bearer tokens", "bob"),
    ("Acme Notes API", "hosting", "Docker on a single VM", "carol"),
    ("Billing Service", "database", "MySQL 8", "carol"),
    ("Billing Service", "queue", "RabbitMQ for invoice events", "carol"),
    ("Web Frontend", "framework", "React 18 with Vite", "alice"),
    ("Web Frontend", "hosting", "static files on a CDN", "bob"),
    ("Search Index", "engine", "Elasticsearch 8", "alice"),
    ("Search Index", "reindex", "nightly full reindex at 02:00", "bob"),
    ("Team Handbook", "oncall", "weekly rotation on Mondays", "carol"),
]
QUERIES = [
    ("what database does the notes api use", 3),
    ("database", 8),
    ("hosting and deployment", 5),
    ("Redis cache ttl", 4),
    ("who is on call", 2),
    ("frontend framework React", 8),
]


def build(eng: Any, scope: str) -> None:
    for i, (subject, predicate, value, agent) in enumerate(FACTS):
        eng.assert_fact(subject, predicate, value, scope, agent, now=1_000 + i)
    # a supersede and a contradiction, so closed and clashing facts exist too
    eng.assert_fact("Acme Notes API", "database", "PostgreSQL 17", scope, "alice", now=2_000)
    eng.assert_fact("Billing Service", "database", "PostgreSQL 15", scope, "bob", now=2_001)


def groups(hits: list[dict[str, Any]]) -> list[list[Any]]:
    """The result as ``[[score, [texts...]], ...]``: adjacent hits with the same score form one sorted group.

    The hashed test embedder gives many facts the same distance to a query, and FalkorDB returns such ties
    in no fixed order (the baseline itself differs from run to run), so only the order BETWEEN distinct scores
    can be compared byte for byte.
    """
    out: list[list[Any]] = []
    for h in hits:
        score = round(h["score"], 6)
        if out and out[-1][0] == score:
            out[-1][1] = sorted([*out[-1][1], h["text"]])
        else:
            out.append([score, [h["text"]]])
    return out


def orders(eng: Any, scope: str, **kw: Any) -> list[list[list[Any]]]:
    return [groups(eng.recall(q, scope, k=k, **kw)) for q, k in QUERIES]
