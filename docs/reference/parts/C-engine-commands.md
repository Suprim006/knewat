# C — FalkorDB engine: GRAPH.* commands, configuration, design, clients

Scope: [docs.falkordb.com](https://docs.falkordb.com/index.md) engine pages (28 pages fetched, plus the falkordb-py README and the 6.0 blog post). Tags: **[LIVE]** = observed 2026-10-14 against `falkordb-dev` (`falkordb/falkordb:latest`, module `graph` ver 60002, Redis 8.10.2); **[CONFLICT]** = sources disagree; **[INFERENCE]** = my deduction, not documented. "Not documented" = absent from the pages read.

Orientation: FalkorDB is a Redis module; commands are `GRAPH.*`, most take the graph key first ([commands index](https://docs.falkordb.com/commands/index.md)). A graph is created implicitly on the first `GRAPH.QUERY` against a new key; there is no CREATE GRAPH ([commands index](https://docs.falkordb.com/commands/index.md)). Requires Redis >= 8.0.0 ([getting started](https://docs.falkordb.com/getting-started/index.md)).

## 1. Commands

Module command set **[LIVE]** (`COMMAND LIST FILTERBY MODULE graph`): DELETE, INFO, CONFIG, LIST, DEBUG, EXPLAIN, EFFECT, QUERY, COPY, RECORD, MEMORY, PROFILE, BULK, UDF, RESTORE, SLOWLOG, CONSTRAINT, RO_QUERY. `GRAPH.DEBUG`, `GRAPH.EFFECT`, `GRAPH.RECORD`, `GRAPH.RESTORE` are not documented in the pages read; `GRAPH.UDF` has no page in this set (only the `JS_HEAP_SIZE`/`JS_STACK_SIZE` configs mention JS UDFs); `GRAPH.BULK` has only a wire spec (below).

### GRAPH.QUERY — [page](https://docs.falkordb.com/commands/graph.query.md)
- Syntax: `GRAPH.QUERY graph_name "query" [timeout value] [--compact] [version value]`. Docs write the args as `Graph name, Query, [timeout], [--compact], [version]`.
- `timeout`: per-query ms ([config](https://docs.falkordb.com/getting-started/configuration.md)); the keyword form is `TIMEOUT <ms>` (e.g. `GRAPH.QUERY wikipedia "MATCH p=()-[*]->() RETURN p" TIMEOUT 500`). **[LIVE]** `TIMEOUT 5000` accepted.
- `--compact`: IDs instead of label/type/key strings ([client spec](https://docs.falkordb.com/design/client-spec.md)).
- `version`: graph schema version; server rejects with a `version mismatch` error if it differs, so clients can drop cached schema maps ([page](https://docs.falkordb.com/commands/graph.query.md)). **[CONFLICT]** **[LIVE]**: `version 999` on a graph at version 1 returned `ERR invalid graph version`; `version 1` (matching) succeeded.
- Parameters: `GRAPH.QUERY g "CYPHER name='Hawaii' MATCH (p)-[:born]->(:state {name:$name}) RETURN p"` — `CYPHER param=val [param=val ...] query` prefix ([page](https://docs.falkordb.com/commands/graph.query.md)). Plans (regular and parameterized) are cached, up to `CACHE_SIZE` unique queries, so parameterize ([page](https://docs.falkordb.com/commands/graph.query.md)). **[LIVE]** `CYPHER p=[1,2] RETURN $p` works (array param).
- Returns: [result set](https://docs.falkordb.com/design/result-structure.md) (header, rows, stats; see §4). Exceeding the timeout -> `(error) Query timed out` ([config](https://docs.falkordb.com/getting-started/configuration.md)).

### GRAPH.RO_QUERY — [page](https://docs.falkordb.com/commands/graph.ro-query.md)
- Same args as QUERY: `Graph name, Query, [timeout], [--compact], [version]`. Returns the result set, or an error if the query writes. Can be routed to read replicas in a cluster ([FAQ on page](https://docs.falkordb.com/commands/graph.ro-query.md)).
- **[LIVE]** write via RO: `graph.RO_QUERY is to be executed only on read-only queries`. RO on a non-existent key: `ERR Invalid graph operation on empty key`.

### GRAPH.DELETE — [page](https://docs.falkordb.com/commands/graph.delete.md)
- `GRAPH.DELETE graph_name` -> string (`OK`). Permanent, no undo. Takes a write lock: running queries finish, new ones are blocked until it completes ([page](https://docs.falkordb.com/commands/graph.delete.md)). Config `ASYNC_DELETE` (default yes) performs deletion in a background thread ([config](https://docs.falkordb.com/getting-started/configuration.md)).
- To remove individual entities use Cypher `MATCH ... DELETE x`; deleting a node removes its incident relationships ([page](https://docs.falkordb.com/commands/graph.delete.md)). **[LIVE]** deleting a missing key -> `ERR Invalid graph operation on empty key`.

### GRAPH.COPY — [page](https://docs.falkordb.com/commands/graph.copy.md)
- `GRAPH.COPY <src> <dest>` -> `OK`. Source stays fully accessible (reads and writes) during the copy; copy is a consistent snapshot as of command start; includes nodes, relationships, properties, indexes and constraints; errors if `dest` exists ([FAQ](https://docs.falkordb.com/commands/graph.copy.md)). Uses `TEMP_FOLDER` for dump files ([config](https://docs.falkordb.com/getting-started/configuration.md)).
- **[LIVE]** existing dest -> `destination key already exists`; index on the source appeared on the copy (`db.indexes()`). Constraint copying not verified.
- Docs sample output of `GRAPH.LIST` after copy includes a `telemetry{A}` key ([page](https://docs.falkordb.com/commands/graph.copy.md)).

### GRAPH.LIST — [page](https://docs.falkordb.com/commands/graph.list.md)
- `GRAPH.LIST`, no args -> array of graph key names in the currently selected Redis DB; empty array if none; internal `telemetry{...}` graphs may appear. (The page's sample numbers items from `2)` — typo.)

### GRAPH.EXPLAIN — [page](https://docs.falkordb.com/commands/graph.explain.md)
- `GRAPH.EXPLAIN graph query` -> string plan, query not run. Accepts `CYPHER param=val` prefix. Look for index scans vs `Node By Label Scan`. **[LIVE]** plan is an indented operator tree (`Project / Filter / Node By Label Scan | (m:Memory)`).

### GRAPH.PROFILE — [page](https://docs.falkordb.com/commands/graph.profile.md)
- `GRAPH.PROFILE graph query` -> plan lines with `Records produced` and `Execution time` per operator. **It executes the query, including writes**; it suppresses RETURN output and query stats. Accepts `TIMEOUT` ([config](https://docs.falkordb.com/getting-started/configuration.md)). **[LIVE]** a `SET` under PROFILE showed `Update` and `Commit` operators.

### GRAPH.SLOWLOG — [page](https://docs.falkordb.com/commands/graph.slowlog.md)
- `GRAPH.SLOWLOG graph_id` -> up to 10 slowest queries with latency >= 10 ms; each entry: Unix timestamp (double), command, query, ms (double), params or `(nil)`. `GRAPH.SLOWLOG graph_id RESET` clears (irreversible). Per-graph.

### GRAPH.CONFIG GET / SET — [GET](https://docs.falkordb.com/commands/graph.config-get.md), [SET](https://docs.falkordb.com/commands/graph.config-set.md)
- `GRAPH.CONFIG GET <name|*>` -> `[name, value]` (nested array for `*`). `GRAPH.CONFIG SET key1 val1 [key2 val2 ...]`; not persisted across restarts; non-runtime params return `(error) This configuration parameter cannot be set at run-time`; invalid value -> error, no partial changes. GET "typically requires administrative privileges" ([FAQ](https://docs.falkordb.com/commands/graph.config-get.md)) — **[LIVE]** it worked from an unauthenticated default session.

### GRAPH.CONSTRAINT CREATE / DROP — [CREATE](https://docs.falkordb.com/commands/graph.constraint-create.md), [DROP](https://docs.falkordb.com/commands/graph.constraint-drop.md)
```
GRAPH.CONSTRAINT CREATE key MANDATORY|UNIQUE NODE label | RELATIONSHIP reltype PROPERTIES propCount prop [prop...]
GRAPH.CONSTRAINT DROP   key MANDATORY|UNIQUE NODE label | RELATIONSHIP reltype PROPERTIES propCount prop [prop...]
```
- `propCount` 1–255. CREATE is **asynchronous**: replies `PENDING`; status `UNDER CONSTRUCTION` -> `OPERATIONAL`, or `FAILED` if existing data violates it (not enforced; fix data and recreate). Inspect with `CALL db.constraints()`. Sync failures: syntax error, already exists, missing supporting index.
- UNIQUE needs a pre-existing exact-match index on the same properties; enforced only when all constrained props are non-null; not enforced for array values; an index backing a constraint cannot be dropped. MANDATORY = property must exist.
- DROP is synchronous (`OK`); does not drop the supporting index; dropping a missing constraint errors.
- **[LIVE]** `CREATE INDEX FOR (m:Memory) ON (m.id)` then `CONSTRAINT CREATE g UNIQUE NODE Memory PROPERTIES 1 id` -> `PENDING`; `db.constraints()` columns `type,label,properties,entitytype,status` -> `OPERATIONAL`. Violation: `unique constraint violation on node of type Memory`; a multi-node CREATE containing one violation was fully rolled back. Missing drop: `Unable to drop constraint, no such constraint.`

### GRAPH.MEMORY USAGE — [page](https://docs.falkordb.com/commands/graph.memory.md)
- `GRAPH.MEMORY USAGE <graph-name> [SAMPLES <count>]` (default 100, clamped [1, 10000]; more samples = more accurate, slower). Returns flat key/value list (RESP2), **all in MB**: `total_graph_sz_mb`, `label_matrices_sz_mb`, `relation_matrices_sz_mb`, `amortized_node_block_sz_mb`, `amortized_node_attributes_by_label_sz_mb` (map label->MB), `amortized_unlabeled_nodes_attributes_sz_mb`, `amortized_edge_block_sz_mb`, `amortized_edge_attributes_by_type_sz_mb` (map), `indices_sz_mb`. **[LIVE]** tiny graph reports 0 for everything (integer MB granularity).

### GRAPH.INFO — [page](https://docs.falkordb.com/commands/graph.info.md)
- `GRAPH.INFO [Section ...]`, sections `RunningQueries`, `WaitingQueries`, `ObjectPool`; no section = all. Output headers `# Running queries`, `# Waiting queries`, `Object Pool` (fields `Unique Objects in Pool`, `Average References per Object`). Can be disabled via `CMD_INFO no`. Not documented: the per-query record fields inside the running/waiting arrays.

### GRAPH.BULK — [wire spec](https://docs.falkordb.com/design/bulk-spec.md)
- `GRAPH.BULK [graph name] ["BEGIN"] [node count] [edge count] ([binary blob] * N)`. Creates **new** graphs only (first call carries `BEGIN`; errors if key exists). Blobs <= 512 MB each, request <= 1 GB. Reply: `[N] nodes created, [M] edges created`. Types: `BI_NULL=0, BI_BOOL=1, BI_DOUBLE=2, BI_STRING=3, BI_LONG=4, BI_ARRAY=5`. Node IDs are implicit creation order from 0. The spec warns it may change; the user-facing tool is `falkordb-bulk-insert` ([home](https://docs.falkordb.com/index.md)).

### ACL — [page](https://docs.falkordb.com/commands/acl.md)
- Subcommands documented: `ACL HELP`, `ACL SETUSER <username> [rule...]`, `ACL GETUSER <username>`, `ACL DELUSER <username>`, `ACL LIST`, `ACL LOG [count]`; plus `ACL SAVE` (needs an ACL file) to persist.
- Rules: `on|off`, `nopass`, `password:<pw>` (example uses `>password123`), `~<pattern>` (graph-key pattern, full R/W), `%<R|W|RW>~<pattern>` (fine-grained), `+<command>`, `-<command>`.
- `%R~` = read data returned (RO_QUERY or read-only QUERY; *not* GRAPH.LIST metadata); `%W~` = update/delete; `%RW~` == `~`. A command that mutates and returns data needs both. Example: `+@all ~app1:* %R~app2:*` lets `GRAPH.COPY` read from `app2:*` into `app1:*`. Read-only user: `ACL SETUSER reader on >pass +GRAPH.RO_QUERY %R~*`.

## 2. Configuration parameters ([page](https://docs.falkordb.com/getting-started/configuration.md))

Set at load: `redis-server --loadmodule ./falkordb.so [OPT VAL]...`, `loadmodule` in redis.conf, `MODULE LOAD`, or Docker `-e FALKORDB_ARGS="THREAD_COUNT 4"` (Redis options go in `REDIS_ARGS`, e.g. `--requirepass`). Runtime: `GRAPH.CONFIG SET` (not persisted). Production image `falkordb/falkordb-server` omits the Browser.

| Name | Doc default | Load / Run | Meaning |
|---|---|---|---|
| THREAD_COUNT | hardware threads | load only | Thread pool size = max concurrent queries |
| CACHE_SIZE | 25 | load only | Max cached query plans (LRU eviction) |
| OMP_THREAD_COUNT | set by GraphBLAS | load only | OpenMP threads per query (intra-query parallelism) |
| NODE_CREATION_BUFFER | 16384 (min 128; rounded up to power of 2) | load only | Spare matrix capacity for new nodes |
| BOLT_PORT | -1 (disabled) | load only | Bolt protocol port |
| IMPORT_FOLDER | /var/lib/FalkorDB/import/ | load only | Absolute path CSV loads may read from |
| TEMP_FOLDER | /tmp | load only | Temp files (e.g. GRAPH.COPY dumps); must exist and be writable |
| ASYNC_DELETE | yes | both | `GRAPH.DELETE` in background thread |
| MAX_QUEUED_QUERIES | unlimited (UINT64_MAX) | both | Beyond this, new queries rejected with `Max pending queries exceeded` |
| TIMEOUT | off (0); **deprecated since v2.10** | both | Default max ms for *read* queries only; writes never time out |
| TIMEOUT_MAX | 0 (off) | both | Hard cap ms for read+write; per-query TIMEOUT may not exceed it; timed-out writes are rolled back |
| TIMEOUT_DEFAULT | = TIMEOUT_MAX (0) | both | Default ms for read+write; per-query `TIMEOUT` overrides |
| RESULTSET_SIZE | unlimited (negative) | both | Max records any query returns |
| QUERY_MEM_CAPACITY | 0 = unlimited | both | Max bytes per query; error `Query's mem consumption exceeded capacity` |
| VKEY_MAX_ENTITY_COUNT | 100000 | both | One virtual key per N entities when serializing/replicating |
| EFFECTS_THRESHOLD | see [CONFLICT] | both | Replicate as effect when avg modification time > threshold (µs) |
| CMD_INFO | yes | both | Enable `GRAPH.INFO` |
| MAX_INFO_QUERIES | 1000 (range 0–1000) | both | Past queries kept in telemetry stream |
| DELTA_MAX_PENDING_CHANGES | 10000 (0 resets to default) | both | Max uncommitted changes buffered in delta structure |
| DELAY_INDEXING | no | both | Build indexes after full RDB decode |
| JS_HEAP_SIZE | 268435456 (256 MB; min 1 MB) | both | QuickJS heap for JS UDFs |
| JS_STACK_SIZE | 1048576 (1 MB; min 1 MB) | both | QuickJS stack for JS UDFs |

**[LIVE] `GRAPH.CONFIG GET '*'` on this machine:** TIMEOUT 1000, TIMEOUT_DEFAULT 0, TIMEOUT_MAX 0, CACHE_SIZE 25, ASYNC_DELETE 1, OMP_THREAD_COUNT 12, THREAD_COUNT 12, INDEX_WORKER_THREADS 0, RESULTSET_SIZE 10000, VKEY_MAX_ENTITY_COUNT 100000, MAX_QUEUED_QUERIES 25, QUERY_MEM_CAPACITY 0, DELTA_MAX_PENDING_CHANGES 10000, NODE_CREATION_BUFFER 16384, CMD_INFO 1, MAX_INFO_QUERIES 1000, EFFECTS_COMPRESSION 0, EFFECTS_THRESHOLD 300, BOLT_PORT 65535, DELAY_INDEXING 0, IMPORT_FOLDER /var/lib/FalkorDB/import/, TEMP_FOLDER /tmp, JS_HEAP_SIZE 268435456, JS_STACK_SIZE 1048576. `MODULE LIST` shows load args `MAX_QUEUED_QUERIES 25 TIMEOUT 1000 RESULTSET_SIZE 10000` — those three are image-baked, not doc defaults. Booleans print as 1/0.
- `INDEX_WORKER_THREADS` and `EFFECTS_COMPRESSION` exist live but are **not documented** on the config page.
- **[LIVE] RESULTSET_SIZE=10000 truncates silently**: `UNWIND range(1,20000) AS x RETURN x` returned exactly 10000 rows, no error or flag (aggregates like `count(x)` still see all 20000).
- **[CONFLICT]** `EFFECTS_THRESHOLD`: doc says 0 µs since v4.20.2; live is 300. `BOLT_PORT`: doc default -1 (disabled); live 65535. The deprecated `TIMEOUT` is 1000 live, so read queries time out at 1 s by default here (**[LIVE]** `TIMEOUT 50` on a heavy read -> `(error) Query timed out`).
- **[CONFLICT] / safety note [LIVE]**: docs say `TIMEOUT_MAX`/per-query `TIMEOUT` cover writes. A write with `TIMEOUT 50` and a ~1.6-billion-row cartesian product was *not* aborted within 180 s, and the container then died and restarted (cause not confirmed; possibly memory). Never run unbounded write cartesian products; set `QUERY_MEM_CAPACITY`/`TIMEOUT_MAX` in a real deployment.

## 3. Design

- **Storage**: graphs are sparse adjacency matrices — one relation-agnostic adjacency matrix, one matrix per relationship type (cell holds the edge id), one diagonal matrix per label; new nodes extend matrices, deleting nodes removes row/column ([design](https://docs.falkordb.com/design/index.md)). Traversal = matrix multiplication; a pattern like `(N0)-[A]->(N1)-[B]->(N2)<-[A]-(N3)` compiles to `A * B * Transpose(A)`; associativity lets the planner order terms for sparsity and parallelize ([design](https://docs.falkordb.com/design/index.md)). GraphBLAS, CSC format "subject to change" ([design](https://docs.falkordb.com/design/index.md)).
- **Pipeline**: parse -> AST -> algebraic expressions -> filter trees -> optimized plan (filtered/conditional traverse, filter, project) -> execute -> result set ([design](https://docs.falkordb.com/design/index.md)). Data in RAM with on-disk persistence; tabular results; inserting a relationship is O(1) ([design](https://docs.falkordb.com/design/index.md)).
- **Memory**: `NODE_CREATION_BUFFER` pre-allocates matrix room (larger = faster writes, more RAM); `DELTA_MAX_PENDING_CHANGES` bounds buffered uncommitted changes ([config](https://docs.falkordb.com/getting-started/configuration.md)); `QUERY_MEM_CAPACITY` caps per-query bytes; `GRAPH.MEMORY USAGE` reports MB by component ([page](https://docs.falkordb.com/commands/graph.memory.md)).
- **Concurrency** ([page](https://docs.falkordb.com/design/concurrency.md)): per-graph reader-writer model. Many reads run in parallel (pool = `THREAD_COUNT`); **one write at a time per graph**, queued FIFO; readers see the snapshot from when the read began (snapshot-isolation-like) and never partial writes. Writes see latest committed state.
- **6.0 engine**: the Rust rewrite adds a columnar batch runtime and multi-version concurrency control "so reads never block and writes stay consistent"; same data files load as is; 6.0 has no supported upgrade path from 4.x (due in 6.2) ([6.0 blog](https://www.falkordb.com/blog/announcing-falkordb-6-0/)). Effects v3 replication format: replicas verify IDs/checksums rather than infer ([blog](https://www.falkordb.com/blog/announcing-falkordb-6-0/)).
- **[CONFLICT] doc staleness**: the concurrency page never mentions MVCC; the design/third-party pages describe the C engine (GraphBLAS, Lex/Lemon parser, libcypher-parser, C thread pool) ([design](https://docs.falkordb.com/design/index.md), [third-party](https://docs.falkordb.com/design/third-party.md)) while the 6.0 blog says the core is Rust. Treat GraphBLAS/OMP details as possibly legacy for 6.0 (live still exposes `OMP_THREAD_COUNT`).
- **Atomicity** ([page](https://docs.falkordb.com/design/concurrency.md)): every writing query (CREATE/SET/DELETE/MERGE, WITH/UNION compounds included) is all-or-nothing, including new labels/relationship types; after a `WITH`, filters see writes from earlier clauses. **No multi-query transactions**: use Redis `MULTI`/`EXEC`, which serializes across *all* graphs. **[LIVE]** a failing multi-node CREATE left no partial nodes.
- **Result-set format** ([result structure](https://docs.falkordb.com/design/result-structure.md), [client spec](https://docs.falkordb.com/design/client-spec.md)): queries with RETURN reply with 3 members `[header, rows, stats]`; without RETURN only `[stats]`. Scalars over RESP2: integer, NULL native; boolean as string `"true"/"false"`; double as string (15-digit). Node = `id, labels, properties`; relationship = `id, type, src_node, dest_node, properties`; arrays/paths are returned as their string form. Internal IDs are **not stable** (higher IDs may move into vacated lower ones after deletes). Stats lines: Labels added/removed, Nodes created/deleted, Properties set/removed, Relationships created/deleted, Indices created/deleted, `Query internal execution time: x milliseconds`. **[LIVE]** additional lines `Cached execution: 0|1` and `Graph version: N` (the latter is not in the client-spec list).
- **Compact format** (`--compact`): each value is `[ValueType, value]`; labels, types and property keys are integer IDs (start at 0, grow monotonically, never change), resolved client-side via `CALL db.labels()`, `db.relationshipTypes()`, `db.propertyKeys()`; header columns `[ColumnType, name]` (always scalar since v2.1.0) ([client spec](https://docs.falkordb.com/design/client-spec.md)). Node `[id,[labelIds],[[keyId,type,val]...]]`; edge `[id,typeId,src,dst,[props]]`. **[LIVE]** ValueType codes seen: 1 null, 2 string, 3 integer, 4 boolean, 5 double, 6 array, 7 edge, 8 node (docs only link the enum source, not list values). The spec's "Procedures documentation" link (`/commands/graph.query#procedures`) has no such section on that page.
- **Persistence/replication knobs**: `VKEY_MAX_ENTITY_COUNT` (virtual keys to limit Redis blocking), `EFFECTS_THRESHOLD` (replicate as effect vs original query) ([config](https://docs.falkordb.com/getting-started/configuration.md)).
- **License**: SSPLv1; internal use does not require open-sourcing, offering FalkorDB as a service does ([license](https://docs.falkordb.com/references/license.md)). Support: support@falkordb.com, Discord ([support](https://docs.falkordb.com/support.md)). Background paper: RedisGraph GraphBLAS (IPDPS 2019 GrAPL) ([references](https://docs.falkordb.com/references/index.md)).

## 4. Client libraries ([page](https://docs.falkordb.com/getting-started/clients.md))

| Language | Project / package | Notes |
|---|---|---|
| Python | falkordb-py (PyPI `falkordb`, MIT) | sync + asyncio (`falkordb.asyncio`) per [README](https://github.com/FalkorDB/falkordb-py); OGM: falkordb-py-orm |
| Node.js | falkordb-ts (npm `falkordb`, MIT) | async/await API per [examples](https://docs.falkordb.com/commands/graph.explain.md); no OGM listed |
| Java | jfalkordb (Maven `com.falkordb:jfalkordb`, BSD) | OGM: spring-data-falkordb (Apache-2.0) |
| Rust | falkordb-rs (crates `falkordb`, MIT) | `.execute().await?` builder in [QUERY examples](https://docs.falkordb.com/commands/graph.query.md); async/sync flavors not documented |
| Go | falkordb-go (BSD) | OGM: falkordb-go-orm |
| PHP | falkordb-php (MIT) | — |
| C# | NFalkorDB (NuGet, Apache-2.0) | — |

Official OGMs: falkordb-py-orm, falkordb-go-orm, spring-data-falkordb. Python/Node/Java are the "most sophisticated" reference clients ([client spec](https://docs.falkordb.com/design/client-spec.md)). Old RedisGraph clients (nredisstack, redisgraph-go, rueidis, etc.) may work but are unsupported. Any Redis client can issue raw `GRAPH.*` ([commands index](https://docs.falkordb.com/commands/index.md)). The FAQ says official clients support RESP and Bolt ([clients FAQ](https://docs.falkordb.com/getting-started/clients.md)); Bolt needs `BOLT_PORT` and is off by default per docs — verify before relying on it.

## 5. Python client cheat-sheet (falkordb-py)

Sources: [README](https://github.com/FalkorDB/falkordb-py), examples on the command pages.
```python
from falkordb import FalkorDB
db = FalkorDB(host="localhost", port=6379)            # password="..." for requirepass (getting-started)
g  = db.select_graph("social")
res = g.query("CREATE (n:Memory {id:$id}) RETURN n", {"id": "m1"})   # params dict = 2nd arg (query page)
rows = g.ro_query("MATCH (n) RETURN n LIMIT 10").result_set          # list of rows
g.explain(q); g.profile(q); g.slowlog(); g.slowlog_reset()
g2 = g.copy("social_copy"); g.delete()
db.list_graphs()          # list page; copy page uses db.list()  [CONFLICT: both appear in docs]
db.config_get("TIMEOUT_DEFAULT"); db.config_set("TIMEOUT_DEFAULT", 10000)
db.create_constraint("g", "UNIQUE", "NODE", "Person", ["first_name", "last_name"])
db.drop_constraint("g", "UNIQUE", "NODE", "Person", ["first_name", "last_name"])
```
- Install: `pip install FalkorDB`; optional `pip install "FalkorDB[hiredis]"` speeds parsing of big results (e.g. vector properties).
- Async:
```python
from falkordb.asyncio import FalkorDB
from redis.asyncio import BlockingConnectionPool
pool = BlockingConnectionPool(max_connections=16, timeout=None, decode_responses=True)
db = FalkorDB(connection_pool=pool); g = db.select_graph("social")
r = await g.query(...); results = await asyncio.gather(g.query(a), g.query(b)); await pool.aclose()
```
- Per-query `timeout` kwarg on `query()` and `version` handling: **not documented** in the README or command pages read (the server args exist; check [Pydoc](https://falkordb-py.readthedocs.io/en/latest/)). Connection pooling is delegated to redis-py pools as shown above. Concurrent writes from one pool still serialize server-side per graph.

## 6. Engine facts that shape a multi-agent memory design (all [INFERENCE] from the sources above)

1. Writes are serialized per graph (FIFO), reads parallel and snapshot-consistent -> one graph per agent/tenant avoids cross-agent write queueing; a shared graph is fine for read-heavy recall.
2. Single-query atomicity is the only transaction boundary; batch a "memory write" (node + edges + provenance) into one `GRAPH.QUERY` (use `UNWIND` with a params list) rather than several calls. Cross-graph atomicity needs `MULTI/EXEC`, which blocks all graphs.
3. Idempotent writes: use `MERGE` plus a UNIQUE constraint on a stable external id (needs an exact-match index first; creation is async -> poll `db.constraints()` until `OPERATIONAL`). Violations roll the whole query back (live-verified).
4. Internal node/edge IDs are not stable after deletes -> never use them as memory IDs; store your own `id` property.
5. `RESULTSET_SIZE` here is 10000 and truncates silently; page recall queries with `ORDER BY ... SKIP/LIMIT` and treat exactly-10000-row results as suspect.
6. Default read `TIMEOUT` is 1000 ms in this image; set `TIMEOUT_DEFAULT`/`TIMEOUT_MAX` (runtime, not persisted) and pass per-query timeouts for expensive traversals. Writes' timeout enforcement was not reliable in the live test -> bound write queries by construction.
7. `MAX_QUEUED_QUERIES 25` with 12 threads means a burst of >~37 simultaneous agent calls gets `Max pending queries exceeded`; clients need retry/backoff or a bounded pool.
8. Use `GRAPH.RO_QUERY` for all recall/reads (safety + replica routing) and `ACL` `%R~`/`%W~` patterns to give "reader" agents read-only access and restrict each agent to a key prefix (`~agentA:*`).
9. `GRAPH.COPY` (snapshot, source stays live, indexes included) = cheap checkpoint/branch of a memory graph for experiments or rollbacks; `GRAPH.DELETE` is permanent.
10. Parameterize every query (plan cache is only 25 entries; non-parameterized variants evict useful plans and invite injection).
11. Use `GRAPH.SLOWLOG`, `GRAPH.PROFILE` (beware: it runs writes) and `GRAPH.MEMORY USAGE` for observability; `GRAPH.INFO` shows queue depth.
12. Persistence: `CONFIG SET` changes are lost on restart, and **[LIVE]** a container restart reloaded an RDB ~21 min old and dropped graphs written since -> don't rely on in-container state without AOF/RDB persistence configured (see operations docs, other parts).
