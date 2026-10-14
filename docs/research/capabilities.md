# FalkorDB capabilities & limits — Track 02 (agent memory) reference

Read 2026-10-14 from docs.falkordb.com (`.md` pages). "not documented" = searched, nothing found. **[CONFLICT]** = docs disagree. Version 6.0 = Rust engine, columnar batch runtime, MVCC; Cypher/APIs unchanged ([blog](https://www.falkordb.com/blog/announcing-falkordb-6-0/)).

## 1. Multi-graph / tenants / ACL
- Each graph is one Redis key. `GRAPH.LIST` (no args) lists graph keys of the selected Redis DB only; may include internal `telemetry{A}` graphs ([graph.list](https://docs.falkordb.com/commands/graph.list.md)).
- `GRAPH.COPY <src> <dest>`: source stays readable/writable during copy; copies nodes, rels, props, indexes and constraints; snapshot-consistent; errors if dest exists ([graph.copy](https://docs.falkordb.com/commands/graph.copy.md)). Python `graph_z = graph_a.copy('Z')`.
- `GRAPH.DELETE graph_name`: permanent; takes a write lock ([graph.delete](https://docs.falkordb.com/commands/graph.delete.md)); `ASYNC_DELETE` defaults `yes` ([configuration](https://docs.falkordb.com/getting-started/configuration.md)).
- Max graph count / graph size: **not documented**.
- Per-user/tenant graph precedent: Graphiti `Graphiti(uri='falkor://localhost:6379', graph_name='user1_memory')` ([graphiti](https://docs.falkordb.com/agentic-memory/graphiti.md)); Mem0 uses `mem0_alice`, "no user_id filtering needed in Cypher" ([mem0](https://docs.falkordb.com/agentic-memory/mem0.md)).
- Cluster: a graph lives wholly on one shard; different graphs spread over shards ([cluster](https://docs.falkordb.com/operations/cluster.md)). Replicas are async and serve `GRAPH.RO_QUERY` ([replication](https://docs.falkordb.com/operations/replication.md)).
- **ACL** ([acl](https://docs.falkordb.com/commands/acl.md)):
  ```
  ACL SETUSER <username> [rule1] [rule2] ...
  ACL SETUSER reader on >pass +GRAPH.RO_QUERY %R~*
  +@all ~app1:* %R~app2:*      # full on app1:*, read-only on app2:*
  ```
  `~pat` = RW on matching graphs; `%R~`/`%W~`/`%RW~` fine-grained (`%RW~` ≡ `~`). A command that mutates *and* returns data needs R+W; R excludes `GRAPH.LIST` metadata.
- Persistence ([acl-persistence](https://docs.falkordb.com/operations/durability/acl-persistence.md)): `ACL SETUSER` is memory-only; start with `--aclfile <file>` (must exist beforehand), then `ACL SAVE`; can't mix with inline `user` directives; `ACL SETUSER default off` for prod. Docker: `-e REDIS_ARGS="--appendonly yes --aclfile /var/lib/falkordb/data/users.acl"`.

## 2. Concurrency & atomicity
- Per-graph reader-writer: parallel readers, **one writer at a time per graph** (FIFO queue); readers get a snapshot from query start, never partial writes ([concurrency](https://docs.falkordb.com/design/concurrency.md)).
- Every write query is atomic incl. new-label schema rollback; `WITH`/`UNION` compounds are one unit ([concurrency](https://docs.falkordb.com/design/concurrency.md)).
- No native multi-query transactions; use `MULTI`/`EXEC`, which "serializes all enclosed commands, so concurrent operations on other graphs will also be blocked" ([concurrency](https://docs.falkordb.com/design/concurrency.md)).
- 6.0 MVCC: "reads never block and writes stay consistent" ([blog](https://www.falkordb.com/blog/announcing-falkordb-6-0/)). **[CONFLICT/gap]** concurrency page still describes serialized writers.
- Writes to **different** graphs in parallel: **not documented explicitly**. `THREAD_COUNT` = pool size = max concurrently processed queries ([configuration](https://docs.falkordb.com/getting-started/configuration.md)); the MULTI/EXEC warning implies other-graph commands are otherwise independent. Benchmark it.
- Config ([configuration](https://docs.falkordb.com/getting-started/configuration.md)): load-time only: `THREAD_COUNT` (default = logical cores), `CACHE_SIZE`, `OMP_THREAD_COUNT`, `NODE_CREATION_BUFFER`. Runtime-settable: `MAX_QUEUED_QUERIES` (default unlimited; overflow → `Max pending queries exceeded`), `TIMEOUT_MAX`/`TIMEOUT_DEFAULT` (read and write; default 0 = off), `RESULTSET_SIZE`, `QUERY_MEM_CAPACITY` (bytes/query), `DELTA_MAX_PENDING_CHANGES`, `DELAY_INDEXING`, `JS_HEAP_SIZE` (256 MB).
  ```
  redis-server --loadmodule ./falkordb.so THREAD_COUNT 4
  redis-cli GRAPH.CONFIG SET MAX_QUEUED_QUERIES 500
  GRAPH.QUERY wikipedia "MATCH p=()-[*]->() RETURN p" TIMEOUT 500
  ```
  Per-query `TIMEOUT` can't exceed `TIMEOUT_MAX`; deprecated `TIMEOUT` applied to reads only.
  - **Observed on the official Docker image (`falkordb/falkordb:latest` = 6.0.2, 2026-10-14):** the module loads with args `MAX_QUEUED_QUERIES 25 TIMEOUT 1000 RESULTSET_SIZE 10000` (from `MODULE LIST`). That is not the documented defaults (unlimited / off). `THREAD_COUNT` = 12 on this machine. Override with `FALKORDB_ARGS` before any load test.
- Durability via RDB/AOF ([persistence](https://docs.falkordb.com/operations/durability/persistence.md)).

## 3. Indexes & constraints
- **Vector** (HNSW; `cosine` or `euclidean`; dim 1–4096) ([vector-index](https://docs.falkordb.com/cypher/indexing/vector-index.md)):
  ```
  CREATE VECTOR INDEX FOR (p:Product) ON (p.description) OPTIONS {dimension:128, similarityFunction:'euclidean'}
  -- optional M (16), efConstruction (200), efRuntime (10); also relationships: FOR ()-[e:Call]->() ON (e.summary)
  CREATE (p:Product {description: vecf32([2.1, 0.82, 1.3])})
  CALL db.idx.vector.queryNodes(label: STRING, attribute: STRING, k: INTEGER, query: VECTOR) YIELD node, score
  CALL db.idx.vector.queryRelationships(relationshipType: STRING, attribute: STRING, k: INTEGER, query: VECTOR) YIELD relationship, score
  ```
  Approximate results; memory ≈ `vectors × dimensions × 4 bytes + ~20%` (1M×768 ≈ 3 GB); docs say vector queries "don't combine well with property filters". Score direction is ambiguous (example uses `ORDER BY score DESC` with cosine) → test. Exact distance fns: `vec.euclideanDistance(a,b)`, `vec.cosineDistance(a,b)` ([functions](https://docs.falkordb.com/cypher/functions.md)).
- **Full-text** (RediSearch) ([fulltext-index](https://docs.falkordb.com/cypher/indexing/fulltext-index.md)):
  ```
  CREATE FULLTEXT INDEX FOR (n:Movie) ON (n.title) OPTIONS { language: 'German', stopwords: ['a', 'ab'] }
  CALL db.idx.fulltext.createNodeIndex('Movie', 'title')
  CALL db.idx.fulltext.queryNodes('Movie', 'Jun*|%Forst%1') YIELD node, score
  CALL db.idx.fulltext.queryRelationships('Manager', 'Charlie Munger') YIELD relationship
  CALL db.idx.fulltext.drop('Movie')
  ```
  Prefix `Jun*` (word end only), fuzzy `%term%1` (distance 1–3), `|` OR, `-` NOT; TF-IDF score.
- **Range** (equality/range/geo/scalar arrays; not maps/vectors) ([range-index](https://docs.falkordb.com/cypher/indexing/range-index.md)): `CREATE INDEX FOR (p:Person) ON (p.age)`, `CREATE INDEX FOR ()-[f:FOLLOW]-() ON (f.created_at)`, `DROP INDEX ON :Person(age)`. Not used for `<>` ([known-limitations](https://docs.falkordb.com/cypher/known-limitations.md)). List: `CALL db.indexes()`.
- **Constraints** are commands, not Cypher ([constraint-create](https://docs.falkordb.com/commands/graph.constraint-create.md)):
  ```
  GRAPH.CONSTRAINT CREATE key MANDATORY|UNIQUE NODE label | RELATIONSHIP reltype PROPERTIES propCount prop [prop...]
  GRAPH.QUERY g "CREATE INDEX FOR (p:Person) ON (p.first_name, p.last_name)"
  GRAPH.CONSTRAINT CREATE g UNIQUE NODE Person PROPERTIES 2 first_name last_name   # -> PENDING
  ```
  Async (`UNDER CONSTRUCTION` → `OPERATIONAL`/`FAILED`); UNIQUE needs a prior exact-match index and that index can't be dropped; not enforced for null/array values; `GRAPH.CONSTRAINT DROP` takes same args ([constraint-drop](https://docs.falkordb.com/commands/graph.constraint-drop.md)); `CALL db.constraints()` ([procedures](https://docs.falkordb.com/cypher/procedures.md)).
- Upsert: `MERGE ... ON CREATE SET ... ON MATCH SET ...` ([merge](https://docs.falkordb.com/cypher/merge.md)).

## 4. Temporal
- Types Date, Time, DateTime, Duration (ISO 8601), usable in properties/params/expressions ([datatypes](https://docs.falkordb.com/datatypes.md)):
  ```
  CREATE (:Event { name: "Conference", date: date("2025-09-15") })
  RETURN localdatetime("2025-06-29T13:45:00").year      // localdatetime() = now
  CREATE (:Cooldown { period: duration("P3DT12H") })
  RETURN date("2025-01-01") + duration("P1M")
  RETURN localdatetime("2025-06-29T13:00:00") - duration("PT30M")
  ```
  `timestamp()` = ms since epoch ([functions](https://docs.falkordb.com/cypher/functions.md)). Comparison operators documented for these types.
- Gaps: a `datetime()` function and timezone-aware construction are **not documented** (docs use `localdatetime()`); **[CONFLICT]** [cypher-support](https://docs.falkordb.com/cypher/cypher-support.md) lists "Temporal arithmetic functions" as unsupported yet datatypes shows date±duration. Docs don't say which temporal types are storable as properties → verify. FLEX: `flex.date.format/parse/truncate/toTimeZone` ([flex](https://docs.falkordb.com/udfs/flex/index.md)).

## 5. Paths & algorithms
- Var-length `-[:TYPE*minHops..maxHops]->` (defaults 1..∞); named paths `MATCH p=...` with `nodes(p)`, `relationships(p)`, `length(p)`; clients can return paths directly ([match](https://docs.falkordb.com/cypher/match.md), [functions](https://docs.falkordb.com/cypher/functions.md)).
- `shortestPath` returns one path; endpoints must be resolved beforehand and **no property filters in the pattern**; `allShortestPaths` returns all ([functions](https://docs.falkordb.com/cypher/functions.md)):
  `MATCH (a:City{name:'A'}),(g:City{name:'G'}) WITH shortestPath((a)-[*]->(g)) as p RETURN length(p), [n in nodes(p) | n.name] as pathNodes`
- Per-hop var-length filter via `prev()`: `WHERE coalesce(prev(s.priority), s.priority) <= s.priority` (same page).
- `CALL algo.SPpaths({sourceNode, targetNode, relTypes, weightProp, costProp, maxCost, maxLen, relDirection:"outgoing"|"incoming"|"both", pathCount}) YIELD path, pathWeight, pathCost` ([sppath](https://docs.falkordb.com/algorithms/sppath.md)); `algo.SSpaths` (no target) ([sspath](https://docs.falkordb.com/algorithms/sspath.md)); `CALL algo.bfs(start_node, max_depth, relationship) YIELD nodes, edges` ([bfs](https://docs.falkordb.com/algorithms/bfs.md)).
- `CALL algo.pageRank(label, relationship-type) YIELD node, score` ([pagerank](https://docs.falkordb.com/algorithms/pagerank.md)); `CALL algo.betweenness({nodeLabels, relationshipTypes, samplingSize, samplingSeed}) YIELD node, score` (sampled, default 32) ([betweenness](https://docs.falkordb.com/algorithms/betweenness-centrality.md)); `CALL algo.labelPropagation([config]) YIELD node, communityId` (`maxIterations` 10) ([cdlp](https://docs.falkordb.com/algorithms/cdlp.md)); `CALL algo.wcc([config]) YIELD node, componentId` ([wcc](https://docs.falkordb.com/algorithms/wcc.md)). Runtime on big graphs: not documented.

## 6. UDFs & FLEX
- JavaScript; `falkor.register('Name', fn)`; server-wide libraries; call as `Lib.Fn(args)` ([udfs](https://docs.falkordb.com/udfs/index.md)):
  ```
  GRAPH.UDF LOAD [REPLACE] <Lib> <script>   |   GRAPH.UDF LIST [Lib] [WITHCODE]   |   GRAPH.UDF DELETE <library>   |   GRAPH.UDF FLUSH
  RETURN StringUtils.UpperCaseOdd('abcdef')
  ```
  Python `db.udf_load(lib, script)`. UDFs see Node/Edge/Path, `node.getNeighbors({...})`, `graph.traverse`, `graph.getNodeById`; **read-only — cannot modify the graph**. **[CONFLICT]** [cypher-support](https://docs.falkordb.com/cypher/cypher-support.md) lists UDFs "Unsupported" but its FAQ and the UDF page say supported.
- FLEX (github.com/FalkorDB/flex, load as a UDF library first): `flex.sim.jaccard`, `flex.text.levenshtein/jaroWinkler/regexGroups/…`, `flex.coll.*`, `flex.map.*`, `flex.json.*`, `flex.date.*`, `flex.bitwise.*` ([flex](https://docs.falkordb.com/udfs/flex/index.md)).

## 7. Python client (falkordb-py)
- Sync: `db = FalkorDB(host="localhost", port=6379)`; `g = db.select_graph("social")`; `g.query(...)`; `g.ro_query(...)`; `g.copy(...)`; `g.delete()` ([README](https://github.com/FalkorDB/falkordb-py/blob/main/README.md)).
- Async: `from falkordb.asyncio import FalkorDB`; `pool = BlockingConnectionPool(max_connections=16, timeout=None, decode_responses=True)`; `db = FalkorDB(connection_pool=pool)`; `await g.query(...)`; `asyncio.gather(...)`; `await pool.aclose()` ([README](https://github.com/FalkorDB/falkordb-py/blob/main/README.md)). Optional `pip install "FalkorDB[hiredis]"` for large/vector results.
- Constructor takes `connection_pool`, `max_connections`, `socket_timeout`, `socket_connect_timeout`, `retry_on_error`, ssl*, cluster args (`read_from_replicas`, `startup_nodes`) ([falkordb.py](https://github.com/FalkorDB/falkordb-py/blob/main/falkordb/falkordb.py)).
- `query(q, params=None, timeout=None)` / `ro_query(...)`; `timeout` in ms; `params` dict becomes a `CYPHER` header ([graph.py](https://github.com/FalkorDB/falkordb-py/blob/main/falkordb/graph.py)). Parameterized queries share cached plans ([graph.query](https://docs.falkordb.com/commands/graph.query.md)); `GRAPH.RO_QUERY` errors on writes ([ro-query](https://docs.falkordb.com/commands/graph.ro-query.md)). Client-level MULTI/pipeline helper: not documented.

## 8. MCP server
- `@falkordb/mcpserver`: OpenCypher queries (read-only mode), create/manage nodes+rels, list and delete graphs, replica reads ([mcp index](https://docs.falkordb.com/genai-tools/mcpserver/index.md)). Env: `FALKORDB_HOST/PORT/USERNAME/PASSWORD`, `FALKORDB_DEFAULT_READONLY`, `MCP_TRANSPORT` (`stdio`|`http`), `MCP_PORT`, `MCP_API_KEY` (Bearer) ([config](https://docs.falkordb.com/genai-tools/mcpserver/configuration.md)). Tool names/schemas and per-tenant scoping: **not documented**. Graphiti MCP server also exists (experimental) ([agentic-memory](https://docs.falkordb.com/agentic-memory/index.md)).

## 9. Cypher gotchas
- openCypher v9 subset; Redis protocol via `GRAPH.QUERY`; no regex operator (use `STARTS WITH`/`ENDS WITH`/`CONTAINS`), no label expressions, no hex/octal; `DELETE` is really `DETACH DELETE` ([cypher-support](https://docs.falkordb.com/cypher/cypher-support.md)).
- No APOC: "APOC procedures may need alternatives" ([neo4j migration](https://docs.falkordb.com/operations/migration/neo4j-to-falkordb.md)). `id()` is internal, "not immutable" ([functions](https://docs.falkordb.com/cypher/functions.md)) → store own IDs (`randomUUID()` exists).
- [Known limitations](https://docs.falkordb.com/cypher/known-limitations.md): unreferenced relationship in a pattern is only existence-checked (`MATCH (a)-[e]->(b) RETURN COUNT(b)` returns 1 for two parallel edges; reference `e`); `LIMIT` doesn't stop eager ops (`UNWIND [1,2,3] AS value CREATE (a {property: value}) RETURN a LIMIT 1` creates 3 nodes); no index for `<>`; no aggregates in pattern comprehensions.
- Properties: maps and null **cannot** be stored; arrays only of scalars; entities not storable ([datatypes](https://docs.falkordb.com/datatypes.md)). Relationships are directed with a single type.

## 10. Memory sizing
- `GRAPH.MEMORY USAGE <graph-name> [SAMPLES <count>]` → MB: `total_graph_sz_mb`, `label_matrices_sz_mb`, `relation_matrices_sz_mb`, per-label/type attribute maps, `indices_sz_mb`; SAMPLES default 100, 1–10000 ([graph.memory](https://docs.falkordb.com/commands/graph.memory.md)). Docs' sample: 752 of 1086 MB were indices.
- `intern(str)` dedupes a string DB-wide, storable as property: `CREATE (:A {v:intern('VERY LONG STRING')})` ([functions](https://docs.falkordb.com/cypher/functions.md)). `QUERY_MEM_CAPACITY` caps per-query memory.

## Design implications for Track 02 (INFERENCE — not stated in docs)
1. **Graph per tenant/user** (`mem:{tenant}:{user}`) mirrors Graphiti/Mem0; enforce with ACL patterns (`~mem:acme:*`, `%R~` for peers) — engine-level isolation for "separate memory per tenant", not WHERE filters.
2. **Shared state/handoffs in a `shared:{team}` graph**; no cross-graph Cypher is documented, so joins across tenant and shared graphs are app-side.
3. **Writes serialize per graph**: batch with `UNWIND $rows` in one query; spread hot writers over graphs; benchmark cross-graph write overlap before quoting concurrency numbers.
4. **Avoid MULTI/EXEC by default** (blocks other graphs); write episode + entities + edges + handoff record as one atomic multi-clause query.
5. **Idempotent handoffs/claims**: range index → UNIQUE constraint on `task_id`/`handoff_id`, `MERGE ... ON CREATE SET`; wait for `OPERATIONAL`; own UUIDs.
6. **Bi-temporal facts** with `valid_from`/`valid_to`/`recorded_at` as epoch-ms integers (range-indexed) instead of the thinly documented temporal functions; supersede instead of delete for as-of queries; null can't be stored, so use a sentinel for "open-ended".
7. **Hybrid retrieval**: vector index (cosine) for candidates → var-length `*1..2` expansion → fulltext for exact names; vector search has no pre-filter, so the per-tenant graph is the cheap filter; over-fetch `k`, post-filter validity.
8. **Explainability**: return named paths + provenance edges (`(:Fact)-[:DERIVED_FROM]->(:Episode)-[:BY]->(:Agent)`) and scores; since `shortestPath` can't filter properties, use `algo.SPpaths` or var-length + `ORDER BY length(p) LIMIT n`.
9. **Memory types as labels**: `:Episode` (append-only turns, `[:NEXT]` chain), `:Entity`/`:Fact` (semantic), `:Procedure`/`:Step` (procedural), `:Agent`, `:Task`/`:Handoff`; map metadata → `toJSON()` strings.
10. **Reads scale**: use `ro_query` + async client with `BlockingConnectionPool`; set `TIMEOUT_DEFAULT/MAX`, `MAX_QUEUED_QUERIES`, `QUERY_MEM_CAPACITY` as agent backpressure; always parameterize.
11. **Sizing**: embeddings dominate (4 B × dim × n × ~1.2); poll `GRAPH.MEMORY USAGE` per tenant; `intern()` repeated strings; consider 384-dim for the demo; `GRAPH.COPY` for demo snapshots/what-if branches.
12. **Verify early**: cross-graph write parallelism, vector score direction, temporal property storage/`datetime()`, MCP tool list, and the flagged doc conflicts (MVCC vs serialized writers; UDF/temporal "unsupported").
