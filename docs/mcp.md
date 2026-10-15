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
29 tools:
- **Engram:** `start_session`, `remember_episode`, `assert_fact` (optional `source_id`/`episode_id`), `recall` (returns
  `recall_id`), `fact_history`, `log_procedure_run`, `best_procedure`.
- **Relay:** `register_agent`, `create_tasks`, `claim_next_task`, `heartbeat`, `complete_task`, `fail_task`, `reopen_task`,
  `handoff`, `verify_artifact`, `record_decision`, `ready_tasks`, `task_status`, `blocked_by_failure`.
- **Lineage** (registered when `plexus.lineage` is installed; see `plexus/mcp/lineage_tools.py`): `add_source`, `why`,
  `why_recalled`, `who_knew`, `knew_at`, `as_of`, `forget_source`, `quarantine_source`, `release_quarantine`.

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

Every call is audited: the tool wrapper sums the database-reported `run_time_ms` of the queries the tool ran and then
writes one `ToolCall` (`audit/record_tool_call`) with `IN_STEP`/`CREATED`/`UPDATED` edges. Deliberate deviation from
PLAN §3 ("same statement"): the server-side time is only known after the tool's own statement has run.

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

Registered by `plexus/mcp/staleness_tools.py` (`register_staleness`), so the server now exposes 36 tools. Changing code makes a
memory **suspect**, never false: it stays recallable, and the agent re-checks it. Paths are normalised to the canonical form
(absolute, `/`, upper-case drive); a relative path is an error. Limits: ids <= 128, paths <= 1024, hashes <= 128, <= 200 changes.

| Tool | Arguments (besides `agent_id`, `step`) | What it does |
|---|---|---|
| `anchor_fact` | `fact_id`, `path`, `symbol=''`, `hash=''` | `(Fact)-[:ANCHORED_TO]->(CodeAnchor)` for a file or a Python function / class. Unknown fact: error, nothing written. |
| `describe_code` | `source_id`, `path`, `symbol=''`, `hash=''` | `(Source)-[:DESCRIBES]->(CodeAnchor)`: this doc describes this code. |
| `mark_changed` | `changes=[{path, symbol='', new_hash, old_hash='', kind?}]` (1..200), `commit=''`, `at=null` | The hook entry point. Active facts anchored to (or derived from a Source at) a changed file / symbol become `suspect`; returns `change_id`, `suspect_fact_ids`, `decisions` (+ `decisions_total`), `docs_to_update`, `unchanged`, `truncated`. A first sighting without `old_hash` is a baseline. |
| `verify_fact` | `fact_id`, `still_true`, `new_value=''`, `evidence=''`, `commit=''` | Confirmed: `verified`. Changed: the new value is asserted (supersede), the old fact ends at the time of the code change, decisions on the old fact are flagged. |
| `facts_to_verify` | `scope=''`, `limit=50` | Suspect facts (changed code or a passed review date), decisions-first, with reason, anchors and decision count. |
| `docs_to_update` | `since=0`, `limit=50` | Docs that describe code changed after the doc was last edited, with the commits / paths. |
| `set_review_date` | `fact_id`, `verify_after` (epoch ms) | Review date for facts no code change can invalidate; once passed the fact is suspect. |

Audit: facts a call made suspect or verified are `UPDATED` edges of the ToolCall and `WROTE` edges of the Step; a created `Change` /
`CodeAnchor` is a `CREATED` edge. `facts_to_verify` adds no `READ` edges (a suspect fact is not strengthened by being listed).
## Memory-strength tools (P7-K, `plexus/mcp/memory_tools.py`; D-012, `docs/forgetting.md`)

Five more tools, registered by `register_memory` (the "29 tools" above counts Engram, Relay and Lineage). Forgetting
lowers a fact's **rank only**; none of these deletes anything.

| Tool | Arguments (besides `agent_id`, `step`) | Result |
|---|---|---|
| `pin_fact` / `unpin_fact` | `fact_id` | `{fact_id, pinned}`. A pinned fact is never ranked below neutral and never swept. |
| `memory_strength` | `fact_id` | `{strength: {activation, a0, multiplier, floor, protected, protect_reasons, pinned, surprise, counts, last_use, last_recall, explanation, …}}`. Read-only: no `READ` edge, so asking is not using. |
| `memory_sweep` | `scope='global'`, `threshold=None` (−50..50), `dry_run=true`, `limit=200` (1..200) | `{sweep: {threshold, dry_run, scanned, candidates:[{fact_id, text, activation}], would_move, moved, skipped, truncated}}`. Moves to `dormant` only with `dry_run=false`; protected and suspect facts are never moved. |
| `restore_fact` | `fact_id` | `{fact_id, restored, status, was}`; a fact that is not dormant is left alone. |

`recall` gains `include_dormant: bool = false` and `forgetting: bool | null = null` (null = the server default,
`PLEXUS_FORGETTING`). Each fact in the result also carries `surprise`, `activation`, `protected` (both `null` when
forgetting is off), `verify_state`, `suspect_since` and `suspect_reason`. `assert_fact` returns `surprise`.
Audit: `pin_fact`, `unpin_fact`, `restore_fact` and a real `memory_sweep` record `UPDATED` edges to the facts they
changed; `ToolCall.query_name` of a forgetting-on `recall` is now its last read, `activation/activation`.
