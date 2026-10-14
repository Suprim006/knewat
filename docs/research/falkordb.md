# FalkorDB: what we're working with

Research notes for Graph Hacks Track 02 (Agent Memory and Coordination). Written before the event starts, as notes only.
Companion files (written by research subagents): `use-cases.md`, `hosting.md`, `capabilities.md`.

## 1. What it is

- FalkorDB is a property-graph database queried with openCypher. It describes itself as the first queryable property graph that stores the adjacency matrix as a sparse matrix and answers queries with linear algebra (GraphBLAS).[3]
- It began as a Redis module: data lives in RAM in custom structures, with on-disk persistence.[4] Clients talk to it over the Redis protocol (`GRAPH.QUERY` / `GRAPH.RO_QUERY`), not Bolt.[21]
- It is built by the original RedisGraph authors, who rebuilt it rather than patching the old codebase.[24]
- Version 6.0 (Sep 2026) is the first release on a new Rust engine. It runs 39% fewer CPU instructions than the C engine, closes 226 bugs, and existing Cypher queries keep working.[6] The rewrite added multi-version concurrency control, so reads never block and writes stay consistent.[6]
- Official clients exist for Python, Node.js, Java, Rust, Go, PHP and C#.[20]
- License: SSPLv1. Internal use is free. If you offer FalkorDB to others as part of a service, the code of that service must be open-sourced.[2] A hackathon entry with a public repo isn't affected.

## 2. The free options

| Option | What you get | Catch |
|---|---|---|
| **Open-source self-hosted** (Docker `falkordb/falkordb`, server on :6379 + Browser UI on :3000)[21] | Full engine, no size limits beyond your RAM, persistence through a Docker volume[22] | Needs Docker/Linux. On this machine Docker Desktop won't start, and the existing WSL distros are broken (checked 2026-10-14) |
| **FalkorDB Cloud Free** | 100 MB RAM (which is also the maximum graph size), multi-graph/multi-tenancy, graph access control, AWS or GCP, no credit card[1] | No TLS, persistence or backups.[1] **Stopped after 1 day unused and deleted after 7 days; the data can't be recovered.**[1] |
| **FalkorDBLite** (`pip install falkordblite`) | Runs the engine as a sub-process over a Unix socket. Same API as `falkordb-py`; switch to a server by changing one line[18] | Linux x64 / macOS arm64 only; Windows has to use WSL2[19] |
| Cloud Startup tier | From $73/month, 1 GB+, TLS, backups every 12h[1] | Paid |

**Takeaways for us (my inference):**
- **Development:** Cloud Free works right away with no setup, and 100 MB is plenty for a demo graph.
- **Judging:** the 1-day-idle stop and 7-day delete are a real risk.[1] Judges look at entries after Oct 18, and a deleted instance means a broken live demo. The live demo needs a self-hosted container with persistence, or a paid tier for the judging period. `hosting.md` compares the options.
- **Local:** we need a working WSL2 Ubuntu (or a repaired Docker) to run it ourselves or to use FalkorDBLite.

## 3. How good is it?

**Independent benchmark** (AIMultiple; one machine; 381K nodes / 804K edges; Neo4j vs FalkorDB vs Memgraph):[7]
- FalkorDB had the lowest latency on 11 of 12 queries and reached 6,693 QPS at 8 threads, 6.7× Neo4j.[7]
- Throughput stops rising after about 8 threads.[7] Neo4j won the heaviest aggregation query (131 ms vs 152 ms).[7]
- Cold start was 1.1 ms. Results were about the same with or without indexes.[7]
- Memory for the same graph: FalkorDB 496 MB, Memgraph 415 MB, Neo4j 2,668 MB heap.[7]
- Not tested: write-heavy workloads, persistence/recovery, full-text search, graph algorithms.[7]

**Vendor claims (treat as marketing):** "496× faster" latency than Neo4j, and PageRank 18.53 ms vs 417.31 ms on 820K nodes / 9.8M edges.[8]

**Practitioner reports:**
- A Mem0 contributor measured graph-query latency of about 0.2 ms vs under 50 ms on Neo4j in their production setup, deployment memory under 100 MB vs 8 GB+, and per-user graph isolation.[13]
- A local-first agent builder replaced a JSONL fact store with FalkorDB. Their graph is 85 MB and they use native HNSW vectors, `ABOUT` edges and `SUPERSEDES` chains for facts that change over time.[14]

**Concurrency model (this matters for Track 02's "high-concurrency" focus):**
- Reads run in parallel, each on a consistent snapshot.[5]
- Writes to one graph are queued and run one at a time, in order.[5]
- Each query is atomic, but there are no transactions spanning multiple queries; Redis `MULTI/EXEC` is the only option, and it locks out every graph while it runs.[5]
- So each memory write should be a single Cypher statement, and one graph per tenant spreads the write load (my inference).

**Weak spots:**
- Everything must fit in RAM.[4]
- It supports only part of openCypher, so APOC-style Neo4j habits don't carry over.[21]
- Some query behaviours differ from Neo4j, e.g. `LIMIT` doesn't limit eager writes, and patterns with an unused relationship can undercount.[23]
- The ecosystem is smaller than Neo4j's.[7]
- The 6.0 Rust engine is very new,[6] so we should pin the image version (my inference).

## 4. What people build with it

- **Agent memory frameworks:** Graphiti (Zep, Apache-2.0, ~31.7k stars) builds temporal "context graphs": facts with validity windows, linked back to the episodes they came from, with hybrid semantic + keyword + graph retrieval.[11] FalkorDB documents Graphiti, Graphiti MCP, Cognee and Mem0 as its supported agent-memory integrations.[10] Mem0 has a FalkorDB plugin with per-user graph isolation.[12]
- **Hackathon projects (4-hour event, Sep 2026):**[15]
  - An SF Board of Supervisors graph with 7,553 nodes. It answers "who dissents together" with a vote-edge pattern, and its read-only queries are guarded by a timeout, a write-keyword regex and a LIMIT cap.
  - A parking finder that combines a geospatial radius search with a join in a single query. Each graph is named by a hash of its source data, with a ready flag so the bot never reads a half-loaded graph.
  - A recommender that returns the shared nodes ("via") that justify each suggestion.
- **Production case studies:**
  - Securin runs 7-hop threat-intelligence traversals in under 350–400 ms for AI security agents, and uses short-lived FalkorDB Lite graphs, one per pentest engagement.[16]
  - Other case studies cover clinical data (AdaptX), ethical-AI data stores (Virtuous AI) and XR knowledge graphs.[17]
- **Built-in features for agent memory:**
  - Vector index (HNSW, cosine or Euclidean, 1–4096 dimensions).[9]
  - Full-text index.[25]
  - Graph algorithms usable as agent tools: BFS, shortest paths, PageRank, betweenness, community detection (CDLP), connected components (WCC).[25]
  - An MCP server.[25]

## 5. What this means for Track 02 (my inference)

1. Give each tenant/user its own graph (native multi-graph). This covers the "separate memory per tenant" requirement and spreads the write load.[5][13]
2. Agents read memory in parallel and each memory write is one atomic statement. That gives us a measurable concurrency demo.[5][7]
3. Model change over time explicitly (`SUPERSEDES` edges or validity windows) instead of overwriting facts. Graphiti and LocalClaw both show this works.[11][14]
4. Use vectors and traversal in one store, with no separate vector DB to keep in sync.[9][14]
5. Return the path or Cypher behind every answer; the hackathon brief asks to "show the path behind an answer".[15]
6. Decide whether to use Graphiti/Mem0 as a library or build our own memory layer. The rules require the main FalkorDB implementation to be new work, so I'm leaning towards our own schema and queries, with frameworks only as reference.

## Sources

[1] https://docs.falkordb.com/cloud/tiers/free — FalkorDB_Cloud_Free_Tier
[2] https://docs.falkordb.com/references/license.md — FalkorDB_License_(SSPLv1)
[3] https://github.com/FalkorDB/FalkorDB — FalkorDB_GitHub_README
[4] https://docs.falkordb.com/design/index.md — FalkorDB_Architecture_and_Design
[5] https://docs.falkordb.com/design/concurrency.md — FalkorDB_Atomicity_and_Concurrency
[6] https://www.falkordb.com/blog/announcing-falkordb-6-0 — Announcing_FalkorDB_6.0
[7] https://aimultiple.com/graph-databases — AIMultiple_Benchmark:_Neo4j_vs_FalkorDB_vs_Memgraph
[8] https://www.falkordb.com/falkordb-vs-neo4j — FalkorDB_vs_Neo4j_(vendor_page)
[9] https://docs.falkordb.com/cypher/indexing/vector-index.md — FalkorDB_Vector_Index
[10] https://docs.falkordb.com/agentic-memory/index.md — FalkorDB_Agentic_Memory
[11] https://github.com/getzep/graphiti — Graphiti_(Zep)_GitHub
[12] https://docs.falkordb.com/agentic-memory/mem0.md — Mem0_+_FalkorDB
[13] https://github.com/mem0ai/mem0/issues/4537 — Mem0_issue_4537:_FalkorDB_graph_store
[14] https://news.ycombinator.com/item?id=48383578 — HN:_Replaced_agent_flat_fact_store_with_graph_DB_(LocalClaw)
[15] https://www.falkordb.com/blog/how-builders-at-hack-for-humanity-used-falkordb-to-solve-real-community-problems — Hack_for_Humanity_FalkorDB_projects
[16] https://www.falkordb.com/case-studies/securin-falkordb-graph-case-study — Securin_case_study
[17] https://www.falkordb.com/category/case-studies — FalkorDB_case_studies
[18] https://www.falkordb.com/blog/falkordblite-embedded-python-graph-database — FalkorDBLite_(embedded_Python)
[19] https://github.com/FalkorDB/falkordblite-ts/blob/main/TROUBLESHOOTING.md — FalkorDBLite-ts_troubleshooting_(Windows)
[20] https://docs.falkordb.com/getting-started — FalkorDB_Getting_Started
[21] https://docs.falkordb.com/operations/docker — FalkorDB_Docker_and_Compose
[22] https://docs.falkordb.com/operations/durability/persistence.md — FalkorDB_Persistence_on_Docker
[23] https://docs.falkordb.com/cypher/known-limitations.md — FalkorDB_Known_Limitations
[24] https://news.ycombinator.com/item?id=44257880 — Show_HN:_FalkorDB_v4.10
[25] https://docs.falkordb.com/llms.txt — FalkorDB_docs_index_(llms.txt)
