# Plexus MCP server

Entry point: `plexus-mcp` (`plexus.mcp.server:main`). Built on the `mcp` 2.x SDK (`mcp.server.mcpserver.MCPServer`),
pinned `mcp>=2.3,<3` (see `docs/spikes/S1-mcp-claude.md`).

| Transport | Command | Tenant binding |
|---|---|---|
| stdio | `uv run --directory <abs>/plexus plexus-mcp --transport stdio --tenant acme` | `--tenant` (or env `PLEXUS_TENANT`), fixed for the process. One process per Claude Code session. |
| streamable HTTP | `uv run plexus-mcp --transport http --port 8765` (compose service `plexus-mcp`) | URL path `/mcp/t/<tenant>` (or header `X-Plexus-Tenant` on `/mcp`), **pinned to the MCP session**: replaying a `mcp-session-id` under another tenant returns 403; a session id the server holds no pin for (never issued, evicted, expired) returns **404** (fail closed: the client initializes a new session). Pins are evicted least-recently-used. |

The tenant is never a tool argument. It must match `^[a-z0-9_]{1,48}$` and selects the graph `plexus_t_<tenant>`; the
schema is applied on first use of a tenant and re-checked every `PLEXUS_SCHEMA_RECHECK_S` seconds (default 5): if the tenant graph is
deleted or replaced under a running server (a demo `--reset`, a restore), the next call re-applies the schema and drops the
cached scope ids, so no restart is needed. The tenant in the URL is a routing identity, not authentication: keep the
port on loopback (compose publishes `127.0.0.1:8765` only) or put a token proxy in front.

DB connection: env `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_PASSWORD`. The sync client uses a blocking pool of
`PLEXUS_DB_POOL` connections (default 256): callers beyond it wait up to `PLEXUS_DB_POOL_TIMEOUT` seconds (default 30)
instead of failing, and connects/queries are retried for up to `PLEXUS_DB_LOADING_WAIT_S` seconds (default 60) while Redis is
still loading its AOF (`-LOADING`). Embeddings: env `PLEXUS_EMBEDDER=fastembed|hash`
(`PLEXUS_EMBED_THREADS`, default 1; `PLEXUS_EMBED_CACHE` / `FASTEMBED_CACHE_PATH` for the model cache).
HTTP only: `PLEXUS_MCP_ALLOWED_HOSTS` (comma list, `host:*` = any port) for the Host-header allow-list.
`GET /healthz` is a static liveness answer; `GET /healthz?deep=1` also pings FalkorDB (503 when it is down); compose uses the
deep form.

## Claude Code

Local, stdio, generated for your checkout (fastest start-up; it names the `plexus-mcp` script of the venv that runs the command):

```bash
cd plexus && uv sync                                              # once
FALKORDB_PORT=6379 uv run plexus mcp-config --tenant demo --out ../mcp.local.json   # or omit --out to print it
uv run plexus mcp-config --tenant demo --http http://127.0.0.1:8765                  # streamable-HTTP variant instead
```

The command reads `FALKORDB_HOST` / `FALKORDB_PORT` / `PLEXUS_EMBEDDER` from the environment and writes them into the config's
`env`. `plexus.mcp.json` at the repo root is only a **portable template**: it contains no machine path, starts the server with
`uv run --directory plexus plexus-mcp ...` (relative to the directory Claude Code is started in, so start it from the repo root),
tenant `demo` and port 6379. It is slower to start than the generated config (Claude's first `ToolSearch` can run while the
server is still `pending`), which is why headless runs should use the generated file. Copy it and edit `--tenant` / the port, or
generate one with `plexus mcp-config`. `tests/demo/test_mcp_config.py` fails if a machine path ever gets committed into it.
Headless:

```bash
env -u ANTHROPIC_API_KEY claude -p "<task>" --mcp-config <abs>/mcp.local.json --strict-mcp-config \
  --allowedTools "mcp__plexus__*" --model haiku --max-turns 8 --output-format stream-json --verbose
```

HTTP variant (tenant in the path):

```json
{ "mcpServers": { "plexus": { "type": "http", "url": "http://127.0.0.1:8765/mcp/t/acme" } } }
```

or in a header: `{"type": "http", "url": "http://127.0.0.1:8765/mcp", "headers": {"X-Plexus-Tenant": "acme"}}`.

A blocked tool still exits 0 in `claude -p`: check `permission_denials` and `tool_result.is_error` in the stream.

## Tools

Every tool takes `agent_id` (required) and `step` (optional int). Results are JSON objects and include `tool_call_id`.
45 tools: 29 in the three groups below (Engram, Relay, Lineage), 7 staleness tools, 5 memory-strength tools, `impact`, `assert_relation` and 2
soft-duplicate tools (the three sections after this list).
- **Engram:** `start_session`, `remember_episode`, `assert_fact` (optional `source_id`/`episode_id`), `recall` (returns
  `recall_id`), `fact_history`, `log_procedure_run`, `best_procedure`.
- **Relay:** `register_agent`, `create_tasks`, `claim_next_task`, `heartbeat`, `complete_task`, `fail_task`, `reopen_task`,
  `handoff`, `verify_artifact`, `record_decision`, `ready_tasks`, `task_status`, `blocked_by_failure`.
- **Lineage** (registered when `plexus.lineage` is installed; see `plexus/mcp/lineage_tools.py`): `add_source`, `why`,
  `why_recalled`, `who_knew`, `knew_at`, `as_of`, `forget_source`, `quarantine_source`, `release_quarantine`.

`add_source` takes `trust='normal'|'high'` (default: keep the source's trust, new = `normal`); `'high'` protects the facts
derived from it from fading (`docs/forgetting.md`). A number 0..1 is still accepted and means `normal`.

**Steps and provenance:** after a call succeeds, the runtime opens or reuses a Lineage `Step` per (agent, n), chained
by `NEXT`, and stores its id on `ToolCall.step_id`.
- **Auto-numbering:** calls without `step` auto-increment per agent. An explicit `step` is respected; one behind the
  agent's latest step falls back to the next number (the `NEXT` chain is append-only).
- **Parallel calls from one agent** (normal for Claude Code) are run one after another per `(tenant, agent_id)`: numbers
  and the call-start times they carry are assigned in the same order, so `Step.n` and `Step.at` never disagree and
  `knew_at` / the Time Machine cut correctly. Different agents never wait for each other. For explicit steps, send them
  in non-decreasing order (or share one step across parallel calls); an out-of-order one is remapped as above.
- **Edges:** writes attach `WROTE` and reads attach `READ`. `assert_fact` uses `link_assert_result`, so a superseded
  fact is READ by its superseder. `recall` writes a `Recall` node with `RETURNED {rank, score}`.
- **Failures:** a rejected call leaves no Step.
- **Degraded bookkeeping:** the tool's own write is the source of truth. If the Step, its `WROTE`/`READ` edges (retried
  once) or the `ToolCall` row could not be written, the call still succeeds and the result carries
  `lineage_degraded: true` and/or `audit_degraded: true` (absent otherwise), so an agent or test can tell.

`scope` (assert_fact, recall, fact_history): `global` (default), `project:<name>`, `user:<name>` (both inherit `global`)
or a scope id (max 512 chars). **Writes** (`assert_fact`) create a named scope on first use; **reads** (`recall`, `fact_history`,
`as_of`) never do: a scope that does not exist gives an empty answer (`recall` returns `count: 0`, `scope_id: null` and records
no `Recall`), so a typo cannot grow the graph.

## Argument limits and errors

Every argument is bounded; a violation is a tool error of one line, e.g. `recall: k: Input should be greater than or equal to 1`
(no model names, no URLs, never the rejected value).

| What | Limit |
|---|---|
| `agent_id`, any id (task, session, fact, source...) | 1..128 chars |
| subject, predicate, names, role, harness, kind, scope | up to 512 chars (subject and predicate at least 1) |
| title, uri | up to 2 000 chars (title at least 1) |
| one value (`value`, `query`, `notes`, `reason`, artifact `summary`) | up to 20 000 chars |
| one text (`remember_episode` text, `handoff` note, decision text, source excerpt) | up to 100 000 chars (at least 1 where required) |
| lists (`tasks` ≤ 200, `depends_on`, `steps`, `artifacts`, `artifact_ids`, `fact_ids`, `based_on_fact_ids`) | up to 200 items |
| `step` | 1..2 147 483 647 |
| `lease_ms` | 1..86 400 000 (one day) |
| `priority` | ±2 147 483 647; `expected_version` 0..2 147 483 647 |
| `as_of`, `t`, `step_n` | 0..9 999 999 999 999 (`step_n` ≤ 2 147 483 647) |
| `remember_episode.role` | `user`, `assistant`, `tool` or `note` |

`create_tasks` items and `complete_task` / `fail_task` artifacts **reject unknown keys** (a misspelt `dependsOn` is an error that
lists the expected keys, not a silently dropped dependency). Unknown *top-level* arguments are ignored by design (the tenant is never
an argument). `log_procedure_run` with a `task_id` and `blocked_by_failure` check that the task exists, like `task_status`.

By default every call is audited (audit mode `full`, below): the tool wrapper sums the database-reported `run_time_ms` of
the queries the tool ran and then writes one `ToolCall` (`audit/record_tool_call`) with `IN_STEP`/`CREATED`/`UPDATED`
edges. Deliberate deviation from PLAN §3 ("same statement"): the server-side time is only known after the tool's own
statement has run.

## Audit modes

A read tool used to cost 2-3 write statements (Step, `Recall` + `READ` edges for `recall`, `ToolCall`), queued behind
every real writer of the tenant graph, and its `READ {via:'recall'}` edges changed ranking (activation weighs them 0.3).
That made a read-only public tenant impossible. Each tool now has a class and each tenant an audit mode.

**Tool class** (`ToolDef.kind`, declared where the tool is defined; an unmarked tool is `write`, so a forgotten
annotation is the safe one): `read` = `recall` `fact_history` `best_procedure` `ready_tasks` `task_status`
`blocked_by_failure` `why` `why_recalled` `who_knew` `knew_at` `as_of` `memory_strength` `facts_to_verify`
`docs_to_update`. Everything else is `write` (including `memory_sweep`, whose `dry_run` is an argument). `recall` is also
an *exposure* tool: its `READ` edges are the provenance behind `who_knew`, `knew_at`, `why_recalled` and forgetting.

**Tenant mode**, from env read once at start (a bad value stops the server): `PLEXUS_AUDIT_MODE` = `full` (default) |
`light` | `off`, and a per-tenant table `PLEXUS_AUDIT_MODES="demo*=off,team_*=full"` (`glob=mode`, first match wins,
matched on the tenant id; unmatched tenants use `PLEXUS_AUDIT_MODE`).

| Mode | read tool | `recall` (exposure) | write tool |
|---|---|---|---|
| `full` | today: Step, `READ`/`Recall` edges, `ToolCall` | full | unchanged |
| `light` | one `ToolCall {wrote:false}`; no Step, no `IN_STEP`, no `READ` | stays **full** | unchanged (full) |
| `off` | **nothing written**; `tool_call_id: null` | nothing written; `recall_id: null` | **refused**: `<tool>: this tenant is read-only (audit mode 'off'): writes are disabled` |

* **Per-call `audit`.** Every read tool accepts an optional `audit: "light" | "full"`. `"light"` lowers that one call
  (for `recall` on a `full` or `light` tenant it drops the Step, `Recall` and `READ` edges: use it for lookups that
  should not count as the agent having *used* the facts). It can never raise the mode: `"full"` is a no-op, and on an
  `off` tenant it changes nothing. Write tools do not take it. A result carries `"audit": "light"|"off"` when the
  call ran below `full` (absent in `full`, so full-mode results are unchanged).
* **Step numbers.** A `light`/`off` call takes no Step, so an agent's `n` sequence counts only calls that have one
  (writes and `recall` in `full`). `knew_at(agent, N)` therefore does not count meta-reads. These calls also skip the
  per-agent call lock (there is no step number to keep in order).
* **`off` is enforced, not trusted.** The call runs on a client whose write methods raise, so a tool that is labelled
  `read` but writes fails closed instead of changing the graph. In `light`, such a tool is audited in full for that
  call and the server logs an error. A test asserts the guard's allowlist equals the set of `read` tools.
* **`off` never creates a graph.** For an `off` tenant the runtime does not apply the schema: if the tenant graph does
  not exist the call is refused (`unknown tenant ...: read-only tenants are not created by requests`), and a graph that
  was deleted under a running server is not re-created either. (`full`/`light` tenants still heal themselves.)
* **No-write proof** (`tests/mcp/test_audit_modes.py`): a burst of all 14 read tools x 3 on an `off` tenant leaves
  Redis `INFO commandstats` with `graph.ro_query` up by 51 or more and **zero** `graph.query`/`graph.delete`/`set`/...,
  the keyspace and `rdb_changes_since_last_save` unchanged, and the node and edge counts identical. The same burst
  in `full` mode is the control (it issues >= 2 `graph.query` per call).
* **Deployment.** `deploy/app.py` calls `ensure_demo_audit_off()`, which puts `demo*=off` first in `PLEXUS_AUDIT_MODES`
  (an operator's own `demo*` rule cannot weaken it): the public `demo` and `demo_*` tenants are readable over MCP and
  never written. See `docs/deploy.md`.

Write statements per read call (counted from `commandstats`): `full` 2 (3 for `recall`), `light` 1, `off` 0.
For the effect on throughput see the next section.

### Throughput (L4 `P-mcp` recall row)

Scripted, no LLM: `deploy/bench_audit_modes.py` runs the Crucible L4 recall sweep on the `P-mcp` arm (300 facts,
`Runtime._run`, 10 recalls per worker) three times per mode, alternating the order, and reports the median. Only
`recall` changes mode (`light` = what `recall(audit="light")` does, `off` = what a `demo*` tenant does); seeding stays
`full`. One FalkorDB 6.0.2 container on `127.0.0.1` (slot 65), Windows 11 desktop, all 27 points per embedder ran with
0 errors and 0 empty recalls. Rows are `ops/s (client p50 / p99 ms)`.

| Embedder | Workers | `full` | `light` | `off` | light / full | off / full |
|---|---|---|---|---|---|---|
| `hash` | 1 | 17.7 (52 / 113) | 31.2 (31 / 60) | 35.0 (26 / 55) | 1.76x | 1.98x |
| `hash` | 10 | 52.4 (181 / 272) | 98.1 (97 / 142) | 95.9 (90 / 194) | 1.87x | 1.83x |
| `hash` | 50 | 41.9 (1109 / 2093) | 109.1 (412 / 800) | 114.3 (367 / 1016) | 2.60x | 2.73x |
| `fastembed` | 1 | 10.5 (93 / 144) | 14.7 (64 / 101) | 18.4 (49 / 100) | 1.40x | 1.75x |
| `fastembed` | 10 | 35.3 (258 / 523) | 40.6 (229 / 325) | 46.1 (207 / 268) | 1.15x | 1.31x |
| `fastembed` | 50 | 28.1 (1710 / 2346) | 38.7 (1259 / 1528) | 43.9 (1131 / 1350) | 1.38x | 1.56x |

How to read it: the `hash` rows isolate the audit cost (the embedder is free): `light` removes two of the three write
statements per recall and is 1.8-2.6x faster, `off` removes all three and is 1.8-2.7x. With the real `fastembed` model
the gain is 1.15-1.4x for `light` and 1.3-1.75x for `off`, because the shared model (single thread, calls serialised)
is the other limiter; this agrees with `docs/BASELINE.md`, where P-mcp is embedder-bound at high worker counts. Caveats:
this is not the compose-network setup of the BASELINE table (its P-mcp numbers are lower: the network hop), so compare
the ratios, not the absolute values; three runs per cell and a desktop that was doing other things, so treat differences of
about 10-15% as noise (`light` and `off` are within it of each other with `hash`); only `recall` was measured, not claims.
`light` on `recall` also drops the exposure provenance (no `Recall`, no `READ` edges), so use it for lookups, not for
reads an agent will act on.

## Headless smoke (verified)

`claude -p "Use the plexus tools: start a session as agent smoke, remember an episode 'hello', assert fact subject=API
predicate=version value=v1 in the default scope, then recall 'API version'. Report the recalled value."` with
`--strict-mcp-config --allowedTools "mcp__plexus__*" --model haiku --max-turns 6` returned `v1` (success, 6 turns, ~$0.006).
Tip: point `command` at the venv script (`<abs>/plexus/.venv/Scripts/plexus-mcp.exe`, no `uv run`) for the fastest start-up.
With `uv run`, Claude's first `ToolSearch` can run while the server is still `pending` and burn the turn budget
(`error_max_turns`); the exit code is 0 either way, so check `result.subtype` and `permission_denials`.

## View API

`uv run plexus-api` (port 8080, env `PLEXUS_API_HOST`/`PLEXUS_API_PORT`; CORS origins from `PLEXUS_CORS_ORIGINS`, default
`localhost`/`127.0.0.1` on 5180 and 5173; Crucible results file from `PLEXUS_RESULTS_PATH`). Response shapes:
`docs/view-api.schema.json` (regenerate with `uv run python -m plexus.api.export_schema`). Reads only: the API holds a
`ReadOnlyClient` with no write method, and `step/{n}` and `why/{id}` return 501 until `plexus.lineage` is installed.

Bounds: `since`, `until`, `after` and the `step/{n}` path are `0..9 999 999 999 999` (out of range = **422**, never 502); `why`/`recall`
ids are 1..128 chars. `/stream`: `poll_ms` is at least 200, at most `PLEXUS_API_MAX_STREAMS` (default 20) connections are open at once
(the next gets **429**), and subscribers polling the same `(tenant, after)` share one `view/flow` read per 150 ms. `GET /healthz?deep=1`
also pings FalkorDB (503 when it is down). `inventory` counts nodes and edges per graph-model label/type in O(labels); if the graph
holds a label or type the model does not list, it falls back to a full scan.

## Staleness tools (P7-J, 7 tools; see `docs/staleness.md`)

Registered by `plexus/mcp/staleness_tools.py` (`register_staleness`), so the server then exposed 36 tools (41 with the memory tools). Changing code makes a
memory **suspect**, never false: it stays recallable, and the agent re-checks it. Paths are normalised to the canonical form
(absolute, `/`, upper-case drive); a relative path is an error. Limits: ids <= 128, paths <= 1024, hashes <= 128, <= 200 changes.

| Tool | Arguments (besides `agent_id`, `step`) | What it does |
|---|---|---|
| `anchor_fact` | `fact_id`, `path`, `symbol=''`, `hash=''` | `(Fact)-[:ANCHORED_TO]->(CodeAnchor)` for a file or a Python function / class. A `hash` that differs from the anchor's stored hash makes the fact suspect (`suspect: true`, `change_id`). Unknown fact: error, nothing written. |
| `describe_code` | `source_id`, `path`, `symbol=''`, `hash=''` | `(Source)-[:DESCRIBES]->(CodeAnchor)`: this doc describes this code. |
| `mark_changed` | `changes=[{path, symbol='', new_hash, old_hash='', kind?}]` (1..200), `commit=''`, `at=null` | The hook entry point. Active facts anchored to (or derived from a Source at) a changed file / symbol become `suspect`; returns `change_id`, `suspect_fact_ids`, `decisions` (+ `decisions_total`), `docs_to_update`, `unchanged`, `truncated`. A first sighting without `old_hash` is a baseline. |
| `verify_fact` | `fact_id`, `still_true`, `new_value=''`, `evidence=''`, `commit=''` | Confirmed: `verified`. Changed: the new value is asserted (supersede), the old fact ends at the time of the code change, decisions on the old fact are flagged. If the backdate fails twice the result has `verify_degraded: true`; calling it again with the same `new_value` finishes the job. |
| `facts_to_verify` | `scope=''`, `limit=50` | Suspect facts (changed code or a passed review date), ordered by live decisions, then activation, then age; each row has reason, anchors, decision count and (forgetting on) `activation`, `protected`. |
| `docs_to_update` | `since=0`, `limit=50` | Docs that describe code changed after the doc was last edited, with the commits / paths. |
| `set_review_date` | `fact_id`, `verify_after` (epoch ms) | Review date for facts no code change can invalidate; once passed the fact is suspect. |

Audit: facts a call made suspect or verified are `UPDATED` edges of the ToolCall and `WROTE` edges of the Step; a created `Change` /
`CodeAnchor` is a `CREATED` edge. `facts_to_verify` adds no `READ` edges (a suspect fact is not strengthened by being listed).
## Memory-strength tools (P7-K, `plexus/mcp/memory_tools.py`; D-012, `docs/forgetting.md`)

Five more tools, registered by `register_memory` (29 + 7 staleness + these 5 = 41; `impact`, `assert_relation` and the 2 soft-duplicate tools make 45). Forgetting
lowers a fact's **rank only**; none of these deletes anything.

| Tool | Arguments (besides `agent_id`, `step`) | Result |
|---|---|---|
| `pin_fact` / `unpin_fact` | `fact_id` | `{fact_id, pinned}`. A pinned fact is never ranked below neutral and never swept. |
| `memory_strength` | `fact_id` | `{strength: {activation, a0, multiplier, floor, protected, protect_reasons, pinned, surprise, counts, last_use, last_recall, explanation, …}}`. Read-only: no `READ` edge, so asking is not using. |
| `memory_sweep` | `scope='global'`, `threshold=None` (−50..50), `dry_run=true`, `limit=200` (1..200) | `{sweep: {threshold, dry_run, scanned, candidates:[{fact_id, text, activation}], would_move, moved, skipped, truncated}}`. Moves to `dormant` only with `dry_run=false`; protected and suspect facts are never moved. |
| `restore_fact` | `fact_id` | `{fact_id, restored, status, was}` (+ `reason: 'already_superseded'`, `superseded_by` when a newer active fact blocks it); a fact that is not dormant is left alone. |

`recall` gains `include_dormant: bool = false` and `forgetting: bool | null = null` (null = the server default,
`PLEXUS_FORGETTING`). Each fact in the result also carries `surprise`, `activation`, `protected` (both `null` when
forgetting is off), `verify_state`, `suspect_since` and `suspect_reason`. `assert_fact` returns `surprise`.
Audit: `pin_fact`, `unpin_fact`, `restore_fact` and a real `memory_sweep` record `UPDATED` edges to the facts they
changed; `ToolCall.query_name` of a forgetting-on `recall` is still `engram/recall`: `activation/*` reads are auxiliary and never name a call that ran another read.

## Impact tool (P9-b, `plexus/mcp/tools_impact.py`)

One read-only tool, registered by `register_impact` (45 tools in total: the 41 above, `impact`, `assert_relation` and the 2 soft-duplicate tools). It answers "what breaks if this is wrong?" before
`quarantine_source` / `forget_source` / `fail_task` write anything, in one call instead of three.

| Tool | Arguments (besides `agent_id`, `step`) | Result |
|---|---|---|
| `impact` | `kind='source'\|'fact'\|'task'`, `id`, `depth=8` (1..12 for source/fact, 1..50 for task), `max_items=50` (1..200), `order='id'\|'valid_from'\|'created_at'` (P9-f: how the listed facts are sorted; a time order lists the earliest first), `offset=0` (P9-f: page through the facts / tasks), `probe_ids=[]` (P9-f: at most 200 ids to test against the whole affected set) | `{impact: {kind, id, depth, facts: {total, ids, records: [{id, status, valid_from, created_at}], order, offset, next_offset, ids_truncated, by_status, probes?}, readers: {steps_total, agents_total, agents, agents_truncated}, decisions: {total, ids, ids_truncated}, tasks: {total, ids, ids_truncated}, handoffs: {total, ids, ids_truncated}, truncated}}` for a source (facts reaching it through `DERIVED_FROM`) or a fact (itself plus the facts derived from it); `tasks` are the tasks the affected decisions are `FOR`. For `kind='task'`: `{impact: {kind, id, depth, tasks: {total, ids, offset, next_offset, ids_truncated, probes?}, truncated}}`, the unfinished tasks that transitively depend on it (what `blocked_by_failure` returns). Totals are exact up to 5000 facts / 5000 tasks (`truncated`); lists are cut at `max_items`, and a cut list always says so (`ids_truncated`; P9-f: before, "not in the first 200 ids" looked like "not affected"). Unknown id -> a tool error naming it. |

Nothing is written (no `READ` edges either: looking at the damage must not make the facts look used); the audit `ToolCall` +
`Step` are the only rows. The expansion is the level-wise, distinct-node one of `lineage/impact_source` / `lineage/impact_fact`
(`docs/queries.md`): a diamond lineage of depth 12 with fan-in 3 (about 500k paths, 60 facts) answers in a few ms.

`Lineage.forget_source`, `quarantine` and `release_quarantine` gained an optional `depth` (1..12, default 8; was a fixed 5 hops),
`Lineage.why` an optional `depth` (1..12, default 6; was a fixed 3), and `Relay.blocked_by_failure` an optional `depth`
(1..50, default 50; was a fixed 10). The MCP tools `forget_source`, `quarantine_source` and `blocked_by_failure` keep their
schemas and use the new defaults. P9-f: the MCP `why` tool takes optional `depth` (1..12, default 6) and `max_elements`
(2..5000, default 200), the values it used to hard-code (Crucible L6-B: chains deeper than 6 hops were unanswerable through
the tool).
## Soft-duplicate tools (P9-c, `plexus/mcp/tools_dedup.py`; `plexus/engram/dedup.py`)

`assert_fact` decides whether a new value is the same statement as a current one (same entity, predicate and scope):

| Tier | Rule (all need the same **discriminator key**, and not "same words, other order") | Result |
|---|---|---|
| exact | equal normalised text | duplicate |
| 1 | value-embedding cosine distance <= 0.08 | duplicate |
| 2 | stemmed, stop-word-free token Jaccard >= 0.6 **and** cosine distance <= 0.16 | duplicate |
| 3 | cosine distance <= 0.20 **or** Jaccard >= 0.5 | not merged: the fact is stored and linked `(new)-[:DUPLICATES_MAYBE {score, cos, jaccard}]->(old)` |

The discriminator key is a multiset of numbers and versions, unit-normalised quantities (`5 minutes` = `300 s` != `5 hours`;
`1 GB` = `1000 MB` != `1 GiB`), number words (`two` = `2`), ordinals, negations (`not never no without`, `un-`/`dis-`/`non-`
prefixes) and a reviewed antonym table (`enabled`/`disabled`, `above`/`below`, `at least`/`at most`, `some`/`only`, ...). So
`enabled`/`not enabled`, `5 minutes`/`5 hours`, `two`/`three` and `at least`/`at most` are never merged. When two values have the
same content words in a different order (`A calls B` / `B calls A`) they are never auto-merged either (tier 3). Facts written
before P9-c have no key and only match by exact text. Thresholds: `PLEXUS_DUP_JACCARD`, `PLEXUS_DUP_TIER2_COS`,
`PLEXUS_DUP_MAYBE_COS`, `PLEXUS_DUP_MAYBE_JACCARD` (the tier-1 distance stays the `Engram` constructor argument).

A merge keeps the raw wording: `ASSERTED_BY.text` on the duplicate's edge, so it is detectable and reversible.
`assert_fact` returns `possible_duplicates: [{fact_id, value, cos, jaccard}]` (empty when none; at most 5) and every `recall`
fact carries `maybe_duplicate_of: [fact ids]`.

| Tool | Arguments (besides `agent_id`, `step`) | Result |
|---|---|---|
| `confirm_duplicate` | `new_id`, `old_id` | `{new_id, old_id, merged, already, reopened, moved}`. The newer fact gets a zero-width window and `(new)-[:DUPLICATES]->(old)`; its asserters now also assert the old fact (`ASSERTED_BY {text, via}`); if the newer fact had superseded the old one (same agent, re-worded) the old one is current again. Needs the soft link and a current newer fact. |
| `reject_duplicate` | `new_id`, `old_id` | `{rejected, undone, restored}`. Deletes the soft link; on an already confirmed pair it undoes the merge. Idempotent. |

Both are write tools: a `ToolCall`, the agent's `Step` with `WROTE` edges to both facts and `UPDATED` audit edges. Errors
(`unknown fact`, `not linked as possible duplicates`, `no longer the current value`) are plain tool errors.

## Typed relations and `recall(hops)` (P9-b / P2, `plexus/mcp/tools_relations.py`, `plexus/engram/relations.py`)

| Tool | Arguments (besides `agent_id`, `step`) | Result |
|---|---|---|
| `assert_relation` | `subject`, `kind` (e.g. `depends on`, max 128 chars), `object`, `scope='global'`, `subject_kind='thing'`, `object_kind='thing'` | `{created, subject_id, object_id, kind, scope_id}`. Writes `(subject)-[:RELATES {kind, scope_id, at}]->(object)`; idempotent per (subject, kind, object, scope); the entities are resolved like `assert_fact`'s subject. A self-relation, an empty kind or an unknown scope id is refused and nothing (not even an Entity) is written. The audit `ToolCall` has `UPDATED` edges to both entities. |

`recall` gains `hops: 0|1|2 = 0`. With `hops >= 1` the entities of the `k` direct hits are expanded over `RELATES` (either direction,
relations visible from the scope or the scopes it inherits), level by level over distinct entities, and the **current** facts of the
entities reached are appended after the direct hits: at most 20 entities and 20 facts per hop, 3 facts per entity, each ranked behind
every direct hit (own distance + 0.25 per hop). Those rows carry `hop` (1|2) and `relation_path` (`[{from, kind, to, dir}]` from the
seed entity); direct rows are unchanged, and `hops=0` runs no extra query. A fact with no word or embedding overlap with the question
is found this way when a chain of relations leads to its entity (test: `tests/integration/test_p9b_relations.py`). The relations are only as
good as what agents write with `assert_relation`; Plexus extracts none by itself (no LLM). Relations are not time-versioned: with `as_of`
the facts follow the time filter but the edges are today's.
