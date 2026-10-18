"""L6-C loaders: one :class:`WorldC` into SQLite (B1h, tuned and untuned) and into a Plexus tenant graph (P arms).

SQLite: ``entities(id, name, fan)``, ``facts(id, entity_id, predicate, value)``, ``relates(src, dst, kind)``. ``fan`` is
stored as a column (what a SQL author could maintain), but the registered ``B1h`` arm does **not** read it: it computes the
fan inside its statement with a ``GROUP BY`` subquery, which is the same work as the Cypher arm's live count of ``ABOUT``
edges. ``tuned`` adds ``relates(src)``, ``relates(dst)``, ``facts(entity_id, predicate)`` and runs ``ANALYZE``.

Plexus: the model-v1 nodes and edges the product's ``recall`` reads. Range indexes first, bulk load in batches, then the
product schema (``apply_schema``: full-text, vector, the remaining range indexes and the UNIQUE constraints), then wait
until every index is ``OPERATIONAL``.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from redis.exceptions import TimeoutError as RedisTimeoutError

from plexus.crucible.l6.stores import BATCH, chunks
from plexus.crucible.l6.world_c import T0, WorldC
from plexus.embed import Embedder
from plexus.embed.hash_embedder import HashEmbedder
from plexus.engram.service import fact_text
from plexus.graph.client import GraphClient
from plexus.graph.schema import apply_schema
from plexus.graph.tenancy import graph_name

OPEN = 9_999_999_999_999
EMB_BATCH = 500  # rows per statement that carry a 384-d vector


def check_counts(world: WorldC, got: dict[str, int], arm: str) -> None:
    want = world.counts()
    bad = {k: (want[k], got[k]) for k in got if k in want and got[k] != want[k]}
    if bad:
        raise AssertionError(f"{arm}: store differs from the ledger (ledger, store): {bad}")


# ------------------------------------------------------------------------------------------------ SQLite
def build_sqlite_c(world: WorldC, path: str | Path, tuned: bool = True) -> tuple[str, dict[str, int]]:
    """Create the SQLite file at ``path`` (replaced if present). Returns ``(path, counts read back)``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.unlink(missing_ok=True)
    c = sqlite3.connect(p)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=OFF")
    c.executescript(
        "CREATE TABLE entities(id TEXT PRIMARY KEY, name TEXT, fan INTEGER);"
        "CREATE TABLE facts(id TEXT PRIMARY KEY, entity_id TEXT, predicate TEXT, value TEXT);"
        "CREATE TABLE relates(src TEXT, dst TEXT, kind TEXT);"
    )
    fans = world.fans()
    c.executemany(
        "INSERT INTO entities VALUES(?,?,?)", [(e["id"], e["name"], fans[e["id"]]) for e in world.entities]
    )
    c.executemany(
        "INSERT INTO facts VALUES(?,?,?,?)",
        [(f["id"], f["entity_id"], f["predicate"], f["value"]) for f in world.facts],
    )
    c.executemany(
        "INSERT INTO relates VALUES(?,?,?)", [(r["src"], r["dst"], r["kind"]) for r in world.relates]
    )
    c.commit()
    if tuned:
        c.execute("CREATE INDEX relates_src ON relates(src)")
        c.execute("CREATE INDEX relates_dst ON relates(dst)")
        c.execute("CREATE INDEX facts_entity_pred ON facts(entity_id, predicate)")
        c.execute("ANALYZE")
    c.execute("PRAGMA synchronous=NORMAL")
    got = {
        "entities": c.execute("SELECT count(*) FROM entities").fetchone()[0],
        "facts": c.execute("SELECT count(*) FROM facts").fetchone()[0],
        "relates": c.execute("SELECT count(*) FROM relates").fetchone()[0],
    }
    c.close()
    check_counts(world, got, "B1h")
    return str(p), got


# ------------------------------------------------------------------------------------------------ FalkorDB
def _wait_indexes(
    client: GraphClient, name: str, timeout_s: float = 300.0, allow_empty: bool = False
) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            st = {
                (r["label"], tuple(r["properties"]), str(r["status"]))
                for r in client.ro(name, "schema/list_indexes")
            }
        except (TimeoutError, RedisTimeoutError):  # the server is busy building; keep polling
            st = {("", (), "BUSY")}
        if (st or allow_empty) and all(s == "OPERATIONAL" for _, _, s in st):
            return
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"indexes not OPERATIONAL on {name}: {sorted(x for x in st if x[2] != 'OPERATIONAL')}"
            )
        time.sleep(0.25)


def plexus_counts_c(g: Any) -> dict[str, int]:
    def n(q: str) -> int:
        return int(g.ro_query(q).result_set[0][0])

    return {
        "entities": n("MATCH (n:Entity) RETURN count(n)"), "facts": n("MATCH (n:Fact) RETURN count(n)"),
        "relates": n("MATCH ()-[r:RELATES]->() RETURN count(r)"),
        "about": n("MATCH ()-[r:ABOUT]->() RETURN count(r)"),
        "in_scope": n("MATCH ()-[r:IN_SCOPE]->() RETURN count(r)"),
        "hubs": n("MATCH (e:Entity)<-[:ABOUT]-(f:Fact) WITH e, count(f) AS c WHERE c >= 100 RETURN count(e)"),
    }  # fmt: skip


def load_plexus_c(
    world: WorldC, client: GraphClient, tenant: str, embedder: Embedder | None = None
) -> tuple[str, dict[str, int]]:
    """Drop and recreate graph ``plexus_t_<tenant>`` holding the world. Returns ``(graph name, counts read back)``."""
    name = graph_name(tenant)
    client.delete_graph(name)
    g = client.graph(name)
    for label in ("Scope", "Entity", "Fact"):
        g.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")  # before the bulk load: every CREATE binds by id
    emb = (
        embedder or HashEmbedder()
    )  # the registered run uses the hash embedder; `--embedder fastembed` is the labelled post-hoc
    sid = world.scope_id
    g.query(
        "CREATE (:Scope {id: $id, kind: 'project', name: $name, created_at: $t})",
        {"id": sid, "name": "l6c", "t": T0},
    )
    ents = [
        {"id": e["id"], "name": e["name"], "norm": e["name"].lower(), "emb": v}
        for e, v in zip(world.entities, emb.embed([e["name"] for e in world.entities]), strict=True)
    ]
    for ch in chunks(ents, EMB_BATCH):
        g.query(
            "UNWIND $rows AS r CREATE (:Entity {id: r.id, name: r.name, norm_name: r.norm, kind: 'thing', "
            "created_at: $t, embedding: vecf32(r.emb)})",
            {"rows": ch, "t": T0},
        )
    name_of = {e["id"]: e["name"] for e in world.entities}
    fvec = emb.embed([fact_text(name_of[f["entity_id"]], f["predicate"], f["value"]) for f in world.facts])
    frows = [
        {"id": f["id"], "e": f["entity_id"], "p": f["predicate"], "v": f["value"], "emb": v}
        for f, v in zip(world.facts, fvec, strict=True)
    ]
    for ch in chunks(frows, EMB_BATCH):
        g.query(
            "UNWIND $rows AS r MATCH (e:Entity {id: r.e}) MATCH (s:Scope {id: $sid}) "
            "CREATE (f:Fact {id: r.id, predicate: r.p, value: r.v, status: 'active', confidence: 1.0, "
            "valid_from: $t, valid_to: $open, created_at: $t, scope_id: $sid, embedding: vecf32(r.emb)}) "
            "CREATE (f)-[:ABOUT]->(e) CREATE (f)-[:IN_SCOPE]->(s)",
            {"rows": ch, "sid": sid, "t": T0, "open": OPEN},
        )
    for ch in chunks([{"a": r["src"], "b": r["dst"], "k": r["kind"]} for r in world.relates], BATCH):
        g.query(
            "UNWIND $rows AS r MATCH (a:Entity {id: r.a}) MATCH (b:Entity {id: r.b}) "
            "CREATE (a)-[:RELATES {kind: r.k, scope_id: $sid, at: $t}]->(b)",
            {"rows": ch, "sid": sid, "t": T0},
        )
    # full-text + vector + the remaining range indexes, after the bulk load. On a 44k-fact graph the server builds each
    # index in the background and a later schema statement can wait behind it past the client's 5 s socket timeout:
    # wait for the indexes to finish and re-run (apply_schema tolerates "already indexed").
    for attempt in range(30):
        try:
            apply_schema(client, name)
            break
        except (TimeoutError, RedisTimeoutError):
            if attempt == 29:
                raise
            _wait_indexes(client, name, allow_empty=True)
    _wait_indexes(client, name)
    got = plexus_counts_c(g)
    check_counts(world, got, "P")
    want = world.counts()
    if got["about"] != want["facts"] or got["in_scope"] != want["facts"]:
        raise AssertionError(
            f"P: ABOUT/IN_SCOPE edges {got['about']}/{got['in_scope']} != facts {want['facts']}"
        )
    return name, got
