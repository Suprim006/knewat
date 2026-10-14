# Plexus MCP server

Entry point: `plexus-mcp` (`plexus.mcp.server:main`). Built on the `mcp` 2.x SDK (`mcp.server.mcpserver.MCPServer`),
pinned `mcp>=2.3,<3` (see `docs/spikes/S1-mcp-claude.md`).

| Transport | Command | Tenant binding |
|---|---|---|
| stdio | `uv run --directory <abs>/plexus plexus-mcp --transport stdio --tenant acme` | `--tenant` (or env `PLEXUS_TENANT`), fixed for the process. One process per Claude Code session. |
| streamable HTTP | `uv run plexus-mcp --transport http --port 8765` (compose service `plexus-mcp`) | URL path `/mcp/t/<tenant>` (or header `X-Plexus-Tenant` on `/mcp`), **pinned to the MCP session**: replaying a `mcp-session-id` under another tenant returns 403. |

The tenant is never a tool argument. It must match `^[a-z0-9_]{1,48}$` and selects the graph `plexus_t_<tenant>`; the
schema is applied once per tenant per process. The tenant in the URL is a routing identity, not authentication: keep the
port on loopback (compose publishes `127.0.0.1:8765` only) or put a token proxy in front.

DB connection: env `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_PASSWORD`. Embeddings: env `PLEXUS_EMBEDDER=fastembed|hash`
(`PLEXUS_EMBED_THREADS`, default 1; `PLEXUS_EMBED_CACHE` / `FASTEMBED_CACHE_PATH` for the model cache).
HTTP only: `PLEXUS_MCP_ALLOWED_HOSTS` (comma list, `host:*` = any port) for the Host-header allow-list.

## Claude Code

Local, stdio: `plexus.mcp.json` at the repo root (edit the absolute paths for your checkout). Headless:

```bash
env -u ANTHROPIC_API_KEY claude -p "<task>" --mcp-config <abs>/plexus.mcp.json --strict-mcp-config \
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
Engram: `start_session`, `remember_episode`, `assert_fact`, `recall`, `fact_history`, `log_procedure_run`, `best_procedure`.
Relay: `register_agent`, `create_tasks`, `claim_next_task`, `heartbeat`, `complete_task`, `fail_task`, `handoff`,
`verify_artifact`, `record_decision`, `ready_tasks`, `task_status`, `blocked_by_failure`.
Lineage (`why`, `why_recalled`, `who_knew`, `knew_at`, `as_of`, `forget_source`) is registered only when
`plexus.lineage` exists (see `plexus/mcp/lineage_tools.py`).

`scope` (assert_fact, recall, fact_history): `global` (default), `project:<name>`, `user:<name>` (both inherit `global`)
or a scope id. Named scopes are created on first use.

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
