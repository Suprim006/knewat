# Spike S2: local embeddings + FalkorDB 6.0.2 vector / fulltext / config / constraints

Status: done (throwaway spike, nothing committed). Image `falkordb/falkordb:6.0.2`
(digest `sha256:107455e862a8…`; Redis 8.10.2, graph module ver `60002`). Client: `falkordb` 1.8.0
(redis-py 8.1.0). Host: Windows 11, 12 logical CPUs, Docker Desktop (WSL2). All data synthetic.

## TL;DR (decisions)

| Topic | Decision |
|---|---|
| Model | `BAAI/bge-small-en-v1.5` via `fastembed` 0.9.0, 384-d. fastembed silently serves the **int8-quantised** ONNX (`Qdrant/bge-small-en-v1.5-onnx-Q`, 66.5 MB). Output vectors are unit-norm (‖v‖ = 1.0 ± 1e-7), so cosine == dot product. |
| Cache | `FASTEMBED_CACHE_PATH=<abs native path>` (or `TextEmbedding(cache_dir=...)`). Default is `<tempdir>/fastembed_cache`, which on Render is wiped on redeploy. Bake the model into the image / a disk. |
| Threads | **Always pass `threads=1` (or 2) in a CPU-limited container.** Default (all cores) collapses to 2.8 emb/s at `--cpus 0.5`; `threads=1` gives 30 emb/s. |
| Batch | `batch_size=16` for ingestion. Larger batches only raise RSS (+~50 MB per doubling past 32) and don't speed anything up. |
| Memory | ~265-285 MB RSS right after model load (Linux), ~300 MB working peak at batch 16-32. Fits Render's 512 MB; **batch ≥ 256 gets to ~475 MB, don't.** |
| Vector query | `CALL db.idx.vector.queryNodes(...)` score is a **cosine distance** (0 = identical); `ORDER BY score ASC` = nearest first. |
| Fulltext | Use DDL `CREATE FULLTEXT INDEX FOR (e:Entity) ON (e.name)`. The legacy `db.idx.fulltext.createNodeIndex` procedure is **broken on 6.0.2** (see below). |
| Config | The full `FALKORDB_ARGS` + `REDIS_ARGS` string from the task spec starts cleanly and every value is applied. |
| Constraints | Range index first, then `GRAPH.CONSTRAINT CREATE`; returns `PENDING`; poll `CALL db.constraints()` for `status`. |

## 1. fastembed measurements

Script: `bench2.py` in the scratch dir. 200 synthetic sentences of ~20 tokens, single process, ONNX Runtime CPU.

### 1.1 Windows 11 (native, Python 3.12.14, uv)

| Item | Value |
|---|---|
| Install (`uv add fastembed falkordb`) | ~14 s; `.venv` = **143 MB** (incl. falkordb, redis, numpy 2.5.4, onnxruntime 1.31.0, tokenizers 0.23.3, huggingface-hub 1.33.0, PIL) |
| Model download | 5 files, **~67 MB** (`model_optimized.onnx` 66,465,124 B + `tokenizer.json` 711 KB), 15-20 s on this link |
| Cache layout | `<cache>/models--Qdrant--bge-small-en-v1.5-onnx-Q/snapshots/<sha>/…` (HF hub layout) |
| `import fastembed` | 0.8-1.2 s (3.8 s on the very first run, cold disk cache) |
| Model load, cached | **0.3-0.6 s** |
| Model load, incl. download | ~20 s |
| Throughput, 200 sentences | batch 1: 55-114/s · batch 16: **116-182/s** · batch 32: 124-155/s · batch 64: 123-138/s · batch 256: 124-133/s (noisy; ±30 % run to run) |
| Single query embed | 6-9 ms |
| RSS (working set) | start 20 MB → after import 82 MB → after load 211 MB (peak 246) → after batch 16: 240 → batch 64: 323 → batch 256: **432** |
| Normalised? | Yes. `norm min/max = 0.9999999 / 1.0000001`, dtype `float32`, shape `(200, 384)`. |
| Sanity | cos("The billing service is owned by Priya's team", "Who owns billing?") = 0.76; vs "Bananas are yellow fruit" = 0.41. `query_embed()` returns the same vector as `embed()` (fastembed adds no BGE query instruction). |

Windows gotchas:
- `FASTEMBED_CACHE_PATH` must be a **native** path (`C:/Users/...`). From git-bash an `$PWD`-style `/c/Users/...` value is NOT converted and Python resolves it to `C:\c\Users\...` (it created a stray `C:\c\` tree, see "Issues").
- huggingface-hub warns "To support symlinks on Windows…"; harmless (it falls back to copies, no admin needed). Silence with `HF_HUB_DISABLE_SYMLINKS_WARNING=1`.

### 1.2 Linux container (`python:3.12-slim`, Python 3.12.15, `pip install fastembed`)

Same fastembed 0.9.0 / onnxruntime 1.31.0 / numpy 2.5.4. Container host is the same WSL2 VM (12 CPUs).

| Item | Unlimited | `--memory 512m --memory-swap 512m --cpus 0.5` |
|---|---|---|
| `site-packages` size | **221 MB** | same |
| Model download + cache (`du /tmp/fe`) | 65 MB, 15-17 s | same |
| `import fastembed` | 0.4-0.6 s | 1.4-1.6 s |
| Model load, cached | **0.3 s** | 5.8 s (CPU-throttled; 0.6 s with `threads=2`) |
| Throughput, default threads | b16: 109-146/s · b32: 111-127/s · b64: 95-116/s · b256: 81-138/s | **b16: 2.8/s · b64: 3.1-3.5/s** (thread oversubscription vs CFS quota) |
| Throughput, `threads=1` | n/a | **b16: 30.2/s · b64: 26.6/s** |
| Throughput, `threads=2` | n/a | b16: 21.5/s · b64: 19.2/s |
| Single query embed | 7-21 ms | `threads=1`: 58 ms · `threads=2`: 5.5 ms · default: 105-400 ms |
| RSS after import | 84 MB | 84 MB |
| **RSS after model load** | **265-283 MB** | 266-282 MB |
| RSS after warmup / b16 / b32 / b64 / b256 | 269-286 / 269-295 / 288-321 / 341-373 / 446-474 MB | 267-285 / 269-293 / 291-318 / 342-369 / (not run) MB |
| Normalised? | Yes (same norms) | Yes |

`docker stats` on the limited container read 354-467 MiB, but that figure includes page cache (model file + pip), while process RSS peaked at ~370 MB at batch 64.

**Render 512 MB budget:** model + runtime ≈ 270-285 MB, leaving ~225 MB for the web process, FastAPI/MCP code and request buffers. Plan on ≈ 300-320 MB steady state with batch 16-32. The FalkorDB server runs elsewhere (own container), so it is not part of this budget. Do not keep two `TextEmbedding` instances alive.

### 1.3 Recommendations

```python
from fastembed import TextEmbedding
# set FASTEMBED_CACHE_PATH in the environment (native absolute path) for deployments
model = TextEmbedding("BAAI/bge-small-en-v1.5", threads=1)   # 384-d, int8, unit-norm
vecs = [v.tolist() for v in model.embed(texts, batch_size=16)]  # list[list[float]] for vecf32($v)
```

- Load once at process start (lazy singleton), warm with one call.
- Dockerfile for Render: run `python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"` during build with `FASTEMBED_CACHE_PATH=/opt/fastembed` so nothing is downloaded at runtime.
- `.tolist()` before passing as a parameter (numpy arrays are not serialisable by the client).
- Pass `threads=1` on any CPU-limited host; raise to 2 only if you measure a gain. Embedding throughput is not the bottleneck at hackathon scale (30/s ≈ 1000 facts in 33 s on 0.5 CPU).

## 2. FalkorDB 6.0.2 vector behaviour (container `plexus-db-90`)

Index and insert (all verified):

```cypher
CREATE VECTOR INDEX FOR (f:Fact) ON (f.embedding)
  OPTIONS {dimension:384, similarityFunction:'cosine'}
-- returns indices_created=1, 0.64 ms. Defaults reported by CALL db.indexes():
--   M 16, efConstruction 200, efRuntime 10, status OPERATIONAL

UNWIND $rows AS r
MATCH (e:Entity {id:r.e})
CREATE (f:Fact {id:r.id, text:r.text, valid_to:r.valid_to, embedding:vecf32(r.v)})-[:ABOUT]->(e)
-- 200 facts + 200 ABOUT edges in ONE statement: 13 ms server time
```

`$rows[i].v` is a plain `list[float]` of length 384.

Query:

```cypher
CALL db.idx.vector.queryNodes('Fact','embedding',5,vecf32($q)) YIELD node, score
RETURN node.id AS id, score ORDER BY score ASC
```

Result for a query equal to a stored vector (f7):

```
f7 0.0 | f112 0.82796 | f9 0.8654 | f2 0.86714 | f177 0.88414     (0.62 ms)
```

- Score is a **distance**: identical vector → `0.0` (exact 0.0 against the index; `vec.cosineDistance(a,a)` gives 4.5e-08 float noise). Matches NumPy `1 - V @ q` to 5 decimals, same order. The procedure already returns nearest-first, but write `ORDER BY score ASC` explicitly.
- Similarity for the API, if needed: `similarity = 1 - score`.
- Combined seed → expand → temporal filter in ONE read query (k=20 seeds):

```cypher
CALL db.idx.vector.queryNodes('Fact','embedding',$k,vecf32($q)) YIELD node, score
MATCH (node)-[:ABOUT]->(e:Entity)
WHERE node.valid_to = 9999999999999
RETURN node.id AS id, e.name AS entity, score ORDER BY score ASC LIMIT 5
```

  Works. Server `run_time_ms` over 20 runs (200 facts): median **0.46 ms**, max 1.49 ms. Run via `ro_query`.
- **The `WHERE` is a post-filter on the k nearest, not a pre-filter.** Querying with the vector of an expired fact (`valid_to` ≠ sentinel) and `k=5` returned only 3 rows (the expired fact and one other dropped). Over-fetch: use `k = 3-5 × wanted` (or `k=50`) and `LIMIT` afterwards.
- Querying a label with no index (`'Nope'`) returns **empty, no error**. Check index existence at startup via `CALL db.indexes()`.
- Wrong query dimension: `Vector dimension mismatch, expected 384 but got 10`.
- Passing a raw list without `vecf32()` as the query: `Invalid arguments for procedure 'db.idx.vector.queryNodes'`.
- **Wrong-dimension insert is accepted silently** (`vecf32` of 10 floats on a `:Fact` was stored without error; whether it is excluded from the index was not checked). Validate length in the Python wrapper.
- Properties of type VecF32 can't go through `size()`/`IS NOT NULL` with size (`Type mismatch: expected List, String, or Null but was VecF32`); use `vec.cosineDistance(a,b)` / `vec.euclideanDistance(a,b)` if you need to compute distances in Cypher.

## 3. Fulltext (container `plexus-db-90`)

**Working form (DDL):**

```cypher
CREATE FULLTEXT INDEX FOR (e:Entity) ON (e.name)       -- indices_created=1
CALL db.idx.fulltext.queryNodes('Entity', $q) YIELD node, score
RETURN node.name, score ORDER BY score DESC
```

`CALL db.indexes()` then lists it: `['Entity', ['name'], {'name':['FULLTEXT']}, …, 'english', [], 'NODE', 'OPERATIONAL', …]`. Language is `english` by default (stemming is on).

**Legacy procedure form is broken here.** `CALL db.idx.fulltext.createNodeIndex(...)`:
- 2 arguments (`'Entity','name'`) → `Received 2 arguments to procedure 'db.idx.fulltext.createNodeIndex', expected at most 1`;
- 1 argument (`'Entity'` or `{label:'Entity'}`), via `GRAPH.QUERY` or `GRAPH.RO_QUERY` → `graph.RO_QUERY is to be executed only on read-only queries` (misleading; the proc is listed as `WRITE` in `dbms.procedures()` and creates nothing).
Don't use it.

Query forms against 10 `Service N beta` + 10 `Entity N alpha` nodes (query string → result count):

| Query | Hits | Note |
|---|---|---|
| `Serv*`, `serv*`, `Ser*` | 10 | prefix, case-insensitive |
| `Service` / `service` | 10 | exact term |
| `Servic` | 10 | matches `Service` through the English stemmer |
| `Entity 3` | 1 (`Entity 3 alpha`) | multi-term = AND |
| `Service 1*` | 5 | term AND prefix |
| `%servic%`, `%servce%`, `%Service%`, `%entty%` | 10 | `%term%` is **fuzzy (Levenshtein distance 1 per `%`)**, not substring: `%servce%` matches `service`, `%entty%` matches `entity` |
| `%serv%` | **0** | edit distance 2+ → no hit, so it is not a substring search |

Scores observed: 1.0 for prefix/fuzzy hits, 2.0 for an exact single term, 6.0 for multi-term matches; use `ORDER BY score DESC`.
`fulltext.queryNodes` takes a **string** with query syntax (`*`, `%`, etc.); sanitise user input in the wrapper (not tested).

## 4. Config parameter names (`plexus-db-91`)

Started with exactly the task's args; **container starts, all values applied**:

```bash
docker run -d --name plexus-db-91 -p 127.0.0.1:6391:6379 \
  -e FALKORDB_ARGS="TIMEOUT_MAX 10000 TIMEOUT_DEFAULT 5000 MAX_QUEUED_QUERIES 500 RESULTSET_SIZE 100000 QUERY_MEM_CAPACITY 268435456" \
  -e REDIS_ARGS="--appendonly yes --maxmemory-policy noeviction" \
  falkordb/falkordb:6.0.2
```

Evidence:
- `MODULE LIST` → `graph` ver 60002, args `['TIMEOUT_MAX','10000','TIMEOUT_DEFAULT','5000','MAX_QUEUED_QUERIES','500','RESULTSET_SIZE','100000','QUERY_MEM_CAPACITY','268435456']`.
- `CONFIG GET appendonly` → `yes` (default image: `no`); `CONFIG GET maxmemory-policy` → `noeviction` (also the default); `maxmemory` → `0`; `save` → `3600 1 300 100 60 10000` (default RDB snapshots).
- `GRAPH.CONFIG GET *` on db-91 (db-90 default in brackets), only differences: `MAX_QUEUED_QUERIES` 500 [25], `QUERY_MEM_CAPACITY` 268435456 [0], `RESULTSET_SIZE` 100000 [10000], `TIMEOUT_DEFAULT` 5000 [0], `TIMEOUT_MAX` 10000 [0], and **`TIMEOUT` becomes 0 [1000]** (observed: setting the new pair leaves `TIMEOUT` at 0, so the old one is not combined with them).

Full `GRAPH.CONFIG GET *` on db-91 (same keys on 6.0.2 default):
`ASYNC_DELETE 1, BOLT_PORT 65535, CACHE_SIZE 25, CMD_INFO 1, DELAY_INDEXING 0, DELTA_MAX_PENDING_CHANGES 10000, EFFECTS_COMPRESSION 0, EFFECTS_THRESHOLD 300, IMPORT_FOLDER /var/lib/FalkorDB/import/, INDEX_WORKER_THREADS 0, JS_HEAP_SIZE 268435456, JS_STACK_SIZE 1048576, MAX_INFO_QUERIES 1000, MAX_QUEUED_QUERIES 500, NODE_CREATION_BUFFER 16384, OMP_THREAD_COUNT 12, QUERY_MEM_CAPACITY 268435456, RESULTSET_SIZE 100000, TEMP_FOLDER /tmp, THREAD_COUNT 12, TIMEOUT 0, TIMEOUT_DEFAULT 5000, TIMEOUT_MAX 10000, VKEY_MAX_ENTITY_COUNT 100000`.

Image defaults on 6.0.2 with no env: module args `MAX_QUEUED_QUERIES 25 TIMEOUT 1000 RESULTSET_SIZE 10000` (so the stock server aborts reads at 1 s and truncates results at 10 000 rows).

Bisecting was not needed (nothing failed). Negative controls:
- `REDIS_ARGS="--appendonly yes --bogusdirective 1"` → container **exits 1** (`# >>> 'bogusdirective 1'`), so typos in REDIS_ARGS are loud.
- `FALKORDB_ARGS="BOGUS_NAME 5 TIMEOUT_MAX 10000"` → container stayed **Up** and logged `Module 'graph' loaded`, with no error line in the log. I did not check whether `TIMEOUT_MAX` still applied in that case. Treat typos in FALKORDB_ARGS as silent: always verify with `GRAPH.CONFIG GET <name>` in a startup check.
- `GRAPH.CONFIG SET` for runtime changes was not exercised.
- Persistence: with `appendonly yes` the container writes `appendonly.aof.1.base.rdb` / `.incr.aof` under its working dir; mount a volume on `/data` (or the image's data dir) to keep it.

## 5. Constraints (graph `g` on `plexus-db-90`)

Order matters: an exact-match (range) index must exist first.

```text
GRAPH.CONSTRAINT CREATE g UNIQUE NODE Task PROPERTIES 1 id
  -> (error) missing supporting exact-match index           # before the index
CREATE INDEX FOR (t:Task) ON (t.id)                          # range index, indices_created=1
GRAPH.CONSTRAINT CREATE g UNIQUE NODE Task PROPERTIES 1 id
  -> PENDING
CALL db.constraints()
  -> columns: type, label, properties, entitytype, status
  -> [['UNIQUE','Task',['id'],'NODE','OPERATIONAL']]         # was OPERATIONAL at first poll (empty graph)
```

Poll loop: `CALL db.constraints() YIELD type,label,properties,entitytype,status` until `status` is `OPERATIONAL` or `FAILED` (only these two plus the first-poll `OPERATIONAL` were observed; an in-progress status string was not captured because the graphs were tiny).

Behaviour once `OPERATIONAL` (error strings exact, as surfaced by redis-py `ResponseError`):

| Statement | Result |
|---|---|
| `CREATE (:Task {id:'t1'})` twice | `unique constraint violation on node of type Task` |
| `MATCH (t:Task {id:'t2'}) SET t.id='t1'` | `unique constraint violation on node of type Task` |
| `UNWIND ['t3','t3'] AS r CREATE (:Task {id:r})` | same error; **whole statement rolled back** (no `t3` stored) |
| `MERGE (t:Task {id:'t1'}) SET t.title='merged'` | works (matches the existing node) |
| `CREATE (:Task {title:'noid'})` | allowed: UNIQUE does not imply the property exists |

Other findings:
- `GRAPH.CONSTRAINT DROP g UNIQUE NODE Task PROPERTIES 1 id` → `OK`.
- `GRAPH.CONSTRAINT CREATE g MANDATORY NODE Task PROPERTIES 1 title` on existing violating data → `PENDING`, then `status = FAILED` in `db.constraints()`; same for a UNIQUE constraint over pre-existing duplicates (`:Dup {k:1}` ×2) → `FAILED`. So create constraints on an empty graph at startup, before ingesting, and check for `FAILED`.
- With the Python client use `db.connection.execute_command("GRAPH.CONSTRAINT","CREATE","g","UNIQUE","NODE","Task","PROPERTIES","1","id")` (the Cypher-level DDL form was not tested).

## 6. Suggested startup bootstrap (verified statements)

```cypher
CREATE VECTOR INDEX FOR (f:Fact) ON (f.embedding) OPTIONS {dimension:384, similarityFunction:'cosine'}
CREATE FULLTEXT INDEX FOR (e:Entity) ON (e.name)
CREATE INDEX FOR (t:Task) ON (t.id)
-- then GRAPH.CONSTRAINT CREATE <graph> UNIQUE NODE Task PROPERTIES 1 id   (after the matching range index)
```

Run each idempotently (catch the already-exists error, or check `CALL db.indexes()` / `CALL db.constraints()` first; the exact duplicate-index error text was not captured).

## Issues / caveats

- Throughput numbers are from a shared dev laptop and swing ±30 %; relative conclusions (threads=1 on limited CPU, small batches) are robust, absolute rates are not.
- The `--cpus 0.5` run reflects Render's smallest tier only approximately; I did not run on Render.
- Stray directory `C:\c\Users\ACER\AppData\Local\hermes\cache\scratch\plexus-s2\{fe_cache,.uvcache}` (~65 MB model + uv cache) was created by an MSYS-path mistake and left in place because the delete command was blocked pending approval. It is harmless scratch, safe to delete.
- Scratch dir with scripts/venv: `C:/Users/ACER/AppData/Local/hermes/cache/scratch/plexus-s2/` (`bench2.py`, `bench4.py`, `vec.py`, `ft2.py`, `con.py`, `misc.py`).
