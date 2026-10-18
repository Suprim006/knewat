# Product fixes analysis: read-path audit, duplicate detection, entity resolution

> **STALE (2026-10-18):** the numbers in this document were measured on builds before the current main (7618d18) and are not valid for it until re-run. Build per number: [docs/NUMBERS_STATUS.md](../NUMBERS_STATUS.md).

Scope: the three shortcomings listed in `docs/PLEXUS_REPORT.md` §8.3 (lines 689-697). Design only: nothing in the repo was
changed except this file. Paths are relative to `plexus/` unless they start with `deploy/` or `docs/`.
All behaviour claims about FalkorDB are for **6.0.2**. "Verified" means I ran it in a throwaway container
(`falkordb/falkordb:6.0.2`, own port, deleted afterwards); "unverified" means reasoning only. The probe scripts are
outside the repo (`C:/Users/ACER/AppData/Local/hermes/cache/scratch/pf_race_probe*.py`, `pf_b_probe*.py`); copy them into
`tests/` when implementing.

## 0. Summary of findings and recommendations

| | Finding | Recommendation |
|---|---|---|
| A | A `recall` is **3 serialised writes** (`record_step`, `record_recall`, `record_tool_call`) behind the per-graph write queue; every other read tool is 2 writes (Step + ToolCall). Only `recall` produces provenance that anything reads (READ/Recall). | **(i) audit classes, per tenant and per tool**, enforced server-side; `off` for demo/observer tenants (lets `deploy/guard.py` allow reads), `light` (1 write, no Step) for meta-reads, `full` unchanged for `recall` in write tenants. Batching (ii) is an optional later layer for `light` rows only. |
| B | The claim "never wrongly merged" holds only for the 4 controls in C7. **Measured: the current rule would auto-merge negations, antonyms, quantifiers, number words and unit changes in sentence-length values** (§B.1). Recall misses are 3 of 4 *heavy* pairs. | Fix **precision first** (discriminator-token equality, unit/number-word normalisation), then add a lexical-corroborated second tier and a `DUPLICATES_MAYBE` soft link with a confirm tool. Extended labelled C7 with a frozen test split. |
| C | The race is real (**reproduced: 2 Entities from 50 racers**). Putting lookup + create into **one write statement is race-free** (**verified: 1 Entity in 20/20 runs of 50 racers, 2 spellings**), because writes are serialised per graph. | **(i) one atomic resolve-or-create statement** + UNIQUE(`Entity.norm_name`) as backstop; SAME_AS alias edges only as the bridge for legacy duplicates. |

Suggested order: **B0 (precision guards) → C → A → B1-B3**. Total effort about 17-19 engineer-days (§E).

---

## A. "Every tool call writes"

### A.1 What actually happens (evidence)

`Runtime.call` (`mcp/runtime.py:165-184`) takes a per-(tenant, agent) lock, runs the tool in a thread, then `_run`
(`:186-222`) always does, in order:

| Step | Code | Write? | For a read tool |
|---|---|---|---|
| tool body (`ts.scope_id(create=False)`, queries) | `tools_engram.py:178-189` | no (`ro`) | pure reads |
| open Step | `runtime.py:192` -> `lineage_hook.py:40-59` -> `queries/lineage/record_step.cypher:8-21` | **rw** (MERGE Agent, scans all of the agent's Steps for `max(n)`, CREATE Step + NEXT) | yes, every call |
| attach READ/WROTE | `lineage_hook.py:63-80` | rw only if ids are non-empty | skipped for reads (`read_ids` is empty) |
| `Outcome.after` hook | `tools_engram.py:195-198` -> `lineage/service.py:172-220` -> `record_recall.cypher:12-35` | **rw** (Recall + BY + IN_STEP + k x RETURNED + k x READ MERGE) | `recall` only |
| ToolCall | `runtime.py:202-214` -> `audit/recorder.py:70-90` -> `record_tool_call.cypher:103-131` | **rw** (ToolCall + IN_STEP, and a 16-way OPTIONAL MATCH over labels) | yes, every call |

So: `recall` = 3 writes; `why`, `why_recalled`, `who_knew`, `knew_at`, `as_of`, `fact_history`, `ready_tasks`, `task_status`,
`blocked_by_failure`, `best_procedure`, `memory_strength`, `facts_to_verify`, `docs_to_update` = 2 writes each.
All of them queue behind every real writer of that tenant graph (FIFO, `FALKORDB_REFERENCE.md` §1). Consequences already
documented: `deploy/guard.py:5-8` and `:278-282` refuse **every** `tools/call` on `demo*` tenants (`_demo_refusal`,
`:376-387`); `docs/BASELINE.md:172` says P-mcp's Step + ToolCall writes cost 2-3x at 1-50 workers.

Two more effects that the report does not state:
1. **A read mutates ranking.** `record_recall.cypher:28-34` writes `READ {via:'recall'}`, which the activation model weighs 0.3
   (`docs/graph-model.md:205`). A visitor poking a public tenant would change which facts rank higher. Reads on observer
   tenants must be side-effect free for this reason too, not only to keep the graph unchanged.
2. **Meta-reads pollute the step chain.** `who_knew` / `why` open a Step for the agent, so "what did X know at step N"
   (`knew_at.cypher:7-25`) counts steps spent asking provenance questions. Hypothesis (unmeasured): `record_step` is
   O(agent's steps) because `ORDER BY p.n DESC LIMIT 1` has no index-ordered scan (`falkordb-plan-shape-tests` item 6b), so it
   gets slower as an agent ages. Measure before relying on it (A.6).

What provenance depends on what:

| Query | Needs | Source |
|---|---|---|
| `why_recalled` | `Recall` + `RETURNED` | `why_recalled.cypher:6-16` |
| `who_knew` | `Step-[READ]->Fact` (+ `Recall` via `IN_STEP`) | `who_knew.cypher:6-13` |
| `knew_at` | `READ` edges of Steps `n <= N` | `knew_at.cypher:7-25` |
| blast radius of a poisoned source (`quarantine`) | who was *exposed* (READ via recall), not only who used | `lineage/service.py:288-346` |
| activation / forgetting | `READ.via`, `READ.at` | `graph-model.md:205-206` |
| View flow feed | `ToolCall` nodes | `queries/view/flow.cypher:7` |

Only `recall` creates exposure provenance. Everything else is audit/observability of meta-queries.

### A.2 Options

**(i) Audit modes `off | light | full`** (per tenant policy, per tool class; optional per-session header).
- `off`: 0 writes. No ToolCall, no Step, no Recall, no READ. Result has `tool_call_id: null`, `recall_id: null`.
- `light`: 1 write: a `ToolCall {wrote:false}` only (no Step, no IN_STEP, no READ, no Recall).
- `full`: today.
- Lost: `off` loses everything; `light` loses who_knew/knew_at/why_recalled for those calls (fine for meta-reads, wrong for `recall`).
- Concurrency: per read call 3 -> 1 (light) or 0 (off) entries in the write queue. `off` never touches the queue.
- Guard: `off` is what makes read-only public tenants possible (A.4).

**(ii) Batched async audit** (bounded queue, one `UNWIND` write per tenant per flush).
- Keep everything (Step, Recall, READ, ToolCall) but defer it. N calls -> 1 write per flush (e.g. 50 ms or 100 calls).
- At-least-once needs: client-generated ids (ToolCall/Recall/Step ids are already `new_id()` before the write, `recorder.py:72`)
  and `MERGE` on id instead of `CREATE`, plus a durable spool (append-only JSONL, fsync per batch, replay at start). An in-memory
  queue alone is at-most-once on a crash. Bounded queue: when full, drop `light` rows first and count `audit_dropped`; never block a read.
- Order: one consumer per tenant, FIFO, enqueue **inside** `_agent_lock` (`runtime.py:144-163`), so `Step.n` and `at` still agree.
  `at` must be the call start (`started`, `:298`), already passed explicitly.
- New problems: read-your-writes. `recall` returns `recall_id`, and the next call may be `why_recalled(recall_id)`: it must flush
  first (a barrier) or answer "pending". A large batch holds the per-graph write lock longer; cap edges per batch (about 1 000)
  because write timeouts are unreliable (`FALKORDB_REFERENCE.md` §2 #12).
- Guard: does not help. It still writes, so `demo` stays refused.

**(iii) Lazy provenance** (write Recall/READ only when the agent later *uses* a fact).
- Server keeps the last N recalls per agent in memory; a write tool that names fact ids (decision `based_on_fact_ids`,
  `assert_fact` duplicate/supersede, `verify_fact`, `pin_fact`) materialises `Recall` + `READ {via:'use'}` in that statement.
  A signed client-side token (HMAC of query/scope/ids/ranks, up to ~3 KB) removes the server memory but adds ~3 KB to the model's
  context per recall, and an unmodified Claude Code (D-002) will not reliably pass it back.
- Lost: **exposure**. Facts shown but not acted on leave no trace, so `who_knew` and the quarantine blast radius shrink to "users".
  `via:'recall'` READs disappear, which also changes forgetting (0.3-weight signal).
- Concurrency: reads cost 0 writes; the use-time write gains a few edges in a statement that exists anyway.
- Guard: read-only tenants work. State is process-local (breaks with more than one MCP process or a restart).

**(iv) Observer tenants** (a tenant class with no write path).
- `demo` / `demo_*` bound to `ReadOnlyClient` semantics: no `rw`, no audit, no Step. Visitor reads are not agents of the team.
  Optionally serve a `GRAPH.COPY` snapshot so the live graph is never touched.
- Lost: provenance of observer reads (intended). Nothing is lost for team tenants.
- Concurrency: observers add only reads; they never join the write queue.
- Guard: this is the policy the guard needs. It is a subset of (i) (`off` + forced read-only).

### A.3 Recommendation: (i), with (iv) as its enforcement for public tenants

(i) is the only option that keeps `full` provenance exactly where it has value (exposure by `recall` in write tenants) and
removes the cost where it has none. (iv) is just "tenant policy = off, writes refused", so it falls out of (i). (iii) loses
exposure provenance, which is the Lineage selling point. (ii) is worth doing later only for `light` rows (observability, so
at-most-once is acceptable there) and is not needed to unblock the demo.

**Policy table** (`mcp/policy.py`, new):

| Tenant class | Read tools classed `exposure` (`recall`) | Read tools classed `meta` | Write tools |
|---|---|---|---|
| `team_*` (default) | full | light | full (unchanged) |
| `demo`, `demo_*` (observer) | off | off | **refused** |
| header `X-Plexus-Audit: light` on a team session | light | light | full (a header may only lower read cost, never writes) |

Design details:
1. `ToolDef` (`mcp/toolkit.py:37-41`) gains `kind: Literal['write','exposure','meta'] = 'write'`. `@tool.read(kind='meta')` marks a read tool.
   Unmarked tools stay `write`/full, so a forgotten annotation is safe.
2. **Server-side verification, not trust.** `MeteredClient.writes` (`metering.py:17-23, 33-44`) already records every rw query. In
   `Runtime._run`: a tool marked read that produced `m.writes != []` is a bug -> log and force `full` for that call.
   For observer tenants wrap the client so `rw` raises (`ObserverClient`, same idea as the API's `ReadOnlyClient`,
   `api/context.py:32`), so a mislabelled tool fails closed instead of writing.
3. `Runtime.call` resolves `effective = policy.audit(tenant, tool_def, header)` before `_execute`, then:
   - `off`: skip `_open_step`, `_attach`, `after`, and `record_tool_call`; return data with nulls.
   - `light`: skip `_open_step`/`_attach`/`after`; call `record_tool_call(step_id=None, wrote=False)` (the cypher already accepts `step_id ''`, `record_tool_call.cypher:102`).
4. `recall` under `light/off` still returns hits, plus `recall_id: null`. `why_recalled` then answers "no record" instead of failing.
5. Observer graph must never be created by a visitor: `Runtime.state` (`runtime.py:106-142`) calls `apply_schema` for an unknown tenant, and
   `DEMO_RE = demo(_[a-z0-9_]*)?` (`guard.py:37`) accepts unlimited names. With reads allowed, `/mcp/t/demo_x1` would create a graph
   per name and the 50-graph cap only covers `team_*` (`guard.py:335-351`). The observer policy must therefore refuse unless the graph
   already exists (`view/indexes` probe, `runtime.py:251-255`), or restrict to an explicit allowlist (env `PLEXUS_OBSERVER_TENANTS`).

### A.4 How `deploy/guard.py` allows public read-only tenants

Today: `PublicGuard.__call__` reads the body for `kind == 'demo'` and `_demo_refusal` (`:376-387`) answers every `tools/call` with `READ_ONLY_MESSAGE`.
Change (still no Plexus imports, so the file stays unit-testable, `guard.py:15`):
```python
OBSERVER_TOOLS = frozenset({"recall", "fact_history", "as_of", "why", "why_recalled", "who_knew", "knew_at",
                            "ready_tasks", "task_status", "blocked_by_failure", "best_procedure", "memory_strength",
                            "facts_to_verify", "docs_to_update"})      # memory_sweep stays out: dry_run is an argument
...
if msg.get("method") == "tools/call":
    name = (msg.get("params") or {}).get("name")
    if name not in OBSERVER_TOOLS:
        return 200, _tool_error(msg.get("id"), READ_ONLY_MESSAGE)   # reword: "writes are disabled; reads are allowed"
    # else forward: Runtime applies policy 'observer' (off + rw refused) regardless of what the guard did
```
- The allowlist is a second gate only; the Runtime policy is the real one (defence in depth). A test asserts
  `OBSERVER_TOOLS == {d.name for d in all_tool_defs if d.kind != 'write'}` so the two lists cannot drift.
- Keep JSON-RPC batch refusal (`:383-384`) and the per-IP bucket (`:59-60`). A public `recall` costs an embedding (about 47/s shared,
  `BASELINE.md:171`), so the global 600/min bucket is the DoS ceiling; consider a separate smaller `demo` bucket.
- Optional DB-level seatbelt: the guard's Redis user for demo graphs with `%R~plexus_t_demo*` (read-only key pattern,
  `FALKORDB_REFERENCE.md` §1 Security). Unverified on 6.0.2 for `GRAPH.RO_QUERY`: probe first.

### A.5 Concurrency implications (summary)
- `off`/`light` shrink the write queue share of reads from 3 (or 2) to 0/1 per call. Gains show for mixed read/write tenants and
  at low worker counts; at 100-200 workers `recall` is embedder-bound (`BASELINE.md:171-172`), so expect no throughput change there.
- Per-agent ordering (`_agent_lock`) is unchanged. `light` calls take no step number, so the agent's `n` sequence only counts
  calls that have a Step (writes and `recall` in full mode). Document it in `docs/mcp.md` "Steps and provenance".
- Mode must be decided **before** the tool body, but verified after (A.3 item 2), so no race on the `wrote` flag.

### A.6 Test plan
1. Unit (`deploy/tests/test_guard.py` style): demo + allowlisted tool -> forwarded; demo + `assert_fact` -> refused with 200 tool error;
   demo + batch -> 400; `demo_new` with no graph -> refused and `list_graphs` unchanged.
2. Integration, seeded observer tenant, run every `OBSERVER_TOOLS` tool: node/edge counts per label/type identical before/after,
   and Redis `INFO commandstats` shows `cmdstat_graph.query` delta 0 (only `graph.ro_query` grew). That is a deterministic "no write" proof.
3. Meta-test over the tool registry: every `kind != 'write'` tool runs under a client that raises on `rw`; a mislabelled tool fails the test.
4. Modes: `full` regression = existing `tests/mcp/test_lineage_hook.py` and `tests/lineage/*`; `light` = ToolCall exists, no Step/Recall/READ;
   `off` = none of them and `tool_call_id is None`; `recall` in `off` does not change `activation` of its hits (rank before == after).
5. Perf (Crucible L4 recall + claim mix, 1/10/50 workers, 3 runs): P-mcp `full` vs `light` vs `off`; report server `run_time_ms`
   and write-queue wait (client latency minus server time). Also time `record_step` at 10, 1 000, 10 000 steps for one agent.
6. Header clamp: `X-Plexus-Audit: off` on a team tenant behaves as `light` (floor), and never affects write tools.

---

## B. Duplicate detection

### B.1 What the code does and what it gets wrong

Rule (`engram/service.py:313-315`, `assert_fact.cypher:47-49`): duplicate iff `norm_value` equal, or `value_tokens` equal
**and** `cosineDistance(value_embedding) <= 0.08` (`FACT_DUP`, `service.py:30`). `normalize` is casefold + whitespace only (`common.py:25-27`):
punctuation is *not* stripped, so "owns it." vs "owns it" is caught by the embedding, not by equality. `value_tokens` is digits only (`service.py:44, 55-68`).
Candidates are already entity + predicate + scope scoped (`assert_fact.cypher:40-42`).

**Measured with the real fastembed model** (cos = cosine distance, `stopJ` = Jaccard of stemmed, stop-word-free token sets):

*Baseline C7 corpus (`crucible/l1.py:769-837`)*: punctuation 3/3 and light 5/5 caught, heavy **1/4 caught** (= 3 of 12 = the 25% miss, `BASELINE.md:145-147`).

| Pair (missed heavy / controls) | cos | stopJ | numeric tokens equal |
|---|---|---|---|
| deploys need two reviewers ~ two reviewers must approve every production deploy | 0.106 | 0.80 | yes |
| on-call engineer is paged first ~ first to be paged is whoever is on call | 0.143 | 0.67 | yes |
| stored in the team handbook wiki ~ find it in the wiki handbook of the team | 0.116 | 0.75 | yes |
| control: Written in Go ~ Rust | 0.282 | 0.33 | yes |
| control: Retries 3 ~ 5 times | 0.064 | 0.67 | **no** (blocks it) |
| control: Runs on Mondays ~ Fridays | 0.144 | 0.33 | yes |
| control: Hosted in eu-west ~ us-east | 0.155 | 0.20 | yes |

Cosine alone cannot separate the missed heavy pairs (0.106-0.143) from the controls (0.144-0.155): that is why raising `FACT_DUP` is not an option.

*Hostile pairs the current rule has never been tested on* (same probe; "auto-merge" = what `assert_fact` does today):

| Pair | cos | Today |
|---|---|---|
| The cache is enabled ~ is **not** enabled in staging | 0.056 | **auto-merged** |
| Retries are enabled ~ **disabled** for the orders queue | 0.068 | **auto-merged** |
| Feature flag is **on** ~ **off** for all users | 0.069 | **auto-merged** |
| Latency must stay **below** ~ **above** 200 ms | 0.005 | **auto-merged** |
| Retries at **least** 3 ~ at **most** 3 times | 0.022 | **auto-merged** |
| two reviewers ~ **three** reviewers (number words, no digits) | 0.056 | **auto-merged** |
| timeout is 5 **minutes** ~ 5 **hours** (same digit) | 0.025 | **auto-merged** |
| Service A calls B ~ Service B calls A | 0.020 | **auto-merged** |
| Deploys are allowed ~ **never** allowed on Fridays | 0.109 | not merged (luck) |
| bare `enabled`/`disabled`, `true`/`false`, `on`/`off` | 0.14-0.30 | not merged (short values are safe) |

An auto-merge here is **information-losing**: no new Fact is stored and only `ASSERTED_BY {at}` is added (`assert_fact.cypher:63-65`), so
the contradicting statement vanishes and `duplicate_of` is returned as if all is well. `assert_fact` for "cache is not enabled" after
"cache is enabled" is the *normal* update path. So B0 is a correctness bug, ahead of the 25% recall gap. Unit changes that are the *same*
quantity (5 minutes ~ 300 seconds: cos 0.122; 1 GB ~ 1024 MB: 0.097) are missed because digits differ.

### B.2 Design (deterministic, LLM-free, D-002)

**B0. Precision guards: a discriminator multiset `D(text)`** replacing `value_tokens`. `D` is the sorted multiset of:
- numbers/versions (as now);
- **number words** (zero..twenty, hundred, "half", ordinals) mapped to digits;
- **quantities normalised to a base unit** from a closed table: `s/sec/seconds`, `min/minutes`, `h/hours`, `d/days`, `ms`; `kb/mb/gb` (decimal) and `kib/mib/gib` (binary) kept separate;
  token form `300s`, `1000000000B`. So "5 minutes" = "300 seconds" but != "5 hours";
- **polarity tokens**: `not no never without cannot n't none`, plus antonym pairs from a reviewed table (`on/off`, `enabled/disabled`, `allow/deny/forbid/block`, `above/below/over/under`,
  `before/after`, `min/max/least/most`, `more/less`, `increase/decrease`, `start/stop`, `open/closed`, `true/false`, `all/some/any/only`), encoded as `pol:<pair>:+|-`; an `un-`/`dis-`/`non-` prefix flips a known stem.
Auto-duplicate requires `D(a) == D(b)` (extends today's rule; stored as `Fact.dup_key`, a new property next to `value_tokens`, written by the same statement, so no extra write).
For "A calls B" vs "B calls A" add: if the token **sets** are equal but the **sequences** differ, never auto-merge (go to soft tier).
- Cost: pure Python on the asserting side, nothing in Cypher except the equality already there. Residual risk: antonyms outside the table. That is why B2 (no information loss) is also needed.
- **Information-preserving duplicate**: when the raw wording differs from `Fact.value`, store it on the edge: `ASSERTED_BY {at, wording}` (extra property in `assert_fact.cypher:64-65`). A wrong merge becomes detectable and reversible (`split_duplicate`), and who_knew can show who actually said what.

**B1. Second signal for recall (tier 2 auto-duplicate).** Add to the existing tier-1 (`norm_value` equal, or cos <= 0.08 and `D` equal) a tier 2:
`cos <= 0.16 AND stopJ >= 0.6 AND D(a) == D(b) AND same predicate AND same entity AND same scope`.
On the 16 baseline pairs this catches the 3 missed heavy pairs (cos 0.106/0.143/0.116, stopJ 0.80/0.67/0.75) and rejects all 4 controls (see table).
**This is tuned on the test set it is evaluated on (n=16), so it is an illustration, not a result.** Thresholds are set on a dev split
and only reported on a frozen test split (B.4). Char 3-gram Jaccard was also computed (0.36-0.46 for the heavy pairs, 0.36-0.80 for controls): it does **not** separate, so it is not used.
Implementation: `stopJ` is computed in Python; the statement receives `$tok_set` (sorted array) and evaluates Jaccard in Cypher on `Fact.tok_set` (same
`[t IN $tok WHERE t IN f.tok]` form verified in C.4), or - to keep the write statement lean - Python reads `cur` first and passes the winning `dup_id` to the
statement, which re-checks only that `dup.status` is still current (race-tolerant: a lost race falls through to the new-fact path, the safe direction).

**B2. Soft link `DUPLICATES_MAYBE`.** Tier 3 (`cos <= 0.20` or `stopJ >= 0.5`, guards still required, plus **entity-wide** candidates with a different predicate
spelling, at most 50 current facts per entity, LIMIT-bounded) creates the **new fact as usual** and `(new)-[:DUPLICATES_MAYBE {cos, stopJ, reason, state:'open', at}]->(old)`;
`assert_fact` returns `possible_duplicates: [{fact_id, value, cos, reason}]`. Nothing is decided silently and nothing is lost.
- Written by a separate, idempotent statement (`engram/link_maybe_duplicates`, MERGE on the pair) after `assert_fact`, not inside it: it is advisory, so a race or a crash costs only a missing hint, and it keeps the serialised write short.
- New tools (41 -> 43): `list_possible_duplicates(scope, limit)` and `resolve_duplicate(fact_id, other_id, same: bool)`.
  `same=true`: add `(newer)-[:DUPLICATES]->(older)` (the edge type already exists in the model and the View, `why_edges.cypher:99,108`, `inventory_edges.cypher:33`,
  but **nothing writes it today**), move `ASSERTED_BY` to the older fact, and close the newer with `valid_to = valid_from` (zero-width window, so `as_of`/`recall` never return it, no new status value).
  `same=false`: set `state:'distinct'` so the pair is never asked again. The *agent* (an LLM or a human) decides; Plexus stays LLM-free.
- Touch list: `api/routes_core.py:30` and `view/inventory_edges.cypher` allow-lists, `docs/graph-model.md`, tool contract tests (`tests/mcp/test_tool_coverage.py`), `test_docs_consistency.py` tool counts.

**B3. Per-predicate thresholds learned from confirmations (deterministic, no ML).** `(:DupStat {predicate, n_same, n_distinct, min_cos_distinct, max_cos_same})`
updated by `resolve_duplicate`. Effective auto threshold per predicate:
`tau(p) = min(0.16, min_cos_distinct(p) - 0.01)` always (lowering is immediate = safe), and `tau(p)` may rise above the default **only** with `n_same >= 5, n_distinct >= 5` and a gap
`max_cos_same < min_cos_distinct`. A pure function of graph data, reproducible, inspectable via a tool. Defer: needs real confirmation volume.

### B.3 Concurrency
Tier 1/2 live in the single `assert_fact` statement (already serialised, `assert_fact.cypher:1-5`), so two agents asserting a paraphrase at once see each other's committed fact:
no new race (BASELINE: concurrency added 0 extra misses). B2 is advisory, outside the statement. The `DupStat` update is one small write per confirmation.

### B.4 Measurement: C7 extended (`crucible/l1.py` + `demo_data/crucible/c7_pairs.yaml`)
- **Corpus** (>= 200 labelled pairs, each with a category and `expected in {merge, distinct, maybe}`), authored by hand/subagent, **frozen test split (50%) never used for tuning**:
  punctuation, light, heavy (40 more), **negation** (not/never/no/without), **antonym**, **quantifier** (all/some, at least/most), **number word**, **unit change same** (5 min = 300 s: merge) and **unit change different** (5 min vs 5 h: distinct),
  direction swap, entity swap (Go/Rust), near-numeric (3 vs 5), long-sentence-one-word-changed, bare booleans.
- **Gates**: (1) `false_merges == 0` on tier 1+2 for **every** category (hard fail, like `C7.violations`); report the exact count and, because 0/n proves little,
  the 95% upper bound (rule of three: 0/100 distinct pairs -> < 3%), so "precision 100%" is never written without n.
  (2) recall per category (tier 1+2) and with soft tier (`maybe` counts as "surfaced"); target heavy >= 75% auto or >= 95% surfaced.
  (3) `resolve_duplicate` replay: simulate confirmations from labels, check B3 never raises tau above a labelled-distinct pair.
- Keep the old 12+4 as a regression row so `BASELINE.md` numbers stay comparable; run sequential and concurrent as C7 does (`l1.py:867-894`); add arms B2 (vector) to show the guards are not Plexus-only.
- Pre-register thresholds and the split in `docs/BASELINE.md` before running (same discipline as L2-scale).

---

## C. Entity resolution before `assert_fact`

### C.1 Evidence
`assert_fact` first calls `resolve_entity_ex` (`service.py:329-334`), which does 3 **reads** (exact `:183`, full-text `:188`, vector `:192`) and then the `upsert_entity`
MERGE on `norm_name` (`:198-209`, `upsert_entity.cypher:6-8`). The docstring admits the race (`:174-177`). `assert_fact.cypher:37-40` anchors on `Entity {id}`, so facts about two spellings never
meet in the duplicate / supersede / contradiction logic. There is no constraint on `Entity.norm_name` (`graph/schema.py:14`: only `Task, Fact, Agent, Decision, Handoff` on `id`).

Two things found on the way, both in existing code:
- `find_entity_fulltext.cypher:2,6` and `service.py:227` search with **all tokens ANDed**. If "auth gateway" exists, a later "auth gateway service" does not find it (the AND needs `service` in the old name),
  although Jaccard would accept (2/3 >= 0.6). Resolution is **order dependent**. Switching the candidate query to OR (`a|b|c`) and keeping the Jaccard filter fixes it (verified below: 1 failure in 10 runs with AND, 0 in 20 with OR).
- Entity names get the same blind spot as values: numeric tokens only (`service.py:187, 231, 245`), so `auth-service-a` vs `auth-service-b` can merge on the vector path. Reuse `D` from B0.

### C.2 What one FalkorDB 6.0.2 statement can do (all **verified** unless marked)
| Probe | Result |
|---|---|
| `MERGE (e {norm_name}) ON CREATE SET ... WITH e CREATE (f)-[:ABOUT]->(e) RETURN e.id` | works on both the create and the match path; `ON CREATE SET e.id = $id` then `e.id = $id AS created` tells which |
| `OPTIONAL MATCH (e)<-[:ABOUT]-(f)` from a node MERGEd in the same statement | works (0 rows, `size(fs) = 0`) |
| `MERGE ... MATCH (x)` with no `WITH` | rejected: "A WITH clause is required to introduce MATCH after an updating clause" |
| `CREATE (n {id}) WITH n MATCH (m {id: n.id})` | **did see the node** here, so the "cannot MATCH a node created in the same statement" quirk (`FALKORDB_REFERENCE.md` §2 #19) did not reproduce in this simple shape. The design does not rely on it either way |
| `CALL db.idx.vector.queryNodes` / `db.idx.fulltext.queryNodes` inside a **write** statement | works, sees entities committed by earlier statements |
| A second `CALL` after a first one that yielded 0 rows | **row set becomes empty** (CALL is a join). Wrap each lookup in `CALL { CALL ... RETURN collect(node) AS xs }`: a subquery that aggregates always returns one row. Works on 6.0.2 |
| `UNIQUE` constraint on `Entity.norm_name` (needs the range index first) | creation is async (`PENDING` -> `OPERATIONAL`); a second `CREATE` with the same key fails with `unique constraint violation on node of type Entity`; `MERGE` on an existing key does not fail |

Writes to one graph are serialised (FIFO), so **a lookup that is part of the write statement cannot interleave with another creator**. That removes the race for paraphrases as well, not only for equal keys.

### C.3 Options
| | What | Verdict |
|---|---|---|
| (i) one statement: exact + full-text + vector lookup inside the creating statement | removes the race at the source; one round trip instead of 4 | **recommended** |
| (ii) UNIQUE(`norm_name`) + retry on conflict | only equal keys collide, and `MERGE` already converges there; two *spellings* have different `norm_name`, so the constraint never fires | keep as a **backstop** (catches a bug or a manual `CREATE`), not as the fix |
| (iii) `SAME_AS` / `MERGE_ENTITY` alias edge + alias-aware reads | works after the fact; every entity-keyed read must follow the alias: `find_entity_exact`, `as_of.cypher:11`, `fact_history`, `recall.cypher`, `knew_at`, `why_*` (queries listed by `grep Entity`: 25 files). Facts on the loser never meet the winner's in `assert_fact` | use **only for legacy duplicates** (migration), 3 queries |
| (iv) optimistic create + reconciliation sweep with a total order `(created_at, id)` | converges (the later creator always sees the earlier), but the loser can already hold facts | not needed once (i) is in; a periodic report is still useful as a monitor |

### C.4 Recommended design: `engram/resolve_entity` (new named query, replaces `upsert_entity` on the hot path)

Python computes, before the statement, only what needs the model or text processing: `norm`, `tok` (sorted distinct casefolded tokens), `num_key` (= `D` from B0), `emb`.
New Entity properties: `tok` (string array) and `num_key` (string); full-text candidate query `q = '|'.join(tok)`.
**Tested statement** (this is the probe, 4-d toy vectors; it needs the scope guard added, marked unverified):

```cypher
// (unverified addition, put first so a bad scope/episode/source creates nothing, replacing before_create + missing_refs reads)
// MATCH (sc:Scope {id: $scope_id}) OPTIONAL MATCH (ep:Episode {id: $episode_id}) OPTIONAL MATCH (src:Source {id: $source_id})
// WITH sc, ep, src WHERE ($episode_id = '' OR ep IS NOT NULL) AND ($source_id = '' OR src IS NOT NULL)
CALL {
  CALL db.idx.fulltext.queryNodes('Entity', $q) YIELD node
  WHERE node.kind = $kind AND node.num_key = $num_key
  WITH node, size([t IN $tok WHERE t IN node.tok]) AS inter,
       size($tok) + size(node.tok) - size([t IN $tok WHERE t IN node.tok]) AS uni
  WITH node, toFloat(inter) / uni AS j WHERE j >= $jac           // 0.6, FULLTEXT_JACCARD
  WITH node ORDER BY j DESC, node.created_at ASC, node.id ASC
  RETURN collect(node) AS ft
}
CALL {
  CALL db.idx.vector.queryNodes('Entity', 'embedding', $k, vecf32($emb)) YIELD node, score
  WHERE node.kind = $kind AND node.num_key = $num_key AND score <= $thr   // 0.10, ENTITY_NEAR
  WITH node, score ORDER BY score ASC, node.created_at ASC, node.id ASC
  RETURN collect(node) AS vec
}
OPTIONAL MATCH (ex:Entity {norm_name: $norm})
WITH coalesce(ex, head(ft), head(vec)) AS hit,
     CASE WHEN ex IS NOT NULL THEN 'exact' WHEN size(ft) > 0 THEN 'fulltext'
          WHEN size(vec) > 0 THEN 'vector' ELSE 'new' END AS how
FOREACH (_ IN CASE WHEN hit IS NULL THEN [1] ELSE [] END |
  MERGE (n:Entity {norm_name: $norm})
    ON CREATE SET n.id = $entity_id, n.name = $name, n.kind = $kind, n.num_key = $num_key,
                  n.tok = $tok, n.embedding = vecf32($emb), n.created_at = $now)
RETURN CASE WHEN hit IS NULL THEN $entity_id ELSE hit.id END AS id, how
```
Notes: the `MERGE` is kept even though `ex` was just checked, so the UNIQUE constraint and `MERGE` semantics stay consistent if the shape ever changes. `ORDER BY ... created_at, id` makes
ties deterministic (vector scores tie in no fixed order, `falkordb-6-0-2-silent-wrong-answers`). Returned `name`/`kind` for the hit come from a second `ro` `find_entity_exact` by id (or add them to the RETURN with `CASE`).
Then `assert_fact` runs as today with `entity_id` (it is a separate statement; entities are never deleted, so no interleaving problem). Cost: one write statement per `assert_fact` that is *not* an exact match, replacing three reads + one write; **for exact matches use the existing
`find_entity_exact` read first** (`service.py:183-185`) to keep the hot path write-free, and only run the statement on a miss (the race only exists on a miss).

**Concurrency test (probe `pf_race_probe.py`, results from this analysis).** 50 threads behind a barrier, 25 per spelling, one new graph per run, 4-d toy embeddings (`1,0,0,0` vs `0.99,0.05,0,0` for the vector pair; tokens `auth gateway service` / `auth gateway` for the full-text pair):

| Flow | Pair | Entities created |
|---|---|---|
| today (separate reads, then MERGE) | vector pair | **2** (outcomes: 2 created, 48 matched) |
| today | full-text pair | **2** (21 created, 29 matched) |
| atomic statement, AND candidate query | full-text pair, shorter name first | **2 in 1 of 10 runs** (order-dependent miss) |
| atomic statement, OR candidate query | both pairs, 20 runs | **1 in 20/20** |

Productise as `tests/integration/test_entity_race.py`: 50 racers x {A, B} spellings, real fastembed vectors, assert `count(Entity) == 1`, every call returns the same `id`, exactly one `how == 'new'`;
repeat 20x with shuffled start order; add the three-spelling case (A, B, C where B~A and C~B but C!~A) and assert the result is **at most 2 and deterministic** (transitivity is not claimed: document it).
Also assert the numeric guard: `Service 1` vs `Service 2` racing yields 2 entities.

### C.5 Migration for existing data
1. **Check key duplicates** (should be none: MERGE has always been the writer): `MATCH (e:Entity) WITH e.norm_name AS n, count(*) AS c WHERE c > 1 RETURN n, c`. If any, resolve them first (the constraint would go `FAILED`, `schema.py:46`).
2. **Backfill** `tok` and `num_key` in bounded batches (200 ids per statement, `UNWIND $rows ... MATCH (e:Entity {id: row.id}) SET e.tok = row.tok, e.num_key = row.num_key`), computed in Python with the new `D`. Entities without the properties never match the new lookup (`node.num_key = $num_key` is false for null), so run the backfill **before** switching the code.
3. **Constraint**: `CREATE INDEX` is already there (`norm_name` index, `schema/indexes.cypher`); add `Entity` to `apply_schema` with property `norm_name` (generalise `UNIQUE_LABELS` from `(label, 'id')` to `(label, prop)` pairs, `schema.py:14, 26-51, 63-71`) and wait for `OPERATIONAL`.
4. **Legacy near-duplicate report** (dry run, read-only): for each Entity run the same lookup against older entities, emit `(younger, older, how, cos, jaccard)`. Review by the owner.
5. **Bridge, not merge**: for accepted pairs write `(younger)-[:SAME_AS]->(older)` (chunked, idempotent MERGE) and make three reads alias-aware: `find_entity_exact` (return the target), `as_of.cypher:11`, `fact_history`. Do **not** re-point `ABOUT` edges: the two entities' current facts for one predicate would then overlap and need a re-run of the duplicate / supersede / contradiction logic. Legacy facts therefore keep not meeting; new facts about either spelling land on the older entity. Document that limit.
6. Rollback: the constraint can be dropped (`GRAPH.CONSTRAINT DROP`); `SAME_AS` edges and `tok`/`num_key` are additive.

---

## D. Risks and open questions
- **Probes used 4-d toy embeddings and a single process.** The ordering/serialisation argument does not depend on dimension, but re-run the race test with the real 384-d model and the real client pool (`PLEXUS_DB_POOL`, `MAX_QUEUED_QUERIES 25` in the image default, `CLAUDE.md` §5: use the Crucible's `FALKORDB_ARGS`).
- A write statement that calls two index procedures is slower than a bare MERGE and holds the per-graph lock while it runs; measure `run_time_ms` at 10k entities (one vector probe is a few ms in the probe graph, which is tiny). Bound with `k <= 5` and `LIMIT`.
- B0's antonym table is a curated list: it narrows, not closes, the false-merge hole. B2's information-preserving duplicate is the net under it.
- A: `ObserverClient`/header audit mode adds a tenant policy concept. Keep it in one module so `guard.py` stays dependency-free.
- `ENTITY_NEAR` and `FACT_DUP` were tuned on synthetic data (`PLEXUS_REPORT.md:693-695`); the extended C7 and a matching entity-name set (aliases, abbreviations, `svc`/`service`, plural) should be added together.

## E. Effort and order of implementation

| # | Work item | Depends on | Days |
|---|---|---|---|
| 1 | **B0** discriminator `D`, number-word / unit tables, polarity lexicon, `Fact.dup_key`, `ASSERTED_BY.wording`; unit tests + the hostile pairs of B.1 as regression | - | 2.0 |
| 2 | **B-eval** extended C7 corpus (>= 200 pairs), categories, gates, frozen split, pre-registration text | 1 | 2.0 |
| 3 | **C** `resolve_entity` statement, OR candidates, `Entity.tok/num_key`, race test (real embeddings), UNIQUE(`norm_name`) in `apply_schema` | 1 (for `D`) | 2.5 |
| 4 | **C migration** backfill, report, `SAME_AS` bridge + 3 alias-aware reads | 3 | 1.5 |
| 5 | **A** `ToolDef.kind`, policy module, `ObserverClient`, `off`/`light` paths, verification of `m.writes`, docs | - | 2.5 |
| 6 | **A guard** allowlist, observer graph-existence rule, tests (`deploy/tests/test_guard.py`), commandstats no-write integration test | 5 | 1.5 |
| 7 | **A perf** L4 `full/light/off` runs, `record_step` scaling measurement | 5 | 1.0 |
| 8 | **B1** tier 2 (stopJ), thresholds from the dev split, report on test split | 1, 2 | 1.5 |
| 9 | **B2** `DUPLICATES_MAYBE`, `link_maybe_duplicates`, 2 tools, View/inventory/docs/test-count updates | 8 | 3.0 |
| 10 | **B3** `DupStat` and per-predicate thresholds | 9 + real confirmations | 1.0 |
| 11 | (optional) **A-ii** batched `light` audit with spool | 5 | 2.0 |

About **17-19 days** with 11 and 10 included or not; the first three items (about 6.5 days) remove the only silent-data-loss risk and the entity race.
Order: **1 -> 3 -> (2 in parallel) -> 5 -> 6 -> 8 -> 4 -> 7 -> 9 -> 10 -> 11.** Reasons: item 1 fixes silent wrong merges and is needed by C's `num_key`; C has a verified
design and a hard test; A unblocks the public read-only demo (guard) but changes the runtime used by all 41 tools, so it comes after the data-correctness items; B2/B3 add tools
and need the labelled corpus first.

## F. Evidence index
- Runtime audit path: `mcp/runtime.py:144-163, 165-184, 186-222`; `mcp/lineage_hook.py:40-80, 90`; `mcp/metering.py:17-44`; `mcp/toolkit.py:37-41, 94-119`; `mcp/tenant.py:53-56, 64-100`.
- Recall hook: `mcp/tools_engram.py:143-198`; `lineage/service.py:105-120, 121-148, 172-220, 222-232`; `queries/lineage/{record_step,link_step,record_recall,who_knew,knew_at,why_recalled}.cypher`; `queries/audit/record_tool_call.cypher:103-131`; `audit/recorder.py:48-90`.
- Guard: `deploy/guard.py:5-8, 37, 86-92, 278-282, 335-351, 368-387`.
- Engram: `engram/service.py:29-31, 44, 55-68, 157-217, 219-248, 284-374`; `queries/engram/{assert_fact,upsert_entity,find_entity_*}.cypher`; `common.py:25-27`; `graph/schema.py:14, 54-71`.
- Benchmarks: `docs/BASELINE.md:145-147, 171-172`; `crucible/l1.py:769-837, 867-894`; `docs/PLEXUS_REPORT.md:689-697`.
- FalkorDB constraints: `docs/reference/FALKORDB_REFERENCE.md` §2 #12, #17-19, #22; skills `falkordb-6-0-2-silent-wrong-answers`, `falkordb-big-write-statement-quirks` (#2, #3, #5), `falkordb-plan-shape-tests` (#6b).
