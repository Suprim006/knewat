# Crucible report `20261014T204729Z`

- Started 2026-10-14T20:47:29Z, finished 2026-10-14T21:11:07Z (1417.4 s). Layers: L1, L4, ablation. **Full run.**
- Command: `crucible all`; commit `84763aa`.
- Ran inside Docker (same compose network as FalkorDB); Linux-5.15.146.1-microsoft-standard-WSL2-x86_64-with-glibc2.41, Python 3.12.15, 12 CPUs; embedder `fastembed`.
- FalkorDB: Redis 8.10.2 at `falkordb:6379`; effective module config: TIMEOUT_MAX=10000, TIMEOUT_DEFAULT=5000, MAX_QUEUED_QUERIES=500, RESULTSET_SIZE=100000, QUERY_MEM_CAPACITY=268435456, THREAD_COUNT=12, CACHE_SIZE=25, OMP_THREAD_COUNT=12.
- `FALKORDB_ARGS` = `TIMEOUT_MAX 10000 TIMEOUT_DEFAULT 5000 MAX_QUEUED_QUERIES 500 RESULTSET_SIZE 100000 QUERY_MEM_CAPACITY 268435456`
- Seeds: [1000, 1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009] (10 repetitions per test case).

## Arms

| Arm | Name | Represents | How it works | Tenant isolation |
|---|---|---|---|---|
| B0 | Files | How Claude Code (CLAUDE.md, auto-memory, agent-team task list) and Hermes (MEMORY.md, kanban, files) coordinate today | MEMORY.md + JSON task list under inter-process file locks (flock), atomic os.replace writes, append-only per-agent JSONL logs | one directory per tenant; the tenant name is validated before it becomes a path |
| B1 | SQLite | "Just use a relational database" | SQLite in WAL mode, BEGIN IMMEDIATE transactions, FTS5 recall, recursive CTEs for provenance | one SQLite database file per tenant; the tenant name is validated before it becomes a path |
| B2 | Vector | Retrieval-based memory (Mem0-style) | Same local bge-small embeddings as Knewat, stored in SQLite + numpy brute-force cosine. Hybrid: claims, decisions and handoffs use B1's SQLite tables because a vector store cannot do atomic claims | one SQLite database file (facts + vectors) per tenant; the tenant name is validated before it becomes a path |
| P | Knewat | Knewat: FalkorDB 6.0.2, one graph per tenant, deterministic Cypher | Engram/Relay/Lineage service layer called directly (memory, decision and handoff calls also write Steps and READ/WROTE edges) | one FalkorDB graph per tenant (knewat_t_<tenant>); the tenant is bound at construction, never taken from a tool argument, and validated against ^[a-z0-9_]{1,48}$ |
| P-mcp | Knewat (MCP path) | Knewat as the MCP server runs it | Same as P, but every call goes through Runtime._run: a Step and a ToolCall node are written per call (no JSON transport or network hop to the MCP server) | one FalkorDB graph per tenant (knewat_t_<tenant>); the tenant is bound at construction, never taken from a tool argument, and validated against ^[a-z0-9_]{1,48}$ |

## Headline (generated from the numbers below)

- B0 matches Knewat (0 violations on both) on C1, C2, C3, C4, C5, C6, C7, C8.
- B1 matches Knewat (0 violations on both) on C1, C2, C3, C4, C5, C6, C7, C8.
- B2 matches Knewat (0 violations on both) on C1, C2, C3, C4, C5, C6, C7, C8.

## L1: correctness under concurrency

Violation counts are summed over every run (no averaging). `pass (n/n)` = all n runs had 0 violations.

| Test | Pass bar | B0 | B1 | B2 | P |
|---|---|---|---|---|---|
| **C1** Claim race: N workers claim M tasks | 0 / 0 / 0 | pass (40/40) | pass (40/40) | pass (40/40) | pass (40/40) |
| **C2** Kill the claimer mid-task (SIGKILL) | all reclaimed within lease + 1 heartbeat; 0 orphans | pass (10/10) | pass (10/10) | pass (10/10) | pass (10/10) |
| **C3** Concurrent assertions on the same entity+predicate | 0 duplicates; 100% of contradictions flagged | pass (10/10) | pass (10/10) | pass (10/10) | pass (10/10) |
| **C4** Dependency DAG (depth 5, fan-out 3) | 0 | pass (10/10) | pass (10/10) | pass (10/10) | pass (10/10) |
| **C5** Tenant isolation probes | 0 | pass (10/10) | pass (10/10) | pass (10/10) | pass (10/10) |
| **C6** Supersede, then query 'as of T' | 0 | pass (10/10) | pass (10/10) | pass (10/10) | pass (10/10) |
| **C7** Paraphrase facts written concurrently by different agents | concurrent misses <= sequential misses (rate reported); 0 false merges | pass (10/10) | pass (10/10) | pass (10/10) | pass (10/10) |
| **C8** Forget by source, then probe recall | 0 | pass (10/10) | pass (10/10) | pass (10/10) | pass (10/10) |

### C1: Claim race: N workers claim M tasks

Metric: double claims / lost updates / tasks never claimed. Bar: 0 / 0 / 0.

Double claims / lost updates / never claimed (all runs), median ops/s:

| Arm | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|
| B0 | 0/0/0 @ 203.4 ops/s | 0/0/0 @ 211.8 ops/s | 0/0/0 @ 206 ops/s | 0/0/0 @ 206 ops/s |
| B1 | 0/0/0 @ 1986.7 ops/s | 0/0/0 @ 1465.5 ops/s | 0/0/0 @ 1087.5 ops/s | 0/0/0 @ 841.3 ops/s |
| B2 | 0/0/0 @ 1949.1 ops/s | 0/0/0 @ 1474.8 ops/s | 0/0/0 @ 1086.1 ops/s | 0/0/0 @ 771.3 ops/s |
| P | 0/0/0 @ 432.9 ops/s | 0/0/0 @ 536.4 ops/s | 0/0/0 @ 579 ops/s | 0/0/0 @ 397.4 ops/s |

### C2: Kill the claimer mid-task (SIGKILL)

Metric: time until the expired lease is reclaimed; orphaned tasks. Bar: all reclaimed within lease + 1 heartbeat; 0 orphans.

| Arm | Slowest reclaim after kill (ms) | Bar: lease + 1 heartbeat (ms) | Orphaned tasks (all runs) |
|---|---|---|---|
| B0 | 1504.7 | 2000 | 0 |
| B1 | 1470.6 | 2000 | 0 |
| B2 | 1269.9 | 2000 | 0 |
| P | 1517.4 | 2000 | 0 |

### C3: Concurrent assertions on the same entity+predicate

Metric: duplicate facts; contradictions not flagged; lost endorsements. Bar: 0 duplicates; 100% of contradictions flagged.

| Arm | Violations (all runs) |
|---|---|
| B0 | duplicate_facts=0, contradictions_missed=0, lost_endorsements=0, wrong_active_count=0 |
| B1 | duplicate_facts=0, contradictions_missed=0, lost_endorsements=0, wrong_active_count=0 |
| B2 | duplicate_facts=0, contradictions_missed=0, lost_endorsements=0, wrong_active_count=0 |
| P | duplicate_facts=0, contradictions_missed=0, lost_endorsements=0, wrong_active_count=0 |

### C4: Dependency DAG (depth 5, fan-out 3)

Metric: tasks started before their dependencies finished. Bar: 0.

| Arm | Violations (all runs) |
|---|---|
| B0 | started_before_deps_done=0, tasks_not_completed=0 |
| B1 | started_before_deps_done=0, tasks_not_completed=0 |
| B2 | started_before_deps_done=0, tasks_not_completed=0 |
| P | started_before_deps_done=0, tasks_not_completed=0 |

### C5: Tenant isolation probes

Metric: rows leaked across tenants (+ cross-tenant writes). Bar: 0.

| Arm | Violations (all runs) |
|---|---|
| B0 | rows_leaked=0, cross_tenant_writes=0, own_data_damaged=0 |
| B1 | rows_leaked=0, cross_tenant_writes=0, own_data_damaged=0 |
| B2 | rows_leaked=0, cross_tenant_writes=0, own_data_damaged=0 |
| P | rows_leaked=0, cross_tenant_writes=0, own_data_damaged=0 |

### C6: Supersede, then query 'as of T'

Metric: wrong-version answers. Bar: 0.

| Arm | Violations (all runs) |
|---|---|
| B0 | wrong_version_answers=0 |
| B1 | wrong_version_answers=0 |
| B2 | wrong_version_answers=0 |
| P | wrong_version_answers=0 |

### C7: Paraphrase facts written concurrently by different agents

Metric: duplicates stored beyond the sequential paraphrase-miss rate; false merges. Bar: concurrent misses <= sequential misses (rate reported); 0 false merges.

Paraphrase pairs stored as two facts instead of one (miss), sequential vs concurrent writers:

| Arm | Misses, sequential | Misses, concurrent | False merges of distinct facts |
|---|---|---|---|
| B0 | 120/120 (100%) | 120/120 (100%) | 0 |
| B1 | 120/120 (100%) | 120/120 (100%) | 0 |
| B2 | 30/120 (25%) | 30/120 (25%) | 0 |
| P | 30/120 (25%) | 30/120 (25%) | 0 |

Misses by paraphrase kind (missed/pairs, sequential):

| Arm | punctuation / case | light rewording | heavy rewording |
|---|---|---|---|
| B0 | 30/30 | 50/50 | 40/40 |
| B1 | 30/30 | 50/50 | 40/40 |
| B2 | 0/30 | 0/50 | 30/40 |
| P | 0/30 | 0/50 | 30/40 |

### C8: Forget by source, then probe recall

Metric: derived facts still returned. Bar: 0.

| Arm | Violations (all runs) |
|---|---|
| B0 | derived_facts_still_returned=0, not_marked_forgotten=0 |
| B1 | derived_facts_still_returned=0, not_marked_forgotten=0 |
| B2 | derived_facts_still_returned=0, not_marked_forgotten=0 |
| P | derived_facts_still_returned=0, not_marked_forgotten=0 |

## L4: performance and scale

- Workers are Python threads in one process; run inside the compose network (docker compose --profile bench run crucible).
- claim = claim_next_task, heartbeat, complete are timed separately; each cycle is claim -> heartbeat -> complete.
- B2's claims are B1's SQLite claims (hybrid), so only its recall is measured separately.
- P-mcp adds a Step and a ToolCall write to every call, as the MCP server does.
- B0/B1/B2 are embedded libraries running inside the crucible container (they have no server); the Knewat arms talk to the FalkorDB container over the compose network. B1/B2 use SQLite's built-in busy handler, which has no fairness queue, so tail latency under write contention is large; cross-process writers cannot be queued in-process.
- recall includes embedding the query with the local bge-small model (one model instance per process, calls serialised by its lock) for B2, P and P-mcp.

### Throughput (claim + heartbeat + complete operations per second)

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| B0 | 569.4 | 533.6 | 166.5 | 101.9 | 72.9 |
| B1 | 17168.6 | 3725.4 | 1655.7 | 1479.6 | 1455.6 |
| P | 668 | 1780.1 | 1028.2 | 679.1 | 373 |
| P-mcp | 122.5 | 258.2 | 227.8 | 172.6 | 152.6 |

### claim: client latency p50 / p95 / p99 (ms)

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| B0 | 1.587 / 3.292 / 4.031 | 18.296 / 25.27 / 30.097 | 266.548 / 425.552 / 524.69 | 930.522 / 1270.43 / 1294.1 | 2459.18 / 3747.62 / 3884.83 |
| B1 | 0.095 / 0.145 / 0.21 | 0.101 / 11.791 / 89.291 | 0.307 / 158.582 / 567.268 | 0.459 / 481.68 / 1687.86 | 0.82 / 1011.61 / 2177.87 |
| P | 1.755 / 2.49 / 2.823 | 5.494 / 11.02 / 15.913 | 49.712 / 83.484 / 139.563 | 155.638 / 278.497 / 355.983 | 570.856 / 1410.09 / 1863.45 |
| P-mcp | 8.355 / 10.356 / 11.643 | 37.204 / 44.523 / 48.247 | 239.264 / 280.918 / 287.23 | 620.807 / 821.036 / 827.713 | 1621.56 / 2241.98 / 2344.93 |

claim: server-side `run_time_ms` p50 / p95 / p99 (ms), summed over the call's queries:

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| P | 0.499 / 0.968 / 1.056 | 0.492 / 0.795 / 0.918 | 1.195 / 2.332 / 3.123 | 2.159 / 3.683 / 5.021 | 3.581 / 9.41 / 15.893 |
| P-mcp | 0.602 / 0.98 / 1.27 | 0.534 / 1.121 / 1.23 | 1.323 / 2.358 / 2.891 | 2.234 / 4.266 / 5.508 | 3.314 / 7.154 / 10.237 |

### heartbeat: client latency p50 / p95 / p99 (ms)

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| B0 | 1.365 / 2.486 / 3.547 | 17.245 / 25.074 / 28.983 | 283.067 / 390.956 / 435.801 | 951.388 / 1294.26 / 1561.61 | 2388.74 / 4120.42 / 4339.78 |
| B1 | 0.016 / 0.041 / 0.067 | 0.017 / 0.084 / 8.647 | 0.024 / 0.159 / 8.719 | 0.028 / 5.137 / 129.52 | 0.045 / 179.449 / 830.28 |
| P | 1.177 / 1.582 / 1.723 | 4.985 / 8.158 / 10.422 | 46.689 / 71.765 / 92.872 | 136.824 / 257.006 / 289.293 | 502.373 / 1020.66 / 1626.83 |
| P-mcp | 7.626 / 9.82 / 10.638 | 35.139 / 97.032 / 110.038 | 199.067 / 227.159 / 231.867 | 486.851 / 736.675 / 826.845 | 1022.75 / 1760.09 / 1782.02 |

heartbeat: server-side `run_time_ms` p50 / p95 / p99 (ms), summed over the call's queries:

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| P | 0.176 / 0.327 / 0.386 | 0.181 / 0.497 / 0.576 | 0.372 / 0.676 / 0.95 | 0.605 / 1.069 / 1.373 | 1.166 / 1.743 / 2.496 |
| P-mcp | 0.266 / 0.414 / 0.583 | 0.246 / 0.788 / 0.993 | 0.412 / 0.8 / 1.007 | 0.915 / 1.528 / 1.876 | 0.929 / 1.753 / 4.237 |

### complete: client latency p50 / p95 / p99 (ms)

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| B0 | 1.514 / 2.817 / 5.176 | 18.601 / 25.331 / 27.258 | 295.572 / 431.402 / 535.673 | 953.01 / 1152.45 / 1447.63 | 2453.61 / 4121.16 / 4279.86 |
| B1 | 0.034 / 0.075 / 0.152 | 0.035 / 0.102 / 0.201 | 0.04 / 0.239 / 9.675 | 0.042 / 0.337 / 33.97 | 0.052 / 4.302 / 179.582 |
| P | 1.391 / 1.831 / 2.005 | 4.89 / 8.357 / 10.527 | 37.383 / 58.418 / 71.454 | 106.43 / 172.244 / 231.284 | 309.747 / 393.496 / 401.886 |
| P-mcp | 7.941 / 10.025 / 11.692 | 35.599 / 42.431 / 44.496 | 208.479 / 234.197 / 238.972 | 571.861 / 793.22 / 876.758 | 1127.26 / 1475.53 / 1500.39 |

complete: server-side `run_time_ms` p50 / p95 / p99 (ms), summed over the call's queries:

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| P | 0.237 / 0.383 / 0.438 | 0.23 / 0.526 / 0.671 | 0.429 / 0.791 / 1.089 | 0.735 / 1.271 / 1.618 | 1.265 / 1.969 / 2.936 |
| P-mcp | 0.322 / 0.558 / 0.695 | 0.304 / 0.979 / 1.323 | 0.459 / 0.964 / 1.371 | 1.031 / 1.782 / 2.243 | 1.043 / 1.783 / 3.067 |

Errors across all claim points: 0.

### recall: client latency p50 / p95 / p99 (ms) and throughput

300 facts seeded; each recall embeds the query (arms with embeddings) and, for the Knewat/SQLite arms, records the recall.

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| B0 | 7.086 / 9.759 / 11.459 @ 133 | 81.087 / 100.361 / 106.55 @ 118.8 | 400.081 / 480.68 / 492.98 @ 125.7 | 686.2 / 881.603 / 950.043 @ 137.8 | 1120.59 / 4184.58 / 4530.23 @ 129.7 |
| B1 | 1.675 / 2.323 / 3.224 @ 525.1 | 13.502 / 54.385 / 57.705 @ 487.3 | 83.51 / 293.969 / 346.386 @ 431.2 | 190.418 / 395.25 / 620.579 @ 430.7 | 483.847 / 1060.35 / 1404.1 @ 351.6 |
| B2 | 14.285 / 21.238 / 24.895 @ 66.3 | 186.331 / 267.869 / 292.484 @ 51.2 | 812.618 / 1938.76 / 1970.24 @ 44.3 | 1550.96 / 1966.87 / 2056.76 @ 62.8 | 3004.84 / 3957 / 4054.86 @ 62.4 |
| P | 26.267 / 37.476 / 41.182 @ 36 | 192.8 / 276.44 / 299.914 @ 51 | 749.176 / 1307.73 / 1413.47 @ 60.1 | 1855.83 / 2651.01 / 2792.45 @ 50.6 | 8146.99 / 11567.7 / 16069 @ 23.7 |
| P-mcp | 69.785 / 125.137 / 182.42 @ 12.9 | 597.62 / 1082.52 / 1103.34 @ 16 | 2626.03 / 4727.34 / 5047.12 @ 17.2 | 3341.38 / 4195.37 / 4477.64 @ 28.1 | 7061.79 / 8619.65 / 9262.73 @ 28.1 |

recall: server-side `run_time_ms` p50 / p95 / p99 (ms):

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| P | 6.536 / 7.88 / 8.224 | 8.096 / 16.778 / 18.328 | 8.225 / 16.993 / 25.241 | 8.295 / 16.668 / 23.585 | 9.644 / 23.201 / 35.78 |
| P-mcp | 8.827 / 14.951 / 22.159 | 12.744 / 29.753 / 37.914 | 12.581 / 31.024 / 36.747 | 9.985 / 22.774 / 29.512 | 9.763 / 20.787 / 29.372 |

### Embedder alone (no database): the ceiling for recall

Recall embeds the query with one shared bge-small instance whose calls are serialised. With W closed-loop workers, latency ~ W / throughput (Little's law), so once that instance saturates, p50 grows linearly with W whatever the store behind it does. Compare with the server-side `run_time_ms` above (about 10 ms).

| Workers | Embeds/s | p50 / p95 / p99 (ms) |
|---|---|---|
| 1 | 67.4 | 13.691 / 19.777 / 19.777 |
| 10 | 45 | 189.626 / 405.1 / 753.717 |
| 200 | 46.9 | 3340.72 / 7234.74 / 8988.23 |

At 200 workers recall runs at 23.7 ops/s (P) and 28.1 ops/s (P-mcp), against 46.9 embeds/s for the embedder alone at 200 workers. The server-side time stays at 9.644 ms (P) / 9.763 ms (P-mcp) p50, while client p50 is 8.1 s / 7.1 s: that is the closed-loop queue (200 workers / throughput), not database time. P-mcp's extra Step and ToolCall writes do not make it slower than P at this worker count, so there the audit writes are not the limiter (at low worker counts, where the embedder is not saturated, P-mcp is slower: see the table above).

### One graph vs N tenant graphs (write ceiling), 50 workers, claim + complete

| Arm | 1 tenant | 4 tenants | 16 tenants |
|---|---|---|---|
| B1 | 1103.4 ops/s, claim p99 666.588 ms | 1480 ops/s, claim p99 561.956 ms | 500.4 ops/s, claim p99 1223.186 ms |
| P | 678.3 ops/s, claim p99 185.752 ms | 1024.8 ops/s, claim p99 163.256 ms | 1173.7 ops/s, claim p99 166.927 ms |

## Ablation (D-001): cut the edges, see what breaks

Deleted relationship types: DEPENDS_ON, BASED_ON, DERIVED_FROM, READ (edges removed: {'DEPENDS_ON': 3, 'BASED_ON': 2, 'DERIVED_FROM': 5, 'READ': 8}). 7/7 capabilities that need those edges break; 5/5 control capabilities (no stripped edge involved) are unaffected.

| Capability | Needs edge | Intact | Ablated | Ablated detail |
|---|---|---|---|---|
| as-of time travel (C6) | (none: control) | pass | pass | as_of(version, before v2) = 'v1' (expected 'v1') |
| recall | (none: control) | pass | pass | recall finds the owner fact |
| contradiction flagged at write time (C3) | (none: control) | pass | pass | conflicting owner flagged: 1 contradiction(s) |
| supersession history | (none: control) | pass | pass | v1 is superseded by v2 (SUPERSEDES edge kept) |
| exclusive claims (C1) | (none: control) | pass | pass | two agents never get the same task |
| dependency-aware claims (C4) | DEPENDS_ON | pass | **FAIL** | claimable without completing anything: ['T1', 'T2', 'T3', 'T4', 'T5'] (expected ['T1', 'T5']) |
| blocked_by_failure | DEPENDS_ON | pass | **FAIL** | blocked_by_failure(T1) = [] (expected ['T2', 'T3', 'T4']) |
| why(decision): evidence + who asserted it | BASED_ON | pass | **FAIL** | why(decision) lists 0 fact(s) with their asserting agents (expected 2) |
| why(fact): source lineage | DERIVED_FROM | pass | **FAIL** | why(derived fact) reaches source(s) 0 (expected the spec source) |
| knew_at(agent, step) | READ | pass | **FAIL** | knew_at(builder, step) lists 0 fact(s) read (expected to include v1) |
| who_knew(fact) | READ | pass | **FAIL** | who_knew(v1) = [] (expected ['builder']) |
| forget by source, cascading (C8) | DERIVED_FROM | pass | **FAIL** | forget_source forgot 0 fact(s) (expected 3: two from the source + one derived from them) |

L1 re-run with the edges stripped as soon as they are written (`P-abl`) next to the intact Knewat arm:

| Arm | Test | Result |
|---|---|---|
| P | C4 | pass (3/3) |
| P | C8 | pass (3/3) |
| P-abl | C4 | **FAIL** 0/3 (started_before_deps_done=181) |
| P-abl | C8 | **FAIL** 0/3 (derived_facts_still_returned=60, not_marked_forgotten=60) |

## Re-runs (cells replaced after the main run)

- 2026-10-14T21:36:03Z, commit `4ac62a8`: Harness bug: the FalkorDB python client's connection pool holds 100 connections, so 200 worker threads sharing one client got MaxConnectionsError (100 failed calls per run; the old report showed one deduplicated message). The harness now uses a 512-connection pool. Affected cells re-executed unchanged otherwise; the embedder probe is new.
- Replaced cells: L1:P:C1, L4:claim:P:200, L4:claim:P-mcp:200, L4:embedder. The original results are kept in `results.json` under `run.reruns[*].superseded`.
  - was L1:P:C1: 30/40 runs passed, violations {'double_claims': 0, 'lost_updates': 0, 'never_claimed': 0, 'errors': 10}
  - was L4:claim:P:200: 100 errors (MaxConnectionsError: Too many connections), 2400 ops completed
  - was L4:claim:P-mcp:200: 100 errors (MaxConnectionsError: Too many connections), 2402 ops completed
  - was L4:embedder: no earlier result

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
