# P10 / Crucible L7: graph (FalkorDB) vs SQL (SQLite), strengths and weaknesses by scale

Status: **pre-registration**. Written and committed before any L7 code, probe or measurement. Branch `p10`,
base `main` f96df06. LLM calls planned: **0** (every L7 family is deterministic).

Prior round: `docs/BASELINE.md` "L6 results" and "L6 after the fixes (P9-int)". L6 asked "does the graph beat
hand-written SQL on provenance questions?" and found ties on correctness, SQL as fast or faster, and a (since fixed)
crash-consistency gap. L7 does **not** redo that. It asks a different question: **where does each backend have a
structural strength or weakness for this product, from ~2 concurrent sessions up to hundreds**, and it tests the
user's working hypothesis instead of assuming it:

> Graph (FalkorDB) gives query expressiveness, easier multi-tenancy, and easier traversal. SQL (SQLite) gives
> atomic writes.

The hypothesis has four components. Each family targets the ones named here:

| Family | What | Hypothesis component(s) targeted |
|---|---|---|
| **G** | multi-tenancy at 1, 2, 20, 200, 2,000 tenants | graph: *easier multi-tenancy* |
| **H** | graph-shaped questions written in Cypher and SQL | graph: *expressiveness*, *easier traversal* |
| **I** | multi-entity all-or-nothing writes, crashes, conflicting writers | SQL: *atomic writes* |
| **J** | concurrent realistic sessions, 2 to 1,000 | all four, under load (the regime Plexus runs in) |

## Conventions carried over from L6

* **Seeded generators**, base seed `20261016` (`random.Random(20261016 + k)` per family/tenant/run `k`); ground
  truth computed in plain Python over the generator's own ledger, never read back from either backend. Before any
  question, each loader asserts node/edge counts against the ledger (`l6.stores.check_counts` style).
* **Results files** under `plexus/demo_data/crucible/l7/<UTC stamp>-<family>/results.json` (+ `report.md`),
  carrying `code_commit`, `dirty`, machine facts, FalkorDB module config, SQLite version, the seed, and per-cell raw
  numbers. A `latest-<family>.json` copy is kept.
* **Timeouts**: FalkorDB runs with the repo's `scripts/agent_db.sh` config (`TIMEOUT_MAX 10000`, `TIMEOUT_DEFAULT 5000`,
  `MAX_QUEUED_QUERIES 500`); L7 reads use a per-call `timeout` of **10,000 ms**; SQLite gets the same 10 s budget via
  a progress handler. A timeout is a wrong answer with latency 10,000 ms.
* **Latency**: client wall time p50/p99 and, for Cypher, server `run_time_ms`. SQLite is in-process, FalkorDB is
  across the Docker/WSL2 port-forward (BASELINE measured ~10 ms Windows->Docker overhead on some paths); every speed
  number is printed with "embedded" / "server" and no cell is called "faster" without that label.
* **Dev runs** at reduced size are allowed while building; they record no result. Anything a dev run makes me change
  in the design is written as a numbered **amendment** below, committed before the recorded run it affects.
* **Honesty rules** (BASELINE §6): ties and Plexus losses are reported as such; a scale that is infeasible on this
  machine is reported with the failure point and resource hit, never silently capped.

## Arms

| Arm | What |
|---|---|
| **F** | FalkorDB 6.0.2 (Docker), one graph per tenant (`plexus_t_<tenant>`, `graph/tenancy.py`), driven through the product's own code where the family has a product path (Engram/Relay/Lineage services, `Runtime._run` for the MCP path), hand-written Cypher elsewhere. |
| **S-file** | SQLite 3.53 (Python `sqlite3`), **one file per tenant**, WAL, `synchronous=NORMAL`, `busy_timeout`: the B1 store of `crucible/backends/sqlite.py`. |
| **S-shared** | SQLite, **one shared file**, a `tenant_id` column leading every primary key and index, row-level filtering in every query. (G, and J where noted.) |
| F-shared (optional, G only, if time) | one FalkorDB graph, `tenant_id` property on every node: the graph analog of S-shared. Marked "not run" if not run. |

Machine: Windows 11, 12 logical CPUs, Docker Desktop (WSL2, 12 CPUs, ~7.4 GiB to the VM). Other agents' idle
FalkorDB containers may be running on other ports; their state is recorded at run time (`docker stats` snapshot).

---

## G: multi-tenancy at scale (targets "graph gives easier multi-tenancy")

**Per-tenant world** (`l7.gen.tenant_world(k)`, seed `20261016 + k`): 5 agents, 10 sources, 100 facts (each derived
from 1 source or 1-2 earlier facts, depth <= 4), 30 steps reading 1-4 facts, 10 decisions based on 1-3 facts,
5 handoffs carrying 1-2 facts, 10 tasks with dependencies. Ids **deliberately collide across tenants** (`f0001`
exists in every tenant), values carry the tenant tag, and every tenant holds one **canary** fact
`canary_<tenant>` whose value is a 32-hex secret drawn from the tenant's seed.

Tenant counts **N in {1, 2, 20, 200, 2000}**, cumulative (tenants 0..N-1 exist when N is measured).

* **G1 creation latency.** F: `graph.schema.apply_schema` on a new graph (the product's real tenant-creation path:
  range, full-text and vector indexes plus UNIQUE constraints), then (separately timed) the bulk load of the world.
  S-file: create file + B1 schema + WAL. S-shared: insert the tenant's rows (there is no per-tenant DDL; the
  number is reported but is not a like-for-like "creation"). p50/p99 per tenant, and the total for 2,000.
* **G2 storage footprint.** F: `MEMORY USAGE <graph key>` per tenant (sampled: all tenants for N <= 200, 200
  sampled for 2,000), `INFO memory used_memory` delta / N, and the RDB size after `BGSAVE` / N; empty (schema only)
  and loaded. S-file: file size after `wal_checkpoint(TRUNCATE)` per tenant, empty and loaded. S-shared: file size / N.
* **G3 cross-tenant leakage (correctness gate, hard 0, not a performance number).** For every N, 200 ordered
  tenant pairs (A, B) (all pairs when fewer): from tenant A's binding, try to read tenant B's data:
  * **G3a product path** (what an agent can reach): look up B's canary id; `why`/`impact`-style traversal from B's
    canary; keyword search for B's secret; the colliding id `f0001` must return A's value, never B's. F through the
    product services bound to A; S-file / S-shared through the hand-written SQL with A's binding.
    **Gate: 0 leaked rows for every arm.** Any non-zero is a bug and blocks the verdict.
  * **G3b raw query-language channel** (what a holder of the query channel can do: an LLM with a raw Cypher/SQL
    tool, as B1a had in L6, or a compromised server). F without ACL (the current deployment: one password) and F
    with a per-tenant Redis ACL user (`~plexus_t_<A>` key pattern, `+GRAPH.RO_QUERY`); S-file raw SQL, with and
    without an authorizer that denies `ATTACH`; S-shared raw SQL, with and without "views + authorizer". Reported
    as a matrix of *leaks / blocked* per configuration (an isolation property, not a gate).
* **G4 latency as a function of N.** After N tenants exist, one client thread runs 2,000 operations, each on a
  tenant drawn uniformly at random: q1 fact by id, q2 decisions based on a fact (1 hop), q3 why-chain (recursive,
  depth <= 4), q4 a write (one fact + one derived-from link). Arms: F (one pooled client, graph chosen by key),
  S-file-cached (one open connection per tenant kept), S-file-open (connect, query, close per op), S-shared.
  Reported: p50/p99 per op and N; ratio N=2000 / N=1; handles/memory of the client process; any failure
  (file-descriptor / handle limit, Redis memory) with the N at which it occurred.

**G predictions.**
1. G3a: 0 leaks in every arm (all four are isolated on the product path by construction).
2. G3b: F without ACL leaks (any graph key is reachable); F with ACL blocks; S-file leaks via `ATTACH` without an
   authorizer and is blocked with one; S-shared leaks without views+authorizer. So the raw-channel isolation of F
   and S-file is a configuration choice of similar effort; S-shared has no database-enforced row isolation.
3. G4: F p50 within 1.5x from N=1 to N=2000 for every op; S-file-cached the same; S-file-open has a constant
   connect overhead (predict +0.1-1 ms per op) but is flat in N; S-shared p50 within 1.5x (B-tree depth grows
   logarithmically). 2,000 open SQLite connections succeed on Windows (no CRT fd limit for Win32 handles).
4. G1: F `apply_schema` costs 20-200 ms per tenant (it creates ~10 indexes and waits for constraints), S-file
   creation 1-20 ms: **SQLite creates tenants faster**. 2,000 F tenants fit in the container's memory.
5. G2: an empty F tenant (schema only) is 20-500 KB of Redis memory; an empty S-file tenant 50-300 KB on disk.
   Neither is predicted to be smaller by more than 3x.
6. **Reading rule for "easier multi-tenancy".** *Confirm* only if F beats **both** SQLite layouts on at least one
   G axis (isolation, flat latency, creation, footprint, tenant-handling code) and loses on none by > 3x. *Refine*
   if F ties S-file (per-tenant container isolation is then a property of "one database object per tenant", not of
   graphs) and beats only S-shared. *Refute* if S-file beats F on isolation and latency. **Predicted: refine.**

---

## H: query expressiveness and traversal (targets "expressiveness" and "easier traversal")

**World** (`l7.gen.h_world(scale)`, one tenant): agents, sources, facts with `status` in {active 75%, superseded
15%, quarantined 10%}, `DERIVED_FROM` (fact->fact, fact->source), `ASSERTED_BY`, `Step-BY->Agent`, `Step-READ->Fact`,
`Agent-DECIDED->Decision`, `Decision-BASED_ON->Fact`, `Handoff FROM/TO Agent, CARRIES Fact`. Background edges are
random, and **motifs are planted** (so every answer is non-trivial) plus whatever the random background creates by
chance (truth counts both). Scales: **small** (~2,000 facts, 50 agents) and **large** (~50,000 facts, 200 agents).

Queries (each written by hand in Cypher and in SQL against the B1-like schema, with the indexes a competent author
adds; truth by Python over the ledger):

* **H1 motifs (pattern queries)**
  * **H1a shortcut triangle**: facts a, b, c with `a->b`, `b->c` and `a->c` (all `DERIVED_FROM`), asserted by three
    distinct agents. Answer: count, and the 5 lexicographically smallest (a, b, c).
  * **H1b handoff cycle**: three distinct agents x->y->z->x via three handoffs, each carrying a fact derived directly
    from one common source. Answer: number of distinct (rotation-canonical) agent cycles, 5 smallest.
  * **H1c independent corroboration**: two active facts with the same subject and predicate, asserted by different
    agents, derived (directly) from different sources, neither derived from the other at any depth. Answer: count
    of unordered pairs, 5 smallest.
* **H2 multi-relationship-type traversal**: for an agent X, pairs (D, f) where X `DECIDED` D, D `BASED_ON` g,
  `g -[:DERIVED_FROM*0..N]-> f`, and some Step of X `READ` f **before** `D.at`. N in {0, 2, 4}; 8 agents per N
  (24 questions). Answer: count of pairs and the 5 smallest. (N = 0 is the user's literal example: "facts read by an
  agent and that a decision by the same agent is based on".)
* **H3 variable-predicate shortest path**: shortest directed `DERIVED_FROM` path from fact a to fact b whose
  **intermediate** facts all have `status = 'active'`. 12 pairs per scale: 4 where the unconstrained shortest path
  is also valid, 4 **traps** where the unconstrained shortest path crosses a non-active fact and a longer valid one
  exists, 4 reachable only through non-active facts (answer: none). Answer: hop count (or none); a returned path
  must be valid and of that length (any shortest path accepted).
* **H4 aggregate over closures**: for every source, the number of distinct agents with a decision that depends on
  it at any depth (decision -> based-on fact -> derived-from* -> source). Answer: the top 10 (source, count), ties
  by id.

**Scoring.** (1) Correctness, strict, against the truth. (2) **Expressiveness proxies, reported as numbers**:
non-blank non-comment lines of the query text; statements per answer; round trips; lines of application code
(Python) needed beyond "send the statement"; and a yes/no: *could this be written as one declarative statement that
a reasonable reviewer would accept?* Where SQL (or Cypher) cannot express it cleanly, the attempt is shown and
marked so. (3) Execution time, 5 repetitions, p50/p99, at small and large scale.

**H predictions.**
1. Correctness: every arm that answers is correct on H1, H2, H4. Lines: Cypher < SQL on H1a, H1b, H1c, H2, H4
   by at least 30% each (Cypher/SQL line ratio <= 0.7).
2. H3: FalkorDB's `shortestPath()` does not accept a predicate on intermediate nodes (predicted from the docs; a
   filter written after it is applied to *the* shortest path, not a constrained search) so the traps make it wrong;
   a variable-length pattern with `all(n IN nodes(p) WHERE ...)` and `ORDER BY length(p) LIMIT 1` is correct but
   enumerates paths and times out at large scale; SQL's recursive CTE needs a path string for cycle-safety and also
   enumerates. Predicted: the only correct-and-fast H3 in **both** languages is an application-side BFS (one
   statement per level). So H3 is "expressible but not efficiently in one statement" for both.
3. Speed: SQLite (embedded) is faster than FalkorDB (server) on >= 60% of (query, scale) cells (as in L6); FalkorDB
   is faster on at least one motif cell at large scale (H1a or H1b: pattern matching over adjacency).
4. **Reading rules.** *Expressiveness confirmed* if Cypher is shorter by >= 30% on >= 4 of the 5 queries
   H1a/H1b/H1c/H2/H4 **and** at least one of them needs app-side code or multiple statements in SQL but not in
   Cypher; *refuted* if Cypher is not shorter on a majority. *Easier traversal* is split: "easier to write" (lines,
   statements on H2/H3/H4) and "faster to run" (latency on H2/H3/H4); predicted **write: confirmed, run: refuted**.

---

## I: atomic multi-entity writes (targets "SQL gives atomic writes"; adversarial toward Plexus's side)

**The composite write ("close-out")**, modeled on what an agent does at the end of a task in the recorded Claude runs
(`demo_data/recordings/acme-claude-sonnet/calls.json`: `assert_fact`, `record_decision`, `complete_task`, `handoff`
in sequence): one logical operation that must be all-or-nothing, touching >= 6 entities over 6 labels/tables:
Step (agent's step), Fact (DERIVED_FROM a Source, ASSERTED_BY the agent, WROTE by the step), Decision (BASED_ON the
fact, DECIDED by the agent, FOR the task), Task update (status `done`, version + 1, `done_at`; guarded by the
expected version), Artifact (PRODUCED for the task), Handoff (FROM/TO agents, FOR the task, CARRIES the fact). Every
entity carries the close-out id `co`, so a partial close-out is detectable.

Arms:

| Arm | How the close-out is written |
|---|---|
| **S-txn** | SQLite `BEGIN IMMEDIATE`, one statement per entity, `COMMIT` (version guard: `UPDATE ... WHERE version=?`, 0 rows -> `ROLLBACK`). |
| S-auto | the same statements in autocommit (a control: SQL's guarantee exists only if used). |
| **F-product** | the Plexus product path as it is: four MCP tool calls through `Runtime._run` (`assert_fact`, `record_decision`, `complete_task`, `handoff`), each its own write(s) + Step + ToolCall. There is no cross-tool transaction. |
| F-multi | the same entity writes as separate Cypher statements, one round trip each (the client-side convention). |
| F-multiexec | the same statements as `GRAPH.QUERY` commands inside Redis `MULTI` / `EXEC` (if FalkorDB accepts them there). |
| **F-1stmt** | one Cypher statement that matches the task with its version guard first and creates/updates everything. |

Tests:

* **I1 writer crash**: a writer process loops close-outs and is killed hard (`TerminateProcess`) 0-400 ms after
  "ready"; 200 kills per arm, new process each time (L6-F protocol). Count: close-outs with some but not all of their
  entities (**partial**), acknowledged close-outs missing anything (**lost**), totals.
* **I2 logical abort**: 25% of close-outs carry a stale expected task version (seeded). The task must not change and
  nothing of that close-out may exist. For F-1stmt both forms are run: guard-first (`MATCH ... WHERE version = $v`
  before any `CREATE`) and guard-last (creates first, then a runtime error if the version does not match): this tests
  whether a runtime error inside one FalkorDB statement rolls back that statement's earlier clauses.
* **I3 database-server crash**: F: `docker kill -s KILL` of the arm's own FalkorDB container while 4 writers run
  close-outs (F-1stmt and F-multi), restart, count partial and lost acknowledged; 20 kills. S: the SQLite engine runs
  inside the writer, so I1 is its server crash. Also: the slot-64 container found at the start of this round
  segfaults while replaying its own AOF on restart (`.p10/aof-crash-evidence/`, `container.log`: "Guru Meditation:
  illegal decrRefCount", stack in `graph_free`); I3 tries to reproduce that from the preserved data directory and
  reports whether it does.
* **I4 conflicting concurrent writers** (W = 20 and 200 threads, 50 operations each, one tenant):
  * **I4a lost update** on a counter property, four modes per backend: naive read-then-write (two statements),
    atomic single statement (`SET c = c + 1` / `UPDATE c = c + 1`), optimistic CAS on a version with retry, and
    pessimistic (SQLite `BEGIN IMMEDIATE` read-modify-write; FalkorDB `WATCH <graph key>` + `MULTI`/`EXEC`, retried
    on abort). Lost updates = W x 50 - final counter; conflict/retry rate reported.
  * **I4b write skew** across two entities: invariant "at most one of tasks t1, t2 is claimed by an on-call agent";
    each writer checks both and claims one. Modes: one statement (both backends), multi-statement without a
    transaction (both), SQLite `BEGIN IMMEDIATE` vs `BEGIN DEFERRED`. Violations counted.
* **I5 single-statement sufficiency**: F-1stmt vs S-txn on the same close-out: lines of code, round trips, client
  latency p50/p99 (1 writer and 8 writers), and their I1/I2 results. Reported whether one Cypher statement is
  sufficient and simpler for this write.

**I predictions.**
1. I1: S-txn **0 partial, 0 lost** in 200 kills; F-1stmt **0 / 0**; F-multiexec **0 / 0** (queued commands are
   dropped when the client dies before `EXEC`); S-auto, F-multi and F-product **> 0 partial** (F-product: >= 10
   partial close-outs in 200 kills, because a close-out is >= 4 round trips plus audit writes).
2. I2: S-txn 0 partial; F-1stmt guard-first 0; F-1stmt guard-last **0** (FalkorDB undoes a failed statement);
   **F-multiexec > 0 partial** (Redis `EXEC` has no rollback: commands queued before the failing one stay applied);
   F-multi and F-product > 0 unless the client compensates.
3. I3: 0 lost acknowledged writes for F after server kills (Redis appends to the AOF before replying, and the
   page cache survives a process kill); F-1stmt 0 partial, F-multi > 0 partial. The AOF-replay crash: predicted
   **not** to reproduce deterministically (stated as unknown if it does not).
4. I4a: naive RMW loses updates in **both** backends (> 0 at W = 20); atomic single statement: 0 in both; CAS: 0 in
   both; pessimistic: SQLite 0; FalkorDB `WATCH` on a graph key **works** (FalkorDB signals key modification), so 0.
   I4b: one statement 0 violations in both; multi-statement without a transaction > 0 in both; SQLite IMMEDIATE 0;
   SQLite DEFERRED 0 violations but `SQLITE_BUSY` upgrade errors.
5. **Reading rule.** *Confirmed* if S-txn is 0 partial in I1 and I2 while the Plexus product path (F-product) is
   > 0 in I1 or I2, **and** FalkorDB has no multi-statement primitive that gives both crash atomicity and rollback.
   *Refined* (cut against "SQL wins atomicity") if F-1stmt matches S-txn on I1/I2 with fewer lines/round trips: then
   "SQL gives atomic writes" holds for writes that span statements, not for writes one Cypher statement can express.
   **Predicted: confirmed for multi-statement and multi-tool writes, refined by I5** (both are reported).

---

## J: concurrent session populations (all components, under load)

**Session mix, from real tool calls** (not invented): the per-agent call sequences of the two recorded Claude runs,
`acme-claude-sonnet` (83 calls) and `pilot-haiku` (17 calls): start_session 20%, recall 16%, claim_next_task 16%,
complete_task 14%, add_source 8%, assert_fact 8%, remember_episode 5%, record_decision 5%, handoff 4%, create_tasks
3%, verify_artifact 1%. A session replays one recorded agent's sequence (seeded choice), with arguments synthesized
by a seeded generator (subjects, values, ids that exist). **J-trav**, a second mix, replaces 10% of the calls with
`why` / `impact` traversals (not in the recordings, which predate those tools; marked as an assumption). Each
session runs in a closed loop (next session starts when one ends) for the cell duration.

**Population P in {2, 20, 200, 1000}** concurrent sessions. Tenant layouts: **J-team** (5 sessions per tenant, so
P/5 tenants, minimum 1) and **J-one** (all sessions in one tenant: the worst case for per-tenant write serialization).
Arms: **F-mcp** (Crucible `PlexusBackend(mode="mcp")`: the product path with Step + ToolCall per call), **F-service**
(the same services without the per-call audit), **S-file** (the B1 SQLite backend); S-shared for J-team if time.
Client: K = min(8, P) driver processes, P/K threads each, the same harness for every arm; embedder `hash` for F
(no model), FTS5 for S (as B1). Cell: 5 s warm-up + 30 s measured, 3 repetitions (median of repetitions reported,
all kept).

Reported per cell: throughput (completed tool calls/s), p50/p99 latency overall and per tool, error rate by class
(`database is locked`/busy, timeout, `Max pending queries exceeded`, pool exhaustion, other; claim conflicts are
domain outcomes, not errors), FalkorDB container CPU% and memory (`docker stats` every 1 s), driver processes' CPU
time and peak working set (they contain the SQLite engine for S), and the FalkorDB server time share.

**J predictions.**
1. Throughput: S-file >= F-service >= F-mcp at every P and layout (embedded engine, no network hop; L4 measured
   SQLite 1456 vs Plexus 373 claim ops/s at 200 workers). F-mcp is 2-4x below F-service (audit writes).
2. J-one at P >= 200: S-file p99 is **higher** than F-service p99 (SQLite's busy handler has no fair queue: L4 saw
   p99 2.2 s), although its throughput stays higher.
3. J-team scales better than J-one for both (F: independent graphs; S: independent files), by >= 1.5x at P = 200.
4. P = 1000: F produces `Max pending queries exceeded` errors (> 0) in J-one (`MAX_QUEUED_QUERIES 500`); S-file
   produces 0 lock errors (120 s busy timeout) but p99 > 5 s in J-one. If 1,000 sessions are infeasible (threads,
   connections, memory), the failure point is reported.
5. FalkorDB CPU saturates below the client's (one writer per graph; reads in the thread pool): in J-one the
   container stays near one core of CPU for writes.

---

## Verdict table (filled in after the runs; criteria fixed now)

| Component | Families | Confirm if | Refute if | Predicted |
|---|---|---|---|---|
| Graph: expressiveness | H1, H2, H4 | Cypher >= 30% shorter on >= 4/5 queries and >= 1 query needs app code / multi-statement in SQL only | Cypher not shorter on a majority | confirm |
| Graph: easier traversal | H2, H3, H4, J-trav | write: fewer lines/statements; run: Cypher faster on a majority of cells | the opposite | write confirm, run refute |
| Graph: easier multi-tenancy | G, J-team | F beats both SQLite layouts on >= 1 G axis, loses none by > 3x | S-file beats F on isolation and latency | refine (per-tenant DB object, not graph) |
| SQL: atomic writes | I1-I5, J errors | S-txn 0 partial (I1, I2), F-product > 0, no FalkorDB primitive with crash atomicity + rollback | F-product 0 partial and FalkorDB has such a primitive | confirm, refined by I5 |

## Amendments

### Amendment 1 (written after the harness builds and dev runs; before the recorded G, H and J runs and the I5 re-run)

Family I's recorded run has already happened (`plexus/demo_data/crucible/l7/20261016T100730Z-i-merged/`, all parts
`--scale full`). Its design choices below (I-1..I-6) were fixed in the code before that run started; the notes file
that lists them was written while the run was in progress, so they are recorded here after the fact, not before.
The I harness code was uncommitted at run time (committed afterwards as `31e6627`; only `ruff format` changed it), and
its `results.json` says `dirty: false` because the L6 `git_state` it used only inspected `crucible/l6/`; the L7
envelope now checks the whole `plexus/` tree (`05632f9`). Everything else here is fixed **before** the run it affects.
Dev runs (reduced size, not results) were made for G, H and J while other benchmarks loaded the machine; what they
showed is stated so that the reader can see which choices were made with a number in view.

**Family I (as run).**
* I-1 The SQLite store for I is purpose-built (`l7/i_queries/s_schema.sql`, one table per entity plus join tables), not
  the B1 schema (B1 has no Step/Artifact/Handoff-carries shape matching the close-out). `busy_timeout=10000`, WAL,
  `synchronous=NORMAL`.
* I-2 A close-out has 14 checkable items (fact, its derived-from, asserted-by, the step, step-WROTE, decision, based-on,
  decided/for, artifact, artifact links, handoff, handoff links, carries, task done at version+1). Complete = 14,
  absent = 0, partial = anything else; one classifier for every arm. F-product mints its own ids: the values passed
  through the tool arguments carry the close-out id, and its Step counts as present when a Step has a WROTE edge to the
  tagged fact.
* I-3 Each close-out needs a claimed task at a known version; that setup is outside the close-out (one autocommit
  statement; F-product: `create_tasks` + `claim_next_task` through the product). The writer prints an intent line
  before and an ack line after each close-out; "in flight at kill" = intent without ack, the only close-outs whose
  atomicity a kill actually tests (reported as complete / partial / absent).
* I-4 Added arms beyond the table: `F-multi-cas-first` (task guard as the first statement: a careful client),
  `F-multiexec-err` (the guard miss raised as a runtime error inside `EXEC`). `F-multi` keeps the product's order
  (guard fourth).
* I-5 I3 uses 4 writer threads per cycle, 0.4-1.6 s of writes, then `docker kill -s KILL`, `docker start`, health
  check; a server that crashed after restart (seen once in dev: plexus-db-68 segfaulted ~3 s after an AOF-replay
  restart while a new graph was created; a crashed Redis stays "Up" in Docker and answers nothing) is detected by
  `REDIS BUG REPORT` in the log and restarted; such events are counted in the results.
* I-6 I4a: W threads, 50 ops each, CAS/WATCH retries with 0-2 ms jitter, 240 s budget per cell; the FalkorDB
  pessimistic W=200 cell hit the budget and was re-run once with 1,500 s (`20261016T104743Z-i`), the merged file flags
  it `replaces_incomplete_cell`. I4b: 500 rounds of two writers released on a barrier, think time 0 and 2 ms.
* I-7 (before the re-run) I5 timings in the merged file were taken while family J's dev run loaded the machine; I5 is
  re-run alone (`--parts I5`) and that run is the reported I5 latency; the merged file's I5 numbers are kept as
  "loaded machine".

**Family G (before the recorded run).**
* G-1 Generator `l7/g_gen.py`: tenant `g<k:04d>`, 99 ordinary facts + the canary, max derived-from depth exactly 4,
  every value tagged with the tenant. F bulk load = `apply_schema` (timed as creation) then 18 `UNWIND` statements
  writing the product model's properties (embedding from the `hash` embedder, Entity/Scope/ABOUT/IN_SCOPE edges) so
  that the real `Engram.recall`, `Lineage.why` and `Lineage.impact` work on it: G3a uses those product services for F,
  no hand-written Cypher.
* G-2 G2: `MEMORY USAGE <graph key>` returns a constant 40 bytes for every graph (the key object only) and
  `GRAPH.MEMORY USAGE` reports whole MB (0 here): neither is usable. F footprint is therefore the `INFO used_memory`
  delta per tenant, `docker stats` memory, and RDB size after `BGSAVE` per tenant. Empty (schema-only) footprint is a
  separate first experiment of 200 schema-only graphs. **Dev showed an empty F tenant at ~0.73 MB of `used_memory`,
  outside prediction G5 (20-500 KB); the prediction is not changed and will be reported as wrong if the run agrees.**
* G-3 G3b: per-tenant ACL user `~plexus_t_<A>` with `+graph.query +graph.ro_query +graph.explain +graph.profile`
  (not `+graph.list`: it has no key and would list every tenant's name); S-shared protection = 13 per-tenant
  `TEMP VIEW`s + an authorizer denying direct reads of `main.*` and any non-SELECT action. 50 raw-channel pairs per N.
* G-4 G4: 2,000 operations **per op type** per arm per N (the pre-registration's "2,000 operations" read per op
  type), same seeded tenant/fact sequence for every arm, every answer checked against the ledger; q4 on F writes a
  minimal Fact (no embedding), unlike the product's `assert_fact`. First use of a (tenant, op) on F is reported apart
  from repeat use (each graph has its own plan cache). Dev at N <= 200: F p50 flat (ratio 1.1-1.3), S-file-cached q4
  grew from ~0.13 to ~1.6 ms. F-shared: not run.
* G-5 Full run: cumulative N = 1, 2, 20, 200, 2000 in one process; dev projected ~11-12 min to create and load 2,000
  F tenants and ~4.3-6.5 GB of Redis memory at N = 2000 against a 7.4 GiB VM; if memory runs out, the N and the
  resource are reported.

**Family H (before the recorded run).**
* H-1 Generator change before any query was timed: with the first background (30% roots, 1.4 parents among the
  rest, uniform attachment) the dev check of the truth found closures of ~9-22 facts (subcritical), so traversal
  would not have been tested at all. The background now uses 10% roots, 1 or 2 parents (50/50) drawn 60% from the
  100 most recent facts and 40% uniformly: large-scale closures average ~1,500 facts (max ~4,600). Statistics of
  the truth only were looked at, no query timing.
* H-2 Arms (all statement texts in `l7/h_queries/`): H1a, H1b, H1c, H2 one Cypher and one SQL statement each; H1c
  also `h1c.natural.cypher` (see H-4); H4 `naive` (one variable-length pattern), `distinct` (DISTINCT between hops),
  `bfs` (FalkorDB `algo.BFS`, max_level -1) in Cypher and one recursive CTE (`UNION`) in SQL; H3 Cypher: `varlen`
  (`*1..8` + `all(...)` + `ORDER BY length LIMIT 1`), `varlen+unbounded` (`*1..`), `shortestpath` (illegal with a
  predicate: the predicate is checked on the single returned path, so it is wrong on traps by construction, kept to
  show it), `bfs_level+app-bfs` (one statement per BFS level, Python BFS `h.bfs`); SQL: `path_cte` (path string,
  `UNION ALL`, depth < 8), `path_cte+unbounded`, `depth_cte` (one row per (node, depth) by `UNION`; returns the hop
  count only, no path; scored on hops), `bfs_level+app-bfs` (the same Python BFS). The H3 answer is unbounded; every
  planted answer is <= 6 hops, so the depth-8 variants are an author who knows paths are short.
* H-3 **Rule for "the answer" per language, fixed now, before any large-scale timing:** for each question family and
  language, the reported answer is the correct single-statement variant with the fewest lines that answers every
  question of the family at both scales within 10 s; if none, the correct variant with the fewest round trips
  (the app-side BFS for H3). Every variant is reported regardless.
* H-4 **FalkorDB 6.0.2 silently answers the natural H1c wrongly** (found at toy size, before any recorded run). In
  `MATCH (f1 ...)-[]->(s1) MATCH (f2 {subject: f1.subject, ...})-[]->(s2) WHERE ... MATCH (f1)-[:ASSERTED_BY]->(a1),
  (f2)-[:ASSERTED_BY]->(a2) ...`: (i) the inline map that refers to `f1` matches nothing (0 rows; with a `WITH f1, s1`
  before it, 29 rows, correct), and (ii) after a Value Hash Join, the later `MATCH` on the already-bound `f1`/`f2` is
  planned as a Cartesian product with fresh label scans: 3.78 M rows on a 361-fact toy graph instead of <= 29; at
  2,000+ facts it fails with "Query's mem consumption exceeded capacity". `h1c.cypher` therefore puts a `WITH`
  barrier between every stage (16 lines instead of 7); the natural form is reported as its own arm. Correctness is
  scored per arm, so any further planner error shows up as a wrong answer.
* H-5 Dev (small 2k and medium 10k facts, loaded machine): every arm correct except the two expected ones and
  `h4.naive` (timeout at 10k); `h1c.cypher` took 8.5 s at 10k facts (its `NOT (f1)-[:DERIVED_FROM*1..]->(f2)`
  predicates enumerate paths), SQL 1.3 s; an `algo.BFS` form of H1c timed out at 10k and is not an arm. H2 Cypher
  needs the hop bound as a literal (FalkorDB takes no parameter in `*0..N`), so the statement is a template; SQL takes
  `:n` as a parameter.

**Family J (before the recorded run).**
* J-1 Sessions replay one of the six recorded agents' sequences (acme planner/researcher/builder, pilot
  planner/researcher/builder) chosen uniformly; that reproduces the pooled mix (dev realised: start_session 20.2%,
  recall 16.3%, claim 15.9%, complete 13.8%, ...). One fresh agent id per session; session RNG
  `Random(SEED + rep*100000 + slot)`, identical scripts across arms.
* J-2 Task supply, identical on every arm: preload `clamp(25 x sessions in tenant, 100, 5000)` tasks plus 4 anchor
  tasks; each replayed `create_tasks` adds 6 tasks; a `claim_next_task` that returns nothing is followed by one extra
  6-task `create_tasks` counted as `create_tasks_refill`. `complete_task` is replayed only when the session holds a
  claim (else skipped, not counted).
* J-3 Tools the B1 store lacks: `start_session` (new `sessions` table) and `verify_artifact` (new table) are written in
  `BEGIN IMMEDIATE`; `remember_episode` on S has no session link (one link fewer than F: favours S slightly).
  `derived_from` carries fact ids only on both arms. F-mcp = `Runtime._run` (Step + ToolCall per call) without the
  per-agent lock and the JSON transport. J-trav: 10% of calls (after the first) replaced by `why` (50%) / `impact`
  (50%); F uses the product tools' work functions, S uses B1 `why` and one recursive CTE for `impact`, which needs a
  `step_reads(fact_id)` index created in J-trav cells only.
* J-4 Counting: a call belongs to the cell if it finishes after warm-up; throughput = ok / no-task / claim-conflict
  calls finished inside the 30 s window; errors are excluded from throughput and listed by class (`locked`,
  `timeout`, `max_pending`, `pool`, `connection`, `unknown_ref`, `other`); latency includes the calls in flight at the
  window end (`late_finishers`, about P). No per-call budget is added in J: F keeps the server's `TIMEOUT_DEFAULT
  5000`, S keeps B1's 120 s `busy_timeout` (the 10 s convention is not applied in J; it would turn lock waits into
  timeouts). "GRAPH.* busy" from `INFO commandstats` is command wall time including waits, not CPU.
* J-5 **Grid trimmed** (dev measured ~2 h 15 min for the full 144 cells): **J-real** all 4 populations x 2 layouts x
  3 arms x **3 repetitions** (72 cells, median of repetitions reported); **J-trav** the same 24 cells x **1
  repetition**. 5 s warm-up + 30 s measured as registered. S-shared for J: not run.
* J-6 Dev showed (loaded machine): `Max pending queries exceeded` only with many graphs (P=1000 J-team, 200 graphs:
  53,423 of 59,370 F-service calls failed) and **0** with one graph and 1,000 callers (p50 13-24 s instead), which is the
  opposite direction of prediction J4's "in J-one"; S-file 0 errors at every P with p99 14-24 s in J-one at P >= 200.
  Prediction J4 is not changed. 1,000 sessions are feasible (8 processes, ~660 MB of drivers, < 1,700 handles).

### Amendment 2 (after the recorded H run, before the recorded J and G runs)

* G-6 If a tenant cannot be created in some arm (e.g. out of memory), the G driver now records the failure (N,
  tenant, arm, error, `docker stats`) as `infeasible` and finishes the report with the levels already measured,
  instead of raising and losing the level (`g.py`, commit after this text). Nothing else in G changes.
* G-7 Memory safety on a shared VM: the WSL2 VM has 7.4 GiB and other people's containers (one Postgres alone uses
  1.4 GiB). Before the G run plexus-db-65 gets `CONFIG SET maxmemory 3800mb` (policy stays `noeviction`), so that a
  FalkorDB tenant population that does not fit fails inside Redis with an `OOM command not allowed` error (reported as
  the infeasibility point) instead of letting the VM's OOM killer pick a container. If 2,000 tenants hit that limit,
  that is the result: "2,000 product-schema tenants do not fit in 3.8 GB of FalkorDB memory on this machine", with
  the N reached.
* Run order: J (alone), then G (alone).
