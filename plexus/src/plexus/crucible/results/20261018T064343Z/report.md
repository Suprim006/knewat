# Crucible report `20261018T064343Z`

- Started 2026-10-18T06:43:43Z, finished 2026-10-18T07:41:33Z (3469.5 s). Layers: L1, L4, ablation. **Full run.**
- Command: `crucible all`; commit `fb8e02f`.
- Ran inside Docker (same compose network as FalkorDB); Linux-5.15.146.1-microsoft-standard-WSL2-x86_64-with-glibc2.41, Python 3.12.15, 12 CPUs; embedder `fastembed`.
- FalkorDB: Redis 8.10.2 at `127.0.0.1:6379`; effective module config: TIMEOUT_MAX=10000, TIMEOUT_DEFAULT=5000, MAX_QUEUED_QUERIES=500, RESULTSET_SIZE=100000, QUERY_MEM_CAPACITY=268435456, THREAD_COUNT=12, CACHE_SIZE=25, OMP_THREAD_COUNT=12.
- `FALKORDB_ARGS` = `TIMEOUT_MAX 10000 TIMEOUT_DEFAULT 5000 MAX_QUEUED_QUERIES 500 RESULTSET_SIZE 100000 QUERY_MEM_CAPACITY 268435456`
- Seeds: [1000, 1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009] (10 repetitions per test case).

## Arms

| Arm | Name | Represents | How it works | Tenant isolation |
|---|---|---|---|---|
| B0 | Files | How Claude Code (CLAUDE.md, auto-memory, agent-team task list) and Hermes (MEMORY.md, kanban, files) coordinate today | MEMORY.md + JSON task list under inter-process file locks (flock), atomic os.replace writes, append-only per-agent JSONL logs | one directory per tenant; the tenant name is validated before it becomes a path |
| B1 | SQLite | "Just use a relational database" | SQLite in WAL mode, BEGIN IMMEDIATE transactions, FTS5 recall, recursive CTEs for provenance | one SQLite database file per tenant; the tenant name is validated before it becomes a path |
| B2 | Vector | Retrieval-based memory (Mem0-style) | Same local bge-small embeddings as Plexus, stored in SQLite + numpy brute-force cosine. Hybrid: claims, decisions and handoffs use B1's SQLite tables because a vector store cannot do atomic claims | one SQLite database file (facts + vectors) per tenant; the tenant name is validated before it becomes a path |
| P | Plexus | Plexus: FalkorDB 6.0.2, one graph per tenant, deterministic Cypher | Engram/Relay/Lineage service layer called directly (memory, decision and handoff calls also write Steps and READ/WROTE edges) | one FalkorDB graph per tenant (plexus_t_<tenant>); the tenant is bound at construction, never taken from a tool argument, and validated against ^[a-z0-9_]{1,48}$ |
| P-mcp | Plexus (MCP path) | Plexus as the MCP server runs it | Same as P, but every call goes through Runtime._run: a Step and a ToolCall node are written per call (no JSON transport or network hop to the MCP server) | one FalkorDB graph per tenant (plexus_t_<tenant>); the tenant is bound at construction, never taken from a tool argument, and validated against ^[a-z0-9_]{1,48}$ |

## Headline (generated from the numbers below)

- B0 matches Plexus (0 violations on both) on C1, C2, C3, C4, C5, C6, C7, C8.
- B1 matches Plexus (0 violations on both) on C1, C2, C3, C4, C5, C6, C7, C8.
- B2 matches Plexus (0 violations on both) on C1, C2, C3, C4, C5, C6, C7, C8.

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
| B0 | 0/0/0 @ 197 ops/s | 0/0/0 @ 199.8 ops/s | 0/0/0 @ 185.5 ops/s | 0/0/0 @ 163.2 ops/s |
| B1 | 0/0/0 @ 1789 ops/s | 0/0/0 @ 1295.4 ops/s | 0/0/0 @ 939.9 ops/s | 0/0/0 @ 580.1 ops/s |
| B2 | 0/0/0 @ 1592.1 ops/s | 0/0/0 @ 1265.7 ops/s | 0/0/0 @ 704.9 ops/s | 0/0/0 @ 641.5 ops/s |
| P | 0/0/0 @ 403.2 ops/s | 0/0/0 @ 410.1 ops/s | 0/0/0 @ 369.8 ops/s | 0/0/0 @ 204.5 ops/s |

### C2: Kill the claimer mid-task (SIGKILL)

Metric: time until the expired lease is reclaimed; orphaned tasks. Bar: all reclaimed within lease + 1 heartbeat; 0 orphans.

| Arm | Slowest reclaim after kill (ms) | Bar: lease + 1 heartbeat (ms) | Orphaned tasks (all runs) |
|---|---|---|---|
| B0 | 1482.7 | 2000 | 0 |
| B1 | 1511.2 | 2000 | 0 |
| B2 | 1473 | 2000 | 0 |
| P | 1473.2 | 2000 | 0 |

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
| P | 60/120 (50%) | 60/120 (50%) | 0 |

Misses by paraphrase kind (missed/pairs, sequential):

| Arm | punctuation / case | light rewording | heavy rewording |
|---|---|---|---|
| B0 | 30/30 | 50/50 | 40/40 |
| B1 | 30/30 | 50/50 | 40/40 |
| B2 | 0/30 | 0/50 | 30/40 |
| P | 0/30 | 30/50 | 30/40 |

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
- B0/B1/B2 are embedded libraries running inside the crucible container (they have no server); the Plexus arms talk to the FalkorDB container over the compose network. B1/B2 use SQLite's built-in busy handler, which has no fairness queue, so tail latency under write contention is large; cross-process writers cannot be queued in-process.
- recall includes embedding the query with the local bge-small model (one model instance per process, calls serialised by its lock) for B2, P and P-mcp.

### Throughput (claim + heartbeat + complete operations per second)

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| B0 | 591.9 | 483.6 | 119.4 | 73.8 | 35.5 |
| B1 | 8535.8 | 4650.4 | 1796.2 | 1534.8 | 746.1 |
| P | 269.1 | 498.4 | 453.7 | 313.9 | 323.2 |
| P-mcp | 120.9 | 259.6 | 121.7 | 102.3 | 121.6 |

### claim: client latency p50 / p95 / p99 (ms)

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| B0 | 1.621 / 3.472 / 4.013 | 19.248 / 35.407 / 39.601 | 387.831 / 747.148 / 1292.46 | 1084.35 / 2151.96 / 2229.23 | 4897.64 / 10913.1 / 11117.7 |
| B1 | 0.12 / 0.808 / 1.134 | 0.11 / 8.827 / 41.855 | 0.303 / 142.722 / 573.37 | 0.49 / 486.941 / 1683.54 | 0.796 / 1427.84 / 4759.97 |
| P | 4.911 / 6.15 / 7.537 | 23.19 / 34.824 / 40.112 | 114.819 / 254.634 / 297.635 | 368.887 / 700.49 / 848.697 | 720.854 / 1218.52 / 1461.88 |
| P-mcp | 8.196 / 10.351 / 12.775 | 36.345 / 48.274 / 53.759 | 314.216 / 672.465 / 743.712 | 1029.63 / 1608.3 / 1977.87 | 1679.63 / 3585.14 / 3716.02 |

claim: server-side `run_time_ms` p50 / p95 / p99 (ms), summed over the call's queries:

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| P | 0.682 / 1.105 / 1.531 | 0.986 / 1.901 / 2.741 | 1.551 / 3.819 / 6.224 | 3.256 / 7.492 / 9.557 | 3.327 / 6.925 / 9.976 |
| P-mcp | 0.683 / 1.164 / 1.38 | 0.747 / 1.457 / 1.812 | 2.067 / 7.273 / 12.023 | 4.473 / 13.261 / 15.166 | 4.107 / 14.819 / 17.219 |

### heartbeat: client latency p50 / p95 / p99 (ms)

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| B0 | 1.332 / 2.458 / 3.478 | 18.909 / 34.878 / 40.938 | 375.936 / 914.624 / 1246.08 | 1161.88 / 1973.33 / 2126.13 | 4766.82 / 10047.9 / 11031.8 |
| B1 | 0.025 / 0.222 / 0.822 | 0.019 / 0.087 / 8.706 | 0.024 / 2.077 / 55.861 | 0.031 / 3.035 / 130.462 | 0.046 / 80.482 / 730.555 |
| P | 1.361 / 1.817 / 2.265 | 9.632 / 14.781 / 17.582 | 56.234 / 125.135 / 162.06 | 185.645 / 371.138 / 455.089 | 392.367 / 757.208 / 885.792 |
| P-mcp | 8.289 / 10.649 / 11.685 | 40.35 / 45.724 / 47.61 | 307.324 / 882.699 / 984.868 | 961.036 / 1375.29 / 1656.72 | 1350.43 / 2643.94 / 3421.32 |

heartbeat: server-side `run_time_ms` p50 / p95 / p99 (ms), summed over the call's queries:

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| P | 0.219 / 0.369 / 0.413 | 0.388 / 0.751 / 0.806 | 0.541 / 1.175 / 1.633 | 1.034 / 2.058 / 2.856 | 1.095 / 1.866 / 2.701 |
| P-mcp | 0.28 / 0.502 / 0.648 | 0.257 / 0.891 / 1.318 | 0.718 / 2.731 / 9.955 | 1.37 / 3.724 / 10.182 | 1.268 / 2.509 / 7.44 |

### complete: client latency p50 / p95 / p99 (ms)

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| B0 | 1.59 / 2.876 / 4.205 | 19.843 / 32.719 / 37.506 | 346.657 / 656.44 / 690.743 | 1167.24 / 2945.15 / 3150.75 | 3905.73 / 10830.6 / 20003 |
| B1 | 0.044 / 0.355 / 1.235 | 0.04 / 0.216 / 19.087 | 0.043 / 0.206 / 8.592 | 0.041 / 0.216 / 18.841 | 0.057 / 2.241 / 129.654 |
| P | 4.589 / 5.938 / 7.017 | 23.129 / 34.397 / 40.469 | 113.891 / 210.151 / 297.273 | 307.125 / 587.349 / 702.956 | 580.723 / 1038.74 / 1272.83 |
| P-mcp | 7.75 / 9.911 / 11.333 | 35.748 / 50.961 / 55.653 | 363.806 / 626.811 / 660.63 | 859.51 / 1304.06 / 1957.2 | 1327.01 / 2455.58 / 2645.04 |

complete: server-side `run_time_ms` p50 / p95 / p99 (ms), summed over the call's queries:

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| P | 0.471 / 0.765 / 0.876 | 0.659 / 1.424 / 1.716 | 0.843 / 1.668 / 2.593 | 1.237 / 2.302 / 3.724 | 1.262 / 2.185 / 2.831 |
| P-mcp | 0.435 / 0.718 / 0.854 | 0.584 / 1.367 / 1.649 | 1.305 / 3.593 / 10.564 | 1.935 / 6.292 / 11.105 | 1.913 / 5.491 / 12.102 |

Errors across all claim points: 0.

### recall: client latency p50 / p95 / p99 (ms) and throughput

300 facts seeded; each recall embeds the query (arms with embeddings) and, for the Plexus/SQLite arms, records the recall.

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| B0 | 6.637 / 10.297 / 10.778 @ 141.2 | 80.012 / 109.926 / 119.744 @ 120.9 | 560.893 / 1308.82 / 1404.84 @ 68 | 1923.99 / 2530.7 / 2629.02 @ 52.5 | 2593.09 / 5877.74 / 6244.23 @ 59.2 |
| B1 | 2.476 / 4.673 / 6.842 @ 364.2 | 18.022 / 47.665 / 82.845 @ 382.2 | 73.724 / 448.526 / 1031.46 @ 287.7 | 137.797 / 1056.06 / 1955.76 @ 291.4 | 356.405 / 2745.99 / 4284.5 @ 204.9 |
| B2 | 24.565 / 67.253 / 86.947 @ 31.6 | 359.195 / 579.441 / 623.943 @ 26 | 1137.77 / 2204.85 / 2305.41 @ 37.4 | 2703.33 / 11429.3 / 12292.6 @ 21.7 | 10500.6 / 19224.8 / 26568.3 @ 17.9 |
| P | 253.814 / 506.965 / 624.438 @ 3.4 | 1480.88 / 2455.72 / 3008.25 @ 6.3 | 10774.8 / 21410.7 / 23348.6 @ 4.1 | 29013.9 / 44059.3 / 48542.9 @ 3.2 | 76203.5 / 113029 / 123034 @ 2.4 |
| P-mcp | 123.273 / 197.882 / 227.367 @ 7.6 | 976.811 / 1291.3 / 1365.88 @ 10.1 | 7231.59 / 13082.4 / 14607.5 @ 6.3 | 22662.9 / 31575.4 / 35742.6 @ 4.4 | 87752.9 / 148037 / 153533 @ 1.9 |

recall: server-side `run_time_ms` p50 / p95 / p99 (ms):

| Arm | 1 workers | 10 workers | 50 workers | 100 workers | 200 workers |
|---|---|---|---|---|---|
| P | 76.637 / 115.529 / 137.438 | 73.544 / 110.06 / 150.846 | 84.833 / 162.421 / 234.743 | 92.351 / 171.418 / 271.135 | 109.805 / 224.817 / 321.06 |
| P-mcp | 43.511 / 50.363 / 60.855 | 58.728 / 90.183 / 102.719 | 65.647 / 104.778 / 133.947 | 71.262 / 113.742 / 138.13 | 135.949 / 358.19 / 688.378 |

### Embedder alone (no database): the ceiling for recall

Recall embeds the query with one shared bge-small instance whose calls are serialised. With W closed-loop workers, latency ~ W / throughput (Little's law), so once that instance saturates, p50 grows linearly with W whatever the store behind it does. Compare with the server-side `run_time_ms` above (about 10 ms).

| Workers | Embeds/s | p50 / p95 / p99 (ms) |
|---|---|---|
| 1 | 68.4 | 11.38 / 30.866 / 30.866 |
| 10 | 59.7 | 138.834 / 319.141 / 502.18 |
| 200 | 79.8 | 2207.31 / 4215.63 / 4924.44 |

At 200 workers recall runs at 2.4 ops/s (P) and 1.9 ops/s (P-mcp), against 79.8 embeds/s for the embedder alone at 200 workers. The server-side time stays at 109.805 ms (P) / 135.949 ms (P-mcp) p50, while client p50 is 76.2 s / 87.8 s: that is the closed-loop queue (200 workers / throughput), not database time. P-mcp is slower than P here, which is the cost of its extra Step and ToolCall writes.

### One graph vs N tenant graphs (write ceiling), 50 workers, claim + complete

| Arm | 1 tenant | 4 tenants | 16 tenants |
|---|---|---|---|
| B1 | 425 ops/s, claim p99 1648.635 ms | 889.3 ops/s, claim p99 751.734 ms | 1771 ops/s, claim p99 362.282 ms |
| P | 111.7 ops/s, claim p99 1356.478 ms | 201.9 ops/s, claim p99 467.686 ms | 459.1 ops/s, claim p99 206.767 ms |

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

L1 re-run with the edges stripped as soon as they are written (`P-abl`) next to the intact Plexus arm:

| Arm | Test | Result |
|---|---|---|
| P | C4 | pass (3/3) |
| P | C8 | pass (3/3) |
| P-abl | C4 | **FAIL** 0/3 (started_before_deps_done=149) |
| P-abl | C8 | **FAIL** 0/3 (derived_facts_still_returned=60, not_marked_forgotten=60) |

## Limits and honesty notes

- Synthetic workloads and data only; one scenario family, a single-node database, scripted (non-LLM) workers.
- L1 workers are threads sharing one backend object (each with its own DB connection / file descriptors); only C2's victims are separate OS processes killed with SIGKILL. Concurrency is real but not deterministic: seeds fix the workload (priorities, DAG shape, values, query times), not the interleaving.
- Violations are reported as exact counts summed over all runs, never averaged.
- B0 and B1 are configured competently (locks / transactions). Where they match Plexus the table says so; Plexus's advantage is claimed only for what a graph does better: provenance, dependency traversal, time travel, contradictions at write time and cascading forget.
- L2 (provenance questions answered by an LLM for baselines) and L3 (end-to-end LLM agents) are out of scope of this run.
- L4 client latency is measured by Python threads in one process: at high worker counts it includes GIL queuing. Server-side run_time_ms is shown next to it for the Plexus arms.
- C5 probes each arm's tool API and, for Plexus, the MCP runtime's tenant binding (a header cannot rebind a connection). It does not probe the HTTP View API: that API is read-only, names the tenant in the URL and has no authentication in v1, so isolation there is by deployment. For B0/B1/B2 nothing stops a process with file access from opening another tenant's directory, and Plexus does not enforce per-graph access control inside FalkorDB either; a client with database access can query any graph.
- BASELINE §1 asks for one container per arm. B0/B1/B2 are embedded libraries with no server, so they run inside the crucible container; only FalkorDB (the Plexus arms) is a separate container.
- Numbers from `--quick` runs, or from outside Docker (Windows port forward adds ~10 ms per round trip), are not the published figures.

## Reproduce

```bash
docker compose -p plexus-bench --profile bench run --rm crucible all      # full L1 + L4 + ablation, inside the network
uv run crucible all --quick                                               # CI-sized, against a local FalkorDB
```
