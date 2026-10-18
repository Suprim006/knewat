# Crucible report `20261018T080919Z`

- Started 2026-10-18T08:09:19Z, finished 2026-10-18T08:10:05Z (46.8 s). Layers: L1. **Full run.**
- Command: `crucible l1 --tests C7X --arms P,P-mcp,B0,B1,B2 --reps 1 --port 6386 --out C:/Change_folder_after_HDD/wt-rerun-current/knewat/demo_data/crucible/c7x_rerun`; commit `e2a7f82`.
- Ran **outside Docker** (host port forward adds latency); Windows-11-10.0.26200-SP0, Python 3.12.14, 12 CPUs; embedder `fastembed`.
- FalkorDB: Redis 8.10.2 at `127.0.0.1:6386`; effective module config: TIMEOUT_MAX=10000, TIMEOUT_DEFAULT=5000, MAX_QUEUED_QUERIES=500, RESULTSET_SIZE=100000, QUERY_MEM_CAPACITY=268435456, THREAD_COUNT=12, CACHE_SIZE=25, OMP_THREAD_COUNT=12.
- Seeds: [1000] (1 repetitions per test case).

## Arms

| Arm | Name | Represents | How it works | Tenant isolation |
|---|---|---|---|---|
| B0 | Files | How Claude Code (CLAUDE.md, auto-memory, agent-team task list) and Hermes (MEMORY.md, kanban, files) coordinate today | MEMORY.md + JSON task list under inter-process file locks (flock), atomic os.replace writes, append-only per-agent JSONL logs | one directory per tenant; the tenant name is validated before it becomes a path |
| B1 | SQLite | "Just use a relational database" | SQLite in WAL mode, BEGIN IMMEDIATE transactions, FTS5 recall, recursive CTEs for provenance | one SQLite database file per tenant; the tenant name is validated before it becomes a path |
| B2 | Vector | Retrieval-based memory (Mem0-style) | Same local bge-small embeddings as Knewat, stored in SQLite + numpy brute-force cosine. Hybrid: claims, decisions and handoffs use B1's SQLite tables because a vector store cannot do atomic claims | one SQLite database file (facts + vectors) per tenant; the tenant name is validated before it becomes a path |
| P | Knewat | Knewat: FalkorDB 6.0.2, one graph per tenant, deterministic Cypher | Engram/Relay/Lineage service layer called directly (memory, decision and handoff calls also write Steps and READ/WROTE edges) | one FalkorDB graph per tenant (knewat_t_<tenant>); the tenant is bound at construction, never taken from a tool argument, and validated against ^[a-z0-9_]{1,48}$ |

## Headline (generated from the numbers below)

- B0 matches Knewat (0 violations on both) on C7X.
- B1 matches Knewat (0 violations on both) on C7X.
- B2 matches Knewat (0 violations on both) on C7X.

## L1: correctness under concurrency

Violation counts are summed over every run (no averaging). `pass (n/n)` = all n runs had 0 violations.

| Test | Pass bar | P | B0 | B1 | B2 |
|---|---|---|---|---|---|
| **C7X** Paraphrase precision: 226 labelled pairs (negation, units, numbers, direction, ...) | 0 false merges in every category on P / P-mcp (baseline arms: reported, not gated) | pass (1/1) | pass (1/1) | pass (1/1) | pass (1/1) |

### C7X: Paraphrase precision: 226 labelled pairs (negation, units, numbers, direction, ...)

Metric: false merges (a different statement stored as a duplicate), per category; recall of true paraphrases. Bar: 0 false merges in every category on P / P-mcp (baseline arms: reported, not gated).

| Arm | Violations (all runs) |
|---|---|
| P | false_merges=0, categories_with_false_merges=0 |
| B0 | false_merges=0, categories_with_false_merges=0 |
| B1 | false_merges=0, categories_with_false_merges=0 |
| B2 | false_merges=0, categories_with_false_merges=0 |

## Limits and honesty notes

- Synthetic workloads and data only; one scenario family, a single-node database, scripted (non-LLM) workers.
- L1 workers are threads sharing one backend object (each with its own DB connection / file descriptors); only C2's victims are separate OS processes killed with SIGKILL. Concurrency is real but not deterministic: seeds fix the workload (priorities, DAG shape, values, query times), not the interleaving.
- Violations are reported as exact counts summed over all runs, never averaged.
- B0 and B1 are configured competently (locks / transactions). Where they match Knewat the table says so; Knewat's advantage is claimed only for what a graph does better: provenance, dependency traversal, time travel, contradictions at write time and cascading forget.
- L2 (provenance questions answered by an LLM for baselines) and L3 (end-to-end LLM agents) are out of scope of this run.
- L4 client latency is measured by Python threads in one process: at high worker counts it includes GIL queuing. Server-side run_time_ms is shown next to it for the Knewat arms.
- C5 probes each arm's tool API and, for Knewat, the MCP runtime's tenant binding (a header cannot rebind a connection). It does not probe the HTTP View API: that API is read-only, names the tenant in the URL and has no authentication in v1, so isolation there is by deployment. For B0/B1/B2 nothing stops a process with file access from opening another tenant's directory, and Knewat does not enforce per-graph access control inside FalkorDB either; a client with database access can query any graph.
- BASELINE §1 asks for one container per arm. B0/B1/B2 are embedded libraries with no server, so they run inside the crucible container; only FalkorDB (the Knewat arms) is a separate container.
- Numbers from `--quick` runs, or from outside Docker (Windows port forward adds ~10 ms per round trip), are not the published figures.

## Reproduce

```bash
docker compose -p knewat-bench --profile bench run --rm crucible all      # full L1 + L4 + ablation, inside the network
uv run crucible all --quick                                               # CI-sized, against a local FalkorDB
```
