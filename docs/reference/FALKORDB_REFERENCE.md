# FalkorDB master reference (for this project)

Index to the full docs read (~290 pages, 2026-10-14) and to live checks on **FalkorDB 6.0.2** (Docker `falkordb/falkordb:latest`, Redis 8.10.2, module ver 60002).
Read this first; open the detailed part only when needed. Section numbers point to `parts/`.

| Part | Covers | Size |
|---|---|---|
| [A-cypher.md](parts/A-cypher.md) | Clauses, functions, procedures, indexes, constraints, data types, EXPLAIN/PROFILE, differences from Neo4j, a **33-pattern cookbook** (§8) | ~38k |
| [B-algorithms-udfs.md](parts/B-algorithms-udfs.md) | All `algo.*` procedures with signatures, "algorithm as an agent tool" ideas (§1.3), JavaScript UDFs, all 41 FLEX functions | ~25k |
| [C-engine-commands.md](parts/C-engine-commands.md) | Every `GRAPH.*` command, config params (with live values), design and concurrency, client libraries, Python cheat-sheet (§5) | ~26k |
| [D-operations-deploy.md](parts/D-operations-deploy.md) | Docker and Compose, persistence and backup, ACL, replication, cluster, K8s, Railway, FalkorDBLite, migration, Cloud tiers, **ops checklist** (§9) | ~37k |
| [E-ecosystem.md](parts/E-ecosystem.md) | Graphiti, Mem0, Cognee, MCP server, LangChain/LangGraph savers, LlamaIndex, Browser demo features, **build vs reuse** (§6) | ~31k |
| [F-graphrag-sdk.md](parts/F-graphrag-sdk.md) | GraphRAG SDK pipeline, the schema it creates, retrieval, the benchmark claim and its caveats, Track 02 fit (§8) | ~25k |
| [../research/capabilities.md](../research/capabilities.md) | Earlier condensed capability notes (a subset of A–C) | |

---

## 1. FalkorDB in one screen

- A **property graph database** that runs as a **Redis module**. Data lives in RAM as sparse adjacency matrices. You query it with **openCypher** (a subset, plus FalkorDB extensions) through `GRAPH.QUERY` and `GRAPH.RO_QUERY` over RESP. Bolt support is experimental.
- **Multi-graph:** each graph is a separate Redis key, and thousands can live in one instance. This is the native unit for tenant, user or agent isolation. `GRAPH.COPY` snapshots a graph; `GRAPH.DELETE` drops one.
- **Indexes:** range (equality, range, geo, arrays), full-text (RediSearch: prefix, fuzzy, TF-IDF) and vector (HNSW; cosine or euclidean; 1–4096 dimensions; on nodes **and relationships**). All three combine with traversal in one query.
- **Algorithms as procedures:** BFS, `algo.SPpaths` and `algo.SSpaths` (weighted, with cost limits), PageRank, betweenness, harmonic centrality, label propagation (communities), WCC, MSF, max flow.
- **Extensibility:** JavaScript UDFs (read-only) and the FLEX library (text similarity, dates, JSON, maps, collections).
- **Concurrency:** many readers run in parallel on snapshots. **Writes to one graph run one at a time**, and each query is atomic. There are no multi-query transactions; `MULTI/EXEC` blocks every graph. 6.0 adds MVCC in the Rust engine, but the concurrency page still describes the C engine [CONFLICT].
- **Security:** Redis ACL users with per-graph key patterns (`~tenantA:*`, `%R~shared:*`).
- **Persistence:** RDB/AOF through a Docker volume. Per-graph `DUMP`/`RESTORE` exists, but the documented round trip looks broken (see D §2.4).
- **Ecosystem:** official clients for Python (sync and asyncio), Node, Java, Rust, Go, PHP and C#. Also an MCP server, Graphiti, Mem0, Cognee, LangChain chat history, a LangGraph checkpointer, the GraphRAG SDK, and the Browser UI on :3000.
- **License:** SSPLv1. **Cloud Free tier:** 100 MB, no persistence, stopped after 1 idle day and deleted after 7.

## 2. Verified on 6.0.2: where reality differs from the docs (READ BEFORE CODING)

| # | Topic | What actually happens on 6.0.2 | Source |
|---|---|---|---|
| 1 | **Vector score** | For cosine, `score` is a **distance** (an identical vector scores ≈ 0). Nearest-first is `ORDER BY score ASC`. The docs show DESC. | A §4 |
| 2 | `datetime()`, `time()`, `vecf64()` | **Unknown functions.** Use `localdatetime()`, `date()`, `duration()`, `timestamp()` (epoch ms), or ISO strings. Date, localdatetime and duration values **can** be stored as properties. | A §2, B |
| 3 | Fuzzy full-text | `%term%1` returns no rows. `%term%` and `%%term%%` work. | A §4 |
| 4 | CCH index, `algo.AStar` | Documented, but **not present** on 6.0.2. | A §4, B §1 |
| 5 | Regex `=~`; mandatory MATCH after OPTIONAL MATCH | Both **work**, although the docs say they're unsupported. | A §7 |
| 6 | `SET n:Label` | Works, though undocumented. | A §1 |
| 7 | Maps or arrays containing null as properties | **Rejected.** Store maps as `toJSON()` strings. There's no null property: use a sentinel or remove the property. | A §5 |
| 8 | BFS | `nodes` excludes the start node. A null start returns empty instead of an error. | B §1 |
| 9 | `allShortestPaths` / `shortestPath` | Endpoints must be bound in an earlier MATCH, and no property filters are allowed in the pattern. Use `algo.SPpaths` for weighted paths or paths with constraints. | A, B |
| 10 | Docker image module args | `MAX_QUEUED_QUERIES 25`, `TIMEOUT 1000`, `RESULTSET_SIZE 10000`; THREAD_COUNT is the core count (12 here). **`RESULTSET_SIZE` silently truncates rows.** Override all of them with `FALKORDB_ARGS`. | C §2 |
| 11 | Other live config values | `EFFECTS_THRESHOLD` is 300 (docs say 0). `BOLT_PORT` is 65535 (docs say -1). `INDEX_WORKER_THREADS` and `EFFECTS_COMPRESSION` exist but aren't documented. | C §2 |
| 12 | **Runaway writes** | A cartesian-product `SET` with `TIMEOUT 50` was **not** aborted. The server died, Docker restarted it, and it reloaded an RDB 21 minutes old, losing recent graphs. → Treat the timeout as **unreliable for writes**. Bound every write with explicit `LIMIT`/`UNWIND` sizes, set `QUERY_MEM_CAPACITY`, and keep AOF on. | C (incident) |
| 13 | Possible hang | `WHERE size([(a)-[:R]->() \| 1]) = 0` hung for more than 60 s once (not confirmed). Use `WHERE NOT (a)-[:R]->()` instead. | A |
| 14 | Data directory | The docs disagree between `/data` and `/var/lib/falkordb/data`. Our container uses `/var/lib/falkordb/data`, and data survived a restart. | D §1 |
| 15 | Eviction | The docs' production example uses `allkeys-lru`, which **can evict whole graphs**. Use `noeviction`. | D §9 |
| 16 | Latency from Windows | Docker Desktop's port forward adds ~10 ms per round trip; it's ~0.3 ms inside the container. Benchmark inside the compose network. | CLAUDE.md |

Known Cypher limits from the docs:
- `LIMIT` doesn't stop eager writes.
- A relationship that isn't referenced elsewhere is only checked for existence, which skews counts.
- Indexes aren't used for `<>`.
- Aggregates aren't allowed in pattern comprehensions.
- There's no APOC.
- `id()` isn't stable, so store your own UUIDs (`randomUUID()`).

## 3. What FalkorDB is best at (ranked by docs, case studies and benchmarks)

1. **Agent memory and per-tenant context.** Fast multi-hop reads on every agent step, plus thousands of isolated graphs in one instance. Mem0, Graphiti, Cognee and the LangChain/LangGraph savers all use it this way (E §1).
2. **GraphRAG and knowledge graphs:** grounded answers with provenance (F). Vendor benchmark: 71.48 vs 55.39 for vector RAG, with heavy caveats (F §7).
3. **Deep traversals in security, fraud and threat intelligence:** for example Securin's 7-hop queries in under 400 ms.
4. **Recommendation and "why" explanations:** shared-neighbour paths returned with the result.
5. **Code and dependency graphs:** Code-Graph, and "what breaks if X goes down".

It's a poor fit for:
- heavy analytics over data larger than RAM;
- write-heavy single-graph hot spots, because writes are serialised per graph;
- multi-statement transactions;
- anything that needs Neo4j/APOC-specific features.

## 4. How to use it well (rules for this project)

1. **One graph per tenant/user (`t_<tenant>`), plus one shared graph per team or workspace.** Enforce it with ACL key patterns. Isolation is physical, not a `WHERE tenant=` filter.
2. **One logical write = one Cypher statement.** Combine MATCH and MERGE/CREATE with `WITH`, and use `UNWIND $rows` for batches. It's atomic, so no `MULTI/EXEC`. Spread hot writers across graphs.
3. **Do compare-and-set in a single query** (claims, leases, versioned updates): `MATCH (t:Task {id:$id}) WHERE t.claimed_by IS NULL OR t.lease_until < $now SET t.claimed_by=$agent, t.lease_until=$until RETURN t`. Writes to a graph run one at a time, so this can't race.
4. **Never overwrite facts; supersede them.** Use `valid_from`/`valid_to` stored as epoch ms with a range index, plus a `SUPERSEDES` edge. Read the "current" version by default and "as of T" when asked.
5. **Hybrid retrieval in one query:** vector top-k (`ORDER BY score ASC`) → graph expansion `*1..2` → validity filter → re-rank. The per-tenant graph is the pre-filter, because vector search has no property pre-filter.
6. **Explainability:** return named paths `p=` with `nodes(p)` and `relationships(p)`, or store provenance edges (`DERIVED_FROM`, `MENTIONED_IN`, `BASED_ON`) and return them with each answer.
7. **Reads use `ro_query`** with the async client and a `BlockingConnectionPool`, and always pass parameters (that enables plan caching and prevents injection). Guard any LLM-generated Cypher: read-only, timeout, LIMIT cap (the Board of SuperVision pattern).
8. **Constraints:** create the exact-match index first, then `GRAPH.CONSTRAINT CREATE ... UNIQUE`, and wait until it's `OPERATIONAL`.
9. **Use algorithms as tools.** PageRank gives memory salience, label propagation gives consolidation clusters, WCC finds orphaned knowledge, `algo.SPpaths` gives the cheapest explanation path (B §1.3).
10. **Ops:** pin the image tag; turn on AOF and `noeviction`; set a password or ACL; add a healthcheck; reseed on boot when the host doesn't persist data (free-vm.md §3).
11. **Testing:** a throwaway graph per test (`test_<uuid>`), deleted in teardown. Give parallel agents and suites their own container, never a shared dev server (incident #12).

## 5. Hosting decision (from research/free-vm.md + hosting.md)

| Rank | Option | Cost | Notes |
|---|---|---|---|
| 1 | **Render Free**: one Docker web service running FalkorDB and FastAPI in the same container, reseeded on boot, kept awake by a 5-minute UptimeRobot ping | $0, card apparently not needed | 512 MB RAM (FalkorDB idles at **88 MB** here). Sleeps after idle and has a cold start. Pinging is a ToS grey area. |
| 2 | AWS Free plan EC2 small (6 months), or Azure for Students (no card) | $0 | Always-on VM with disk; card rules vary |
| 3 | Oracle Always Free A1 (2 OCPU / 12 GB) | $0 | Rejects prepaid and virtual cards, which is a problem for Nepali USD cards. Capacity errors happen, and idle VMs get reclaimed. |
| Paid | Railway Hobby with FalkorDB's verified template | ~$5–10/mo | Lowest effort and reliable |

In every case, also submit complete local `docker compose` instructions and the demo video, which the rules accept.
