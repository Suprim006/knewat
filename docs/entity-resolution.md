# Entity resolution (P9-d)

`assert_fact` anchors its duplicate / supersede / contradiction logic on `Entity {id}`, so facts about two spellings of
one thing ("Payment Service", "payment-service") only meet if both resolve to the same Entity. Until P9-d the lookups
were three separate reads followed by a `MERGE` on the *spelling*, so two concurrent writers using two spellings could
both miss and create two Entities (reproduced: 2 entities for a vector pair, 2 for a full-text pair).

## The statement

`queries/engram/resolve_entity.cypher` is one write statement:

1. full-text candidates: `CALL db.idx.fulltext.queryNodes('Entity', 'a|b|c')` (**OR** of the name tokens), same `kind`
   and same `num_key` (numbers / versions in the name), token Jaccard >= `FULLTEXT_JACCARD` (0.6), best first;
2. vector candidates: `CALL db.idx.vector.queryNodes('Entity', 'embedding', 5, vecf32($emb))`, same `kind` and
   `num_key`, cosine distance <= `ENTITY_NEAR` (0.10), nearest first;
3. exact: `OPTIONAL MATCH (ex:Entity {norm_name: $norm})`;
4. `coalesce(ex, head(ft), head(vec))`; only when nothing matched, `MERGE (n:Entity {norm_name}) ON CREATE SET ...`
   (`id`, `name`, `kind`, `num_key`, `tok`, `embedding`, `created_at`).

Returns one row `id, name, kind, how` with `how` in `exact | fulltext | vector | new`. Ties go to the oldest
`(created_at, id)`, so the outcome is deterministic.

FalkorDB 6.0.2 serialises writes per graph, so the lookups *inside* the write cannot interleave with another creator:
whoever runs second sees the first's Entity. Two quirks shaped the text (both re-verified with the real 384-d model in
`tests/integration/test_resolve_entity.py`): a bare `CALL` that yields 0 rows empties the row set (so each lookup is
`CALL { CALL ... RETURN collect(node) AS xs }`, which always returns one row), and `MERGE` must come after the reads
(`WITH` boundary).

`Engram.resolve_entity_ex` first reads `engram/find_entity_exact`, so an existing entity never writes; only a miss
runs the statement. It retries once on `unique constraint violation` (UNIQUE(`Entity.norm_name`) is the backstop).
`before_create` (the scope / episode / source check of `assert_fact`) runs after the exact read missed and before the
statement.

## The full-text AND -> OR fix

The old query ANDed all tokens, so "auth gateway service" did not find an older "auth gateway" (the AND needs `service`
in the old name) although the Jaccard filter would accept it (2/3). Resolution depended on creation order. The
candidate query is now OR; the Jaccard filter stays. `test_fulltext_is_independent_of_creation_order` covers both orders.

## What is not claimed

* **Not transitive.** A~B and B~C does not make A~C: a new name joins the best / oldest *existing* entity. With
  "alpha beta gamma delta" / "alpha beta gamma" / "beta gamma" the result is 1 or 2 entities depending on arrival order
  (never 3); `EXPECTED_BY_ORDER` in `tests/integration/test_entity_race.py` pins all six orders.
* The numeric guard compares the numbers in the *name* only: "auth-service-a" and "auth-service-b" can still merge
  through the vector path (the richer discriminator of P9-c is not used for entities yet).
* Entity `kind` is not part of the key: the same normalised name is one Entity whatever the kind (as before).

## Race results

50 threads behind a barrier (one connection each, real bge-small embeddings, a new graph per run, shuffled arrival):

| Case | Result |
|---|---|
| "Payment Service" / "payment-service" / "payment services" x 50 | **1 Entity in 20/20 runs**, every call returns the same id, exactly one `created` |
| the same flow on the pre-P9-d code | 2 Entities in every run sampled |
| 50 distinct product names, 5 runs | 50 Entities, all `new` |
| "Worker 0" .. "Worker 49" | 50 Entities (numeric guard) |
| "Service 1" / "service-2" x 25 | 2 Entities |
| X / Y / Z non-transitive chain x 50 | 1 or 2 Entities, never 3 |

## Migrating an existing tenant

```
plexus migrate entities --tenant demo --dry-run     # counts + report, writes nothing
plexus migrate entities --tenant demo               # backfill, add the constraint, report
plexus migrate entities --tenant demo --json        # the full report
```

1. lists names held by more than one Entity (exit code **2**; resolve them by hand, the constraint would go `FAILED`);
2. backfills `Entity.tok` and `Entity.num_key` in batches of 200 (idempotent). Entities without them never match the
   fuzzy lookups, so run this before relying on the new resolution on an old graph;
3. runs the idempotent `apply_schema`, which adds UNIQUE(`Entity.norm_name`) (a `FAILED` constraint is a logged
   warning, not an error, so a legacy tenant still starts);
4. read-only report of near-duplicate legacy entity pairs (younger -> older, via full-text and / or vector).

There is no automatic merge and no `SAME_AS` bridge: the facts of the two spellings already sit on two nodes, and
re-pointing `ABOUT` edges would need the duplicate / supersede / contradiction logic re-run plus alias-aware reads in
queries owned elsewhere. The report is for review.

Rollback: drop the constraint (`GRAPH.CONSTRAINT DROP <graph> UNIQUE NODE Entity PROPERTIES 1 norm_name`);
`tok` / `num_key` are additive properties.
