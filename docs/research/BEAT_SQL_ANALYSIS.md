# Can Plexus beat SQL and files? Design analysis for a pre-registered Crucible L6

Written 2026-10-16 (Graph Hacks, Track 02). Status: analysis, no repo code changed. Sources: our code and results (file:line cited), two
micro-probes I ran today (§2, queries in Appendix A), and a few external references (ledger: `docs/research/.ledger-beat-sql.json`).
Labels: **[measured]** = I ran it today, **[repo]** = from our committed results, **[inf]** = my inference, a hypothesis to test.

## 0. Short answer

1. **The L1/L2 tie is mostly a benchmark-design fact, not a verdict on graphs.** In L2 the SQLite arm is *not SQL*: the model gets a
   CSV dump in one shot with no tools (`l2/contexts.py:7`, `l2/llm.py:5,9`), while Plexus gets a developer-written query per
   question. L2 therefore compares "a deterministic query vs. an LLM reading a capped dump". The SQLite backend that *does* have
   recursive CTEs (`backends/sqlite.py:410`, `:675`) was never asked the L2 questions. A hand-written-SQL arm would, I expect, tie
   Plexus at 100% (§1.3).
2. **There is no capability in agent memory where a graph store beats a competent relational schema on correctness**, and I found none
   where it wins latency by an order of magnitude [measured, §2]. On traversal, our own Cypher was the *worse* side until we hand-tuned it
   (§2.1). What a graph gives is a natural model, one-statement writes, Cypher ergonomics, and vector+traversal in one engine.
3. **Large, honest gaps do exist against the status quo** (files, flat vector retrieval, a one-shot LLM reader) once the history exceeds
   the context and the question is deep, wide or cross-project. They come from *structured, provenance-bearing, queryable memory*,
   not from FalkorDB specifically. Any L6 must therefore carry a **hand-written-SQL control arm** so the two claims are reported
   separately: "structured memory beats the status quo" (likely true, large) and "graph beats SQL" (likely false, report the tie).
4. **Two places where Plexus can plausibly beat a competent SQL arm** need product work first: multi-hop associative recall (§3, C) and
   dependency/impact features beyond what an edge table gives for free (§5). **One place where Plexus will probably lose** is
   crash-consistent provenance (§3, G), and that loss is fixable.
5. Recommended claim for the submission is in §6. Do not claim "faster", "more correct", or "better than SQL".

---

## 1. Why Plexus tied

### 1.1 What the arms actually are

| Arm in L1 | What it is | Provenance/graph features |
|---|---|---|
| B1 SQLite | `BEGIN IMMEDIATE` transactions, edge table `fact_links(src,dst,kind)` (`sqlite.py:81-83`), recursive CTEs for `why` and `forget_source` (`:410`, `:675`), `capabilities` includes why/knew_at/as_of/forget_cascade/dependencies (`:111`) | Full, in SQL |
| B0 files | flock + atomic replace; "no transactions across files" (`files.py:15`) | None queryable (`Unsupported`) |

| Arm in L2 / L2-scale | What the model or code is given |
|---|---|
| B0, B1 | A **text artifact**, cut or BM25-selected to 32,000 chars, one-shot, `--tools ""` (`l2/llm.py:5,9`). B1 = schema + CSV rows: "the model cannot run SQL, so a dump is what a one-shot reader gets" (`l2/contexts.py:7`) |
| B2 | Top-12 vector chunks |
| P | A hand-written Cypher answerer (`l2/plexus_answerer.py`), no LLM |

So the 43/43 vs 43/43 tie (small history) says "Sonnet can read 18-25k chars". The 36/36 vs 32/36 (scale) says "a query beats a reader
whose context holds the wrong rows". **Neither run asks whether Cypher beats SQL.** §8.2 of the report concedes the Cypher is hand-written, but
understates the point: the baselines were not given *any* query execution, hand-written or otherwise.

### 1.2 Per question family (L2's 10 families, with L2-scale scores B0/B1/P) [repo]

| Family | Real shape | Hops / tables | Would hand-written SQL do it? | What discriminated in L2-scale |
|---|---|---|---|---|
| Decision provenance (1/4, 1/4, 4/4) | Decision→Fact→Agent/Source | 3-table join (`queries/l2/decisions.cypher`, one-hop `DERIVED_FROM` to Source) | Yes, one join | Reader retrieval miss: the second fact or its source was outside the 32k (`BASELINE.md:267`) |
| Handoffs (3/4, 4/4, 4/4) | Handoff→items | 2 joins | Yes | One B0 miss |
| Time travel (3,3,3) | `valid_from <= t < valid_to` | 1 table, range predicate | Yes, indexable | Nothing |
| Supersession impact (4,4,4) | Decision→Fact{status} | 1 join | Yes | Nothing |
| **Dependencies (2,2,3)** | **Transitive closure over `DEPENDS_ON`** | **Recursive; DAG of 12 tasks, depth ~4** (`l2/queries/l2/tasks_downstream.cypher:7`) | **Yes, one CTE** | Q17: B1 had all six ids in context and still missed the chain: a *reader reasoning* error (`BASELINE.md:268`). Only family where the answer shape is graph-like |
| Contradictions (3,4,4) | Self-join on subject+predicate | 1 join | Yes | One B0 miss |
| Recovery (3,3,3) | `CLAIMED{reclaimed_from}` | 1 table | Yes | Nothing |
| Memory scope (4,4,4) | Scope chain (≤3 hops, `recall.cypher` `INHERITS*0..3`) | Scope list computed in Python in SQLite (`sqlite.py:352-360`) | Yes | Nothing |
| Episodes (3,3,3) | Count/lookup | 1 table | Yes | Nothing |
| Forgetting (4,4,4) | `DERIVED_FROM` cascade | **Depth 1 in the scenario** (fact→Source); C8 reaches depth 2 (`l1.py:933-943`) | Yes | Nothing |

Findings from the table:
- **9 of 10 families are ≤2-join scans.** The graph's one distinctive operator (variable-depth traversal) appears in one family, at depth
  ≤4, with 3 questions. The deepest lineage anywhere in the benchmark is 2 hops; the deepest dependency structure is C4's depth 5
  (`crucible/config.py:28`, layers 1-3-9-27-81, almost a tree, "a few diamonds" per `l1.py:433`).
- Even the Plexus answerer mostly **scans and filters in Python**: `_decision_rows` fetches all decisions then filters
  (`plexus_answerer.py:89-91`), `_handoff` fetches all handoffs (`:107-108`), `_fact` fetches all facts (`:142-146`). Only
  `tasks_downstream`, `facts_from_source`, and `facts_visible` use `*n..m` patterns. The Plexus arm is not exercising the graph much.
- The L2-scale gap (4 questions vs B1, p=0.125) comes from reader retrieval misses plus one reasoning slip. Hand-written SQL would not
  have either failure mode.

### 1.3 Diagnosis: three causes, ranked

| # | Cause | Evidence | Direction of bias |
|---|---|---|---|
| 1 | **The comparison is query-vs-reader, not graph-vs-SQL** | §1.1; L1 has the SQL arm and it ties (C4, C8 pass with 0 violations) | Flatters Plexus in L2 (unfairly), ties in L1 (fairly) |
| 2 | **Questions are shallow and sprint-scoped** | §1.2; every L2-scale question names its sprint and sprints don't interact (`BASELINE.md:214`, report §8.2) | Flatters baselines (BM25 on the sprint tag works) |
| 3 | **L1 baselines are competent** | flock + `os.replace`; `BEGIN IMMEDIATE` | Correct: claims, leases, and as-of are table stakes (report §6.2) |

**Verdict on "does the product offer nothing SQL can't?":** on L1/L2 as built, yes, nothing measured. The honest counterfactual (not run):
a `B1h` arm with the same 17 queries ported to SQL (a CTE for `tasks_downstream`, joins elsewhere) would score 43/43 and 36/36, and be
faster per call (in-process SQLite 0.1 ms claims, report §6.4). **I recommend running exactly that, cost $0 and about a day**, before a
reviewer does. It converts the main weakness into a stated result.

---

## 2. What I measured today (FalkorDB 6.0.2 vs SQLite, one machine, Docker Desktop) [measured]

Private container `falkordb/falkordb:6.0.2` on port 16379, default `TIMEOUT 1000` ms. SQLite 3 in-process (so client time for Cypher
includes about 10 ms of Docker-forward overhead; I quote **server-side** `run_time_ms` for Cypher where I can). Medians of 9-11 runs.
Queries in Appendix A. These are probes, not a pre-registered benchmark; single machine, one run.

### 2.1 Probe A: variable-length `*1..N` on a diamond-heavy dependency DAG

DAG: root + L layers of 6 tasks, each depending on 2 tasks of the layer below (so 2^L distinct paths, only 6L+1 distinct nodes).
Question: all tasks downstream of root (what `blocked_by_failure` asks).

| L (tasks) | Cypher `*1..L+1` + `DISTINCT` (server) | Cypher level-wise BFS from Python (`dependents_of`) | SQLite CTE `UNION` | SQLite CTE `UNION ALL` + depth bound |
|---|---|---|---|---|
| 8 (49) | 0.5 ms | 9 calls, 2.9 ms | 0.3 ms | 2 ms |
| 12 (73) | 4.7 ms | 13 calls, 5.2 ms | 0.2 ms | 61 ms |
| 16 (97) | **109 ms** | 17 calls, 8 ms | 0.3 ms | 727 ms |
| 20 (121) | **timeout (>1 s)** | 21 calls, 10 ms | 0.4 ms | interrupted at 3 s |
| 24 (145) | **timeout (>1 s)** | 25 calls, 20 ms | 0.5 ms | interrupted at 3 s |

Reading:
- **Cypher's variable-length match enumerates paths.** That is exactly why `relay/dependents_of.cypher:5-8` says the old `*1..10` query
  "enumerated every PATH and was exponential on layered DAGs", and why `Relay.blocked_by_failure` is a Python BFS issuing one query per level
  (`relay/service.py:369-389`). The same blow-up appears in SQL if you write `UNION ALL`; **SQLite's `UNION` dedups per iteration, so the
  recursion stays linear** (SQLite docs [1]: with `UNION`, a row is queued only if no identical row was queued before). A competent
  SQL author gets linear time for free; our Cypher needs a Python workaround.
- `l2/queries/l2/tasks_downstream.cypher:7` still uses `*1..20`. It is fine on the 12-task DAG and would time out on a layered DAG like Probe A. **Fix
  or replace it before any L6 run.**
- The 5 unrolled hops in `forget_source.cypher:14-29` and `quarantine.cypher:13-28` are the same workaround, hard-coding the depth cap at 5.

### 2.2 Probe B: lineage forest, "who read anything derived from source X"

Data: 1,001 sources, 131,110 facts in `DERIVED_FROM` trees of depth 4 (1,000 trees with fan-out 3 = 120 facts, one "hot" source with fan-out
10 = 11,110 facts), 262,220 `READ` edges from 262,220 steps by 100 agents. Query: distinct agents that read any fact within 4 hops of
the source (the poisoning blast radius).

| Variant | Normal source (120 facts) | Hot source (11,110 facts) |
|---|---|---|
| Cypher, natural form `(s:Source{id})<-[:DERIVED_FROM*1..4]-(f)<-[:READ]-(st)` | **timeout (>1 s)** | 905 ms |
| Cypher, level-wise with `UNWIND $ids` + `(:Fact {id:x})<-[:READ]-` (id from a variable) | 0.11-0.29 s server time per call; plan shows `Conditional Traverse` from an anonymous node then `Filter`, not an index seek; the 3-5 call chain exceeded the 1 s limit | n/a (timeout) |
| Cypher, anchored: `MATCH (s:Source{id:$id}) MATCH (s)<-[:DERIVED_FROM*1..4]-(f:Fact) WITH DISTINCT f MATCH (st:Step)-[:READ]->(f)` | **1.0 ms server (4.2 ms with client)** | **19.9 ms server (23 ms)** |
| SQLite CTE, default planner | 146-208 ms | 236-300 ms |
| SQLite CTE with `CROSS JOIN` order hint | **0.86 ms** | **56 ms** |

Reading:
- **Query planning dominates both engines, and the winner flips with how much effort each side got.** Default SQLite scanned the 262k-row
  `reads` table (even after `ANALYZE`); hinted, it is level with tuned Cypher on the small blast radius (0.9 ms vs 1.0 ms server-side) and 2.8x slower on the hot
  source (56 ms vs 19.9 ms). Naive Cypher times out. The repo already knows the Cypher side of this (P5 review notes in `forget_source.cypher:10-13`,
  `recall.cypher:17-22`).
- **Neither side shows an order-of-magnitude edge at 131k facts.** Both are milliseconds to tens of milliseconds when tuned. Latency
  is not where a graph can claim a win at our scale.
- `why` over depth 4 (single leaf to its source, with path): Cypher 1.9 ms, SQLite 0.01 ms [measured; includes client overhead for Cypher].
- Consequence for L6: **the baseline needs the same tuning budget** (EXPLAIN, index hints, `ANALYZE`) as the Cypher. An untuned SQL arm
  would "lose" for a reason a reviewer can reproduce in five minutes; an untuned Cypher arm would time out. Report both.

### 2.3 What the probes do not show
Single-node, 131k facts (not 10M), in-process vs networked, no concurrent load, no vector component. Postgres was not tried.
FalkorDB's own doc says unreferenced relationship aliases are checked only for existence [2], so some engine paths avoid
enumeration; my timeouts are for the query shapes above, on 6.0.2.

---

## 3. Which capabilities are structurally graph-shaped, and is a gap measurable?

"Gap" = Plexus vs a *competent* SQL arm (recursive CTE, tuned) unless stated. "Status quo" = flat files, BM25/vector reader.

| # | Capability | Graph formulation | What competent SQL / files needs | Cost at scale (depth d, fan-out f, N) | Measurable gap vs SQL | Gap vs status quo |
|---|---|---|---|---|---|---|
| A | **Transitive closure / blast radius of a poisoned source** (`DERIVED_FROM*`) | One expand; returns facts, readers, decisions, handoffs (`quarantine.cypher`) | Edge table + `WITH RECURSIVE ... UNION`, join to reads/decisions/handoffs. Needs `UNION` (not `UNION ALL`) and a join-order hint (§2) | Linear in edges touched; ms at 131k facts, hot source tens of ms (§2.2). Cypher `*n..m` is exponential on diamonds (§2.1); needs level-wise or a hard hop cap | **None on correctness; latency within ~3x, sign depends on tuning.** Cypher currently *worse* at diamond fan-in | **Large** once the lineage exceeds the context: a reader cannot enumerate 2,000 derived facts (and cannot output them), grep needs a script |
| B | **Why-chain, 3+ hops** (path with the intermediate nodes) | `nodes(p)` returns the path natively | Path-accumulating CTE (string/array concat). SQLite has no arrays, so a delimited string; Postgres arrays are fine | One chain: microseconds either way. Many chains: linear | **Ergonomic only** (a few lines of SQL). Not measurable as latency or accuracy | **Large when depth ≥ 4 and the reader must retrieve per hop** (multi-hop RAG: each hop is a retrieval that can miss; `BASELINE.md:267` is this failure at 2 hops) |
| C | **Hybrid vector + traversal in one query** | `db.idx.vector.queryNodes` then expand (`recall.cypher`). One round trip | pgvector/sqlite-vec top-k, then join on `entity_links`. Two statements or a CTE. Equivalent | Vector filter runs after top-k, so over-fetch loop (`recall.cypher:11-14`); same in sqlite-vec | **None in accuracy, small in round trips.** But: today the "expansion" is only to *sibling facts of the same entity* (`ABOUT`), which SQL does with one equi-join. No entity-to-entity relation exists, so no multi-hop retrieval | **Potentially large**, if answers sit 2+ relation hops from the query's entity and carry no lexical/semantic overlap with it (flat top-k cannot reach them). Needs product change P2 |
| D | **Multi-tenant graphs: isolation + parallelism** | One graph per tenant; writes parallel across graphs | SQLite file per tenant (`sqlite.py:112`, already the baseline); Postgres schema/DB per tenant | L4: Plexus 678→1,174 ops/s going 1→16 graphs; SQLite 1,103→500 (disk contention on this machine, report §6.4) | **Disputable.** The SQLite drop is an I/O artifact of 16 files on one disk; not structural. Postgres untested. Isolation (C5): tie | Large vs one shared file/table; same as any DB-per-tenant design |
| E | **Time travel over supersession chains** | Validity window + `SUPERSEDES` chain; `as_of` is a range predicate | Same columns; range predicate or SQL:2011-style versioning | Index seek | **None.** C6 tie; SQL is arguably the more natural fit | Large vs overwrite-in-place files only |
| F | **Dependency-aware claim + failure impact** | `OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d) WHERE d.status<>'done'` in one write (`claim_next_task.cypher:12-18`) | `NOT EXISTS (deps JOIN tasks ...)` in one `BEGIN IMMEDIATE` (`sqlite.py:535-541`) | **Plexus scans all open tasks per claim** (`MATCH (t:Task) WHERE status IN [...]`, no ready-flag). SQLite has `tasks_ready(status, priority, seq)` | Untested beyond M=500 tasks. At 100k open tasks **SQL is likely ahead** [inf] | Large vs flat JSON task list (`tasks.json` rewritten whole under a lock) |
| G | **Atomic provenance with the write** | Step/READ/WROTE links are written in statements *after* the tool's write (report §8.3) | `assert_fact` writes fact, links, step, reads in one transaction (`sqlite.py:262-318`) | n/a | **SQL wins, today**: crash between statements loses a lineage edge in Plexus, never in SQLite. Measurable: orphan rate after SIGKILL | Files also lose it |
| H | **In-DB graph algorithms** (PageRank, WCC, communities, shortest path) | `algo.*` | Export to Python/networkx; SQL has none natively | O(E) export per run | Latency of an export; **no accuracy gap** | Moot for flat files |

Summary:
- **A and B** are "graph-shaped" but SQL expresses them in one CTE. They give large gaps only against readers.
- **C** is the only item where the graph *shape* could change answer quality (retrieval that follows relations), but we don't build entity
  relations today, so the product currently delivers nothing there.
- **D, E, F** are ties or likely SQL wins. **G is a likely SQL win** and a documented product weakness.
- In **no row** is there a measurable accuracy or order-of-magnitude latency gap against a tuned recursive-CTE baseline on one node.

---

## 4. Proposed pre-registered L6

### 4.0 Design principles (so the result is believable)

1. **Arms** (every family runs the subset that applies):

| Arm | What it is | Role |
|---|---|---|
| **P** | Plexus, Cypher/tool call (no LLM) | Under test |
| **P-naive** | Plexus with the natural `*1..N` query (no tuning) | Shows the trap; reported, not hidden |
| **B1h** | SQLite, hand-written CTE/SQL per question, tuned (EXPLAIN, hints) | **Control for the "graph" claim.** Same author effort and spec as P; line counts reported |
| **B3h** | Postgres 17 + pgvector, hand-written | Optional; the real competitor for multi-host teams (SQLite can't be shared across hosts). The machine already runs Postgres 17 (`flyerhr-postgres`) but needs the pgvector image |
| **B1a** | SQLite with a read-only `sql` tool, driven by `claude -p` (Sonnet), same turn/token budget | "Realistic agent + SQL" |
| **B0g** | Files + `grep`/`jq`/Bash tool, `claude -p`, same budget | "Realistic agent + files" (can compute anything with a script) |
| **B0r / B2** | Existing one-shot readers under 32k (BM25 / vector top-12) | The L2-scale arms, kept for continuity |

2. **Ground truth is generated, not typed, and independent of every backend.** A seeded Python generator emits an event stream (DAG, lineage,
   reads, handoffs, supersessions, quarantine) and computes truth with plain BFS/sets over its own ledger (cross-check with networkx).
   Each backend replays the same stream; before any question, assert per-arm edge count and a hash of the sorted `(src,dst,kind)` list match
   the ledger. Plexus ids are random UUIDs, so truth is by label (as in `l2/scenario.py`).
3. **Answer-size control.** Readers cannot output 2,000 ids. Questions ask for a **count + 10 yes/no membership probes + top-5 earliest**,
   scored exactly. Otherwise the gap is an output-length artifact.
4. **Tuning budget parity.** Every SQL and Cypher query gets EXPLAIN/PROFILE review; plans recorded. Report P-naive and an untuned SQL arm
   as sensitivity rows.
5. **Latency fairness.** Report server-side time and end-to-end. Label SQLite "embedded" and FalkorDB/Postgres "server"; put B1h behind the
   same thin HTTP service for the e2e column.
6. **Statistics.** Exact paired sign test (as in L2-scale). **Minimum 6 discordant questions all one way for p=0.031; 5-0 gives 0.063.**
   So n must satisfy n × (baseline error) ≥ 6; design families so the weakest baseline errs on ≥ 30%, with n ≥ 24 per family, 3 reps for
   LLM arms (majority per question). L2-scale's 36 questions at 11% baseline error could not reach significance by construction.
7. **Pre-register, with predicted ties.** Commit hypotheses (including "P = B1h on accuracy") and decision rules before the first LLM call.
   Dry-run all deterministic arms first ($0).
8. **Cost.** Deterministic arms ($0): P, P-naive, B1h, B3h. LLM arms: 5 families × 24 q × 3 arms × 2 reps ≈ 720 calls; with tool loops at
   about $0.10-0.20 each that is $70-140 notional. Too much for the deadline: **run LLM arms on a 8-question pilot per family (≈ $20)** and
   keep the full run for the deterministic arms.

### 4.1 The families

#### L6-A Deep blast radius, with diamonds (`DERIVED_FROM` depth d ∈ {2,4,8,12}, fan-in 1-3)
- **Generator:** 20k-200k facts, depth up to 12, facts derived from 1-3 parents (so path count ≫ node count), steps/reads by 100 agents,
  decisions `BASED_ON`, handoffs `CARRIES`. 24 poisoned-source questions across blast sizes 10/100/1,000/5,000 facts.
- **Questions:** "How many facts / distinct agents / decisions / handoffs are affected by poisoning source S?" (counts) + 10 membership probes.
- **Arms:** P (level-wise or anchored), P-naive, B1h, B1a, B0g, B0r.
- **Metrics:** exact count, probe accuracy, p50/p99 latency (deterministic arms), tool calls, tokens (LLM arms).
- **Expected:** P = B1h on accuracy (both 100%). Latency within ~3x, sign uncertain. **P-naive times out beyond d ≈ 16** (§2.1).
  B0r/B2 fail beyond context (count off by >10% for blast ≥ 1,000). B0g ≈ 100% if the agent writes a script, with more tokens.
- **Honest headline:** "structured lineage answers blast-radius queries at 5k facts in tens of ms; a reader cannot; SQL matches Plexus."
- **Failure risks:** our own Cypher is the weak side (fix first, P1 in §5); depth cap of 5 hops in `forget_source` truncates at d=8, 12 (this
  is a *bug-class* finding: report it); hot-source query ~20-60 ms either way.

#### L6-B Why-chain depth sweep (decision → fact → fact → … → source, depth d ∈ {2,3,4,6,8,12})
- **Generator:** chains with 3 distractor parents per level; near-twin chains (same text, different sprint) to defeat lexical shortcuts.
- **Question:** "Give the ordered chain of fact ids from decision D to its root source" and "which agent asserted the d-th ancestor?".
- **Arms:** P (`why` path), B1h (path CTE), B1a, B0g, B0r, B2.
- **Metrics:** exact ordered-chain match vs d, calls, tokens.
- **Expected:** P = B1h = 100% at all d. B1a 70-100% (agent must write a path CTE; failure modes: cycles, `UNION ALL`). B0g declines with d (one grep
  per hop). B0r/B2 collapse for d ≥ 4 [inf]. Gap vs readers large; vs B1h zero.
- **Failure risk:** `lineage/why_edges.cypher:61-91` caps `DERIVED_FROM` at `*1..3`. At d>3 Plexus **fails its own question**. Either raise the cap (cost
  analysis in §2.1) or report the cap honestly as a limit.

#### L6-C Multi-hop associative recall under a fixed budget (needs product change P2)
- **Generator:** an entity graph (services, modules, owners, policies) with typed relations; 50k facts, 5k entities. Each question names entity E1; the answer fact is attached
  to E2/E3 reachable by 2-3 typed relations, with **no lexical or embedding overlap** with the query. Distractors: near-twin facts on lexically closer entities (the L5b lesson).
- **Arms:** P (`recall(hops=2)`), B1h (join over `entity_links`, control), B3h (pgvector + join), vector top-k, BM25, B1a.
- **Metrics:** evidence recall@k (k=5,10), answer EM from the retrieved set (deterministic extraction, no LLM), chars returned.
- **Expected:** P = B1h = B3h ≈ 90-100%; BM25/vector top-k ≤ 30% [inf]. Gap vs flat retrieval is large and *is the multi-hop retrieval literature's usual claim* [inf, not verified here]; gap vs SQL join is zero.
- **Failure risks:** (1) the relations are oracle-quality here; real extraction is noisy, so the headline is "given good edges". State it. (2) If P2 isn't built, don't run C.
  (3) Vector post-filter (`recall.cypher:11-14`) can starve the seed set.

#### L6-D Cross-project / cross-sprint aggregation (the gap the report names, §8.2, §9.1)
- **Generator:** the L2-scale scenario at 200 sprints (about 10x current, 5M+ chars), sprint **not named** in the question.
- **Questions (aggregate, count + top-5 + probes):** "Across all sprints, how many decisions relied on a fact later superseded?", "Which agent asserted the most facts later forgotten?", "Which sources are cited by decisions in more than 10 sprints?"
- **Arms:** P, B1h (GROUP BY), B1a, B0g (jq/python over JSONL), B0r, B2.
- **Expected:** B0r/B2 ≈ 0-20% (aggregate needs every sprint); P = B1h = 100%; **B1a and B0g ≈ 90-100%** (an agent with a shell can aggregate JSONL). The strongest honest sentence:
  "tool-less readers cannot aggregate; any queryable store can; Plexus is one."
- **Failure risk / design conflict:** graph-per-tenant (C5 isolation, report §2.4) makes cross-*tenant* queries impossible by design.
  Model projects as `Scope` nodes inside one team graph for this family, and say that the isolation boundary is then the team, not the project.

#### L6-E Consistent reads under concurrent writes (multi-hop snapshot)
- **Setup:** 8 writers appending lineage + quarantining sources while 8 readers run blast-radius queries; 10 seeded runs; 100 k lineage edges.
- **Invariants checked per read (no LLM):** every `Decision` in the answer has all its `BASED_ON` facts present; quarantine is all-or-nothing (no half-quarantined subtree); blast-radius
  count ≥ the count at the read's start.
- **Arms:** P, B1h (single-statement CTE; also multi-statement without `BEGIN`, as a naïve client would), B0 (files), B3h.
- **Expected:** P and B1h (single statement) 0 violations; multi-statement SQL without a read transaction and B0 show violations (torn view across `tasks.json`/`decisions.jsonl`, `files.py:15`).
  Honest framing: "snapshot reads are free in FalkorDB and in SQLite WAL if you use one statement; files give none".

#### L6-F Provenance crash-consistency (expected **Plexus loss**, include anyway)
- **Setup:** SIGKILL a writer at a random point inside `assert_fact`/`record_decision`/`handoff` (the C2 harness machinery), 200 kills per arm; afterwards count facts/decisions
  **without** their `Step`/`READ`/`WROTE` links.
- **Expected:** B1h 0 (one transaction, `sqlite.py:262-318`), P > 0 (documented, report §8.3), B0 > 0. Pre-register this as "P expected to lose".
- **Why include:** it is the only axis where the claim "graph is better" is plausibly *reversed*, and the fix (P1 in §5) is concrete. Showing loss → fix → tie is a stronger story than silence.

(L6-H, optional: tenant fan-out, create/fork/drop 1,000 tenant graphs vs 1,000 SQLite files / Postgres schemas; memory per idle tenant; leak probes at 1,000 tenants. Expected tie; run only if time allows.)

### 4.2 Summary of expected outcomes (to be pre-registered, so a tie is a pass)

| Family | P vs B1h (graph effect) | P vs B1a/B0g (agent with tools) | P vs B0r/B2 (status quo) |
|---|---|---|---|
| A blast radius | tie accuracy; latency within ~3x | tie / fewer tokens | **large** |
| B why-chain depth | tie (P fails past `*1..3` unless fixed) | P ≥ B1a | **large** at d ≥ 4 |
| C multi-hop recall | tie | n/a | **large** (needs P2) |
| D cross-project | tie | tie | **large** |
| E consistent reads | tie | n/a | vs files: large |
| F crash consistency | **B1h wins** | n/a | P ≥ files |

---

## 5. Product changes that would widen a real gap

Effort: **S** < ½ day, **M** ~1 day, **L** 2+ days, assuming subagent-driven work with owner review (the deadline is Oct 18 20:00 NPT).

| # | Change | Why it matters | Gap it creates | Effort | Risk |
|---|---|---|---|---|---|
| P1 | **Fix variable-depth traversal**: replace `tasks_downstream.cypher:7`, `why_edges.cypher` `*1..3`, and the 5-hop unrolls with an anchored, distinct-node expansion (Probe B form) or level-wise; remove hard caps or make them parameters; add a diamond-DAG regression test | Today Plexus times out on a 145-task diamond DAG (§2.1) and truncates lineage at 3-5 hops | Removes a *self-inflicted loss* in L6-A/B. Does not create a win over SQL | M | FalkorDB planner quirks (report §6.9 item 7) |
| P2 | **Typed entity relations + `recall(hops=2)`**: `assert_relation(a, kind, b)` creating `(Entity)-[:RELATES {kind}]->(Entity)`, recall expands seeds' entities N hops, ranks by distance; bounded output | The only change that lets graph *shape* improve retrieval; today expansion is a same-entity join | L6-C: large vs flat top-k; zero vs SQL join. Also gives a real "hybrid vector+traversal" claim | L (schema, `recall.cypher`, tool, tests, benchmark) | Edges are only as good as agents' writes (no LLM in Plexus). The L3 pilot shows richer results cost tokens (+75%, report §6.7), so cap output |
| P3 | **Atomic provenance**: fold `link_step`/READ/WROTE into the write statement (report §9.5) | Closes the one documented SQL advantage (L6-F) | Turns a loss into a tie | M-L | Planner bugs in long statements (report §6.9) |
| P4 | **`impact` tool**: one call returns blast radius of a Source / Fact / Task (facts, readers, decisions, handoffs, blocked tasks) as counts + capped list | Agents currently need `quarantine` (a write) to learn the blast radius, or 3 calls. A read-only dry-run is safer and cheaper | Fewer calls/tokens vs B1a/B0g (measurable in L6-A) | M | Must be bounded |
| P5 | **Compact why-path in `recall` by default** (`derived_from` already returns ids, `recall.cypher` final `RETURN`; add a one-line path string and rank explanation) with a `detail` switch | Agent needs fewer follow-up `why` calls (calls/question is measurable). But read §Risk | Calls and tokens vs B1a/B0g, not vs SQL-as-a-store | S-M | **L3 showed Plexus agents spent 75% more tokens on richer tool output**; gate the default on a measured token budget |
| P6 | **Failure propagation + critical-path claiming**: `fail_task` marks transitive dependents `blocked` (today a failed dep "blocks forever" silently, `claim_next_task.cypher:8`; `fail_task.cypher` touches only the task); claim ordering by downstream weight (maintained counter) | Team stalls are invisible today. Critical-path priority shortens makespan | Measurable in a discrete-event simulation (K workers, durations): makespan vs FIFO-priority. SQL can do it too, so it's a feature gap, not an engine gap | M | A counter must be maintained transactionally |
| P7 | **Ready-queue index**: keep a `ready` flag updated on `complete_task`, so claim stops scanning all open tasks (`claim_next_task.cypher:12-18`) | Removes a likely SQL win at N=100k tasks (§3 F) | Parity at scale | S-M | Flag drift; keep the old query as fallback in tests |
| P8 | **Cross-project reads**: `Project` as `Scope` inside the team graph + a read-only aggregate tool; keep tenant graphs as the isolation unit | Enables L6-D and the §9.1 questions | Aggregation without per-sprint naming | L | Weakens "graph per project" isolation; document |
| P9 | **Postgres+pgvector arm** (`B3h`) | A reviewer's first question; multi-host teams can't use SQLite | Credibility, not a gap | M | May beat Plexus on claim throughput (`SKIP LOCKED`) |

Order if time is short: **P1 → B1h arm → L6-A/B deterministic → P3 → L6-F → (P2 + L6-C only if >1.5 days remain)**. P1 is a bug fix with a demonstrable
before/after, and everything in L6 depends on it.

---

## 6. Honest verdict: what to claim, what not to

### 6.1 Claims the evidence supports now [repo]
- Every feature is a graph read or write on FalkorDB, and removing the four edge types breaks 7 of 7 edge-dependent capabilities while 5 of 5
  controls survive (ablation, report §3.4). **Caveat to state alongside:** the SQLite backend keeps the same links in an edge table
  (`sqlite.py:81-83`), so this shows "edges matter", not "FalkorDB specifically".
- A deterministic provenance query beats an LLM reading a capped dump at 10-17x history: 36/36 vs 32/36 and 30/36, **at 0 tokens and 7.5 ms vs
  about 20k tokens and 5 s per question**; gap vs B1 not significant (p=0.125). The robust win is **cost, latency and determinism**.
- L1 correctness ties with competent baselines; we say so. SQLite is faster on single claims; Plexus's p99 is lower than SQLite's at 200 workers
  (1.86 s vs 2.18 s) and tenant spreading scales +73% in our setup.
- The Staleness (L5a) and forgetting (L5b) results are honest, pre-registered, and include a failed first run.

### 6.2 Claims to avoid
| Do not say | Because |
|---|---|
| "Plexus beats SQL" / "a graph beats a relational DB" | No SQL query was ever run in L2; L1 ties; §2 shows SQL ahead or level on traversal |
| "SQLite answered 32/36 / 30/36" without "reading a dump, no tools" | The B1 arm is a one-shot reader (`l2/contexts.py:7`) |
| "Faster" (except cost/latency vs LLM readers) | L4: SQLite faster at every worker count on median claim |
| "Handles deep lineage / arbitrary-depth blast radius" | Caps: `*1..3` in `why`, 5 hops in forget/quarantine; `*1..N` times out on diamond DAGs |
| "Multi-hop retrieval" | Expansion is a same-entity sibling join today |
| "Atomic provenance" | Report §8.3: links are written after the memory write |
| "Better than Mem0/Graphiti/Letta" | Not benchmarked against them |

### 6.3 Suggested submission sentence
> "Plexus makes provenance, dependencies and time first-class edges in FalkorDB, so *why*, *who knew* and *what is affected* are single
> deterministic queries (zero tokens, milliseconds). Against flat files and tool-less LLM readers that is a large cost and latency win,
> and a measurable accuracy win once histories exceed the context. A well-built relational schema with recursive CTEs matches Plexus on correctness
> and is faster on simple claims; we publish that tie, the benchmark, and the cases where we lose."

### 6.4 What "tackling it" realistically means by Oct 18
1. (~1 day, $0) `B1h`: port the 17 L2 queries to SQL on the existing SQLite backend; add rows to L2 and L2-scale. Expected tie. **Do this first.**
2. (~½ day) P1 + a diamond-DAG regression test; re-run Probe A/B inside the benchmark as L6-A deterministic.
3. (~1 day, $0) L6-A, L6-B deterministic arms (P, P-naive, B1h); LLM pilot of 8 questions/family for B0r/B1a/B0g (~$20).
4. If time: P3 + L6-F (turn the likely loss into a story).
5. Skip P2/L6-C, P8/L6-D unless the above is done; both need new product surface and a pre-registration, and neither is required to submit honestly.

If only one thing is done, do (1): it answers the question every informed reviewer will ask, and the answer is cheap to give.

---

## Appendix A: the probe queries (so they can be re-run)

Scripts: `C:\Users\ACER\AppData\Local\hermes\cache\scratch\probe_a.py`, `probe_b2.py`, `probe_dbg2.py` (scratch is pruned after 24 h; copy
if wanted). Container: `docker run -d -p 127.0.0.1:16379:6379 falkordb/falkordb:6.0.2`.

```cypher
-- A: path-enumerating (times out at L>=20)        -- A': Plexus workaround, one call per level
MATCH (t:Task)-[:DEPENDS_ON*1..L]->(:Task {id:'root'})   UNWIND $frontier AS fid
RETURN DISTINCT t.id                                     MATCH (:Task {id:fid})<-[:DEPENDS_ON]-(x:Task) RETURN DISTINCT x.id
-- B anchored (1.0 ms server normal / 19.9 ms hot source)
MATCH (s:Source {id:$id}) MATCH (s)<-[:DERIVED_FROM*1..4]-(f:Fact) WITH DISTINCT f
MATCH (st:Step)-[:READ]->(f) RETURN DISTINCT st.agent_id
```
```sql
-- SQLite: UNION dedups per iteration (linear); hint the join order or the default plan scans reads
WITH RECURSIVE d(id) AS (SELECT src FROM links WHERE dst=? AND kind='derived_from'
  UNION SELECT l.src FROM links l JOIN d ON l.dst=d.id WHERE l.kind='derived_from')
SELECT DISTINCT s.agent FROM d CROSS JOIN reads r ON r.fact=d.id JOIN steps s ON s.id=r.step;
```
Indexes used: `links(dst,kind)`, `links(src,kind)`, `reads(fact)`, `steps(id)`; Cypher `INDEX FOR (n:Source|Fact|Step) ON (n.id)`. One bug note: my first
"unrolled 4 hops" variant returned 0 rows (a grouping error), so I do not report its timing.

## Appendix B: references

[1] SQLite, "WITH clause": recursive CTE queue semantics; "UNION is used instead of UNION ALL to prevent the recursion from entering an infinite loop if the graph contains cycles". https://www.sqlite.org/lang_with.html (quote in ledger)
[2] FalkorDB, known limitations: unreferenced relationship aliases are only checked for existence. https://docs.falkordb.com/cypher/known-limitations.html
[3] FalkorDB, concurrency design: write queries are atomic, parallel reads. https://docs.falkordb.com/design/concurrency
[4] MAPLE-Guard (poisoned shared-memory write contaminates agents that never saw the attack; gating cut attack success 38.2%→0.9%). https://arxiv.org/html/2608.00426v1 (as summarised in `docs/research/landscape/3-coordination.md` §3; abstract-level only)
[5] MAST failure taxonomy (Cemri et al.). https://arxiv.org/abs/2503.13657
[6] Memory-consistency position paper. https://arxiv.org/html/2603.10062
[7] Letta, plain-file agent reaching 74.0% on LoCoMo (evidence that file + tools baselines are strong). https://letta.com/blog/benchmarking-ai-agent-memory (via `landscape/2-memory-layers.md`)
