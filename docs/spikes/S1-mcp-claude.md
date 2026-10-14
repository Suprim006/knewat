# S1: Python MCP server ↔ unmodified Claude Code (headless), Windows

**Verdict:** works on both transports with unmodified `claude` 2.1.296 in `-p` mode. Claude called both tools and returned the tenant-tagged results over stdio and over streamable HTTP. Spike code lives in `C:/Users/ACER/AppData/Local/hermes/cache/scratch/plexus-s1/` (throwaway; the full `server.py` is reproduced below).

Versions: `mcp 2.3.0` (+ `mcp-types 2.3.0`, `httpx2 2.13.1`), `starlette 1.8.0`, `uvicorn 0.54.0`, uv 0.12.5, Python 3.12, Claude Code 2.1.296, model `haiku` (`claude-haiku-5-5`).

## 0. Biggest gotcha: `mcp` 2.x is not `mcp` 1.x

`pip install mcp` now gives **2.3.0**, which breaks v1 code:

| v1 (most tutorials) | v2 (this spike) |
|---|---|
| `from mcp.server.fastmcp import FastMCP` → now raises `ModuleNotFoundError` with a migration hint | `from mcp.server.mcpserver import MCPServer, Context` |
| `FastMCP(...).streamable_http_app()` | `MCPServer(...).streamable_http_app(streamable_http_path="/mcp", stateless_http=False, ...)` returns a Starlette app |
| client uses `httpx` | client transport uses **`httpx2`** (`import httpx2`), and `streamable_http_client(url, http_client=...)` |

Pin it: `"mcp>=2.3,<3"` (or `<2` if we decide to stay on v1 docs). Tool decorators (`@mcp.tool()`), `ctx: Context` injection by annotation and `mcp.run("stdio")` are unchanged. A `str`-returning tool arrives at Claude as `{"result":"..."}` (structured output wraps scalars); the content text block is the plain string.

## 1. Server (`server.py`)

One file, both transports. Tenant binding: stdio = CLI arg bound once per process; HTTP = URL path `/mcp/t/<tenant>`, translated by a tiny ASGI middleware into an `x-plexus-tenant` header, which tools read through `ctx.headers`. The same tools also accept a client-sent `X-Plexus-Tenant` header on plain `/mcp` (no path), which is the alternative binding.

```python
"""S1 spike: MCP server with per-connection tenant binding (mcp 2.x MCPServer)."""
import argparse

from mcp.server.mcpserver import Context, MCPServer

TENANT_HEADER = "x-plexus-tenant"
mcp = MCPServer("plexus")
STDIO_TENANT: str | None = None  # bound once at process start (one process per connection)


def _tenant(ctx: Context) -> str:
    if STDIO_TENANT is not None:
        return STDIO_TENANT
    h = ctx.headers or {}
    t = h.get(TENANT_HEADER)
    if not t:
        raise ValueError("no tenant bound to this connection")
    return t


@mcp.tool()
def echo(text: str, ctx: Context) -> str:
    """Echo text back, tagged with the connection's tenant."""
    return f"tenant={_tenant(ctx)} echo={text}"


@mcp.tool()
def add(a: int, b: int, ctx: Context) -> str:
    """Add two integers, tagged with the connection's tenant."""
    return f"tenant={_tenant(ctx)} sum={a + b}"


class TenantPathMiddleware:
    """Pure ASGI: /mcp/t/<tenant> -> /mcp, tenant injected as x-plexus-tenant header
    (any client-supplied value is overwritten). The tenant is PINNED to the MCP session
    at initialize time; a request replaying that mcp-session-id under another tenant -> 403."""

    def __init__(self, app):
        self.app = app
        self.pins: dict[str, str] = {}  # mcp-session-id -> tenant

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/mcp/t/"):
            return await self.app(scope, receive, send)
        tenant = scope["path"][len("/mcp/t/"):].split("/", 1)[0]
        hdrs = [(k, v) for k, v in scope["headers"] if k.lower() != TENANT_HEADER.encode()]
        sid = next((v.decode() for k, v in hdrs if k.lower() == b"mcp-session-id"), None)
        if sid and self.pins.get(sid, tenant) != tenant:
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"session bound to another tenant"})
            return
        hdrs.append((TENANT_HEADER.encode(), tenant.encode()))
        scope = {**scope, "path": "/mcp", "raw_path": b"/mcp", "headers": hdrs}

        async def send_wrap(msg):
            if msg["type"] == "http.response.start" and not sid:
                for k, v in msg.get("headers", []):
                    if k.lower() == b"mcp-session-id":
                        self.pins[v.decode()] = tenant
            await send(msg)

        await self.app(scope, receive, send_wrap)


def main():
    global STDIO_TENANT
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    ap.add_argument("--tenant")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    if a.transport == "stdio":
        STDIO_TENANT = a.tenant or "default"
        mcp.run("stdio")
    else:
        import uvicorn

        app = TenantPathMiddleware(mcp.streamable_http_app(streamable_http_path="/mcp"))
        uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="info")


if __name__ == "__main__":
    main()
```

Project setup: `UV=~/AppData/Roaming/Python/Python311/Scripts/uv.exe; $UV init --bare --python 3.12 . && $UV add mcp uvicorn`.

## 2. stdio

`mcp_stdio.json` (absolute paths, forward slashes, no `~`, no `%VAR%`):

```json
{
  "mcpServers": {
    "plexus": {
      "command": "C:/Users/ACER/AppData/Roaming/Python/Python311/Scripts/uv.exe",
      "args": ["run", "--directory", "C:/Users/ACER/AppData/Local/hermes/cache/scratch/plexus-s1",
               "python", "server.py", "--tenant", "acme"]
    }
  }
}
```

```bash
D=C:/Users/ACER/AppData/Local/hermes/cache/scratch/plexus-s1
env -u ANTHROPIC_API_KEY claude -p "Call the plexus echo tool with text hello, then add 2 and 3. Reply with both results." \
  --mcp-config $D/mcp_stdio.json --allowedTools "mcp__plexus__echo,mcp__plexus__add" \
  --max-turns 5 --model haiku --output-format stream-json --verbose > s1_stdio.jsonl
```

Result (run 1): exit 0, `result.subtype=success`, 4 turns, **tenant=acme in both results**: `tenant=acme echo=hello`, `tenant=acme sum=5`. `system/init` → `mcp_servers` entry `{"name":"plexus","status":"connected","source":"dynamic"}`; tools listed as `mcp__plexus__add`, `mcp__plexus__echo`. No stderr output. Wall time 17.5 s (Claude's `duration_ms` 5.5 s; the ~12 s difference is CLI start-up plus connecting every ambient MCP server, plus `uv run` spawning the venv Python). Cost $0.0048.

## 3. Streamable HTTP

Start the server (background; keep it running):

```bash
cd C:/Users/ACER/AppData/Local/hermes/cache/scratch/plexus-s1
~/AppData/Roaming/Python/Python311/Scripts/uv.exe run python server.py --transport http   # 127.0.0.1:8765
```

`mcp_http.json`, tenant in the **path**:

```json
{ "mcpServers": { "plexus": { "type": "http", "url": "http://127.0.0.1:8765/mcp/t/acme" } } }
```

`mcp_http_hdr.json`, tenant in a **header** (also worked; header passes through plain `/mcp`):

```json
{ "mcpServers": { "plexus": { "type": "http", "url": "http://127.0.0.1:8765/mcp",
                              "headers": { "X-Plexus-Tenant": "globex" } } } }
```

Claude config key is `"type": "http"` (streamable HTTP); `"sse"` is the legacy transport.

Results:

| Run | Config | Flags | Outcome |
|---|---|---|---|
| 2 | `mcp_http.json` (path, tenant acme) | `--allowedTools "mcp__plexus__*"` | success, 4 turns, `tenant=acme` ×2, wall 9.8 s, `duration_ms` 5.2 s, $0.0014 |
| 3 | `mcp_http_hdr.json` (header, globex) | `--strict-mcp-config`, **no** `--allowedTools` | tools **denied** (see §4) |
| 4 | `mcp_http_hdr.json` | `--strict-mcp-config --allowedTools "mcp__plexus__*"` | success, 4 turns, `tenant=globex` ×2, wall 7.9 s, `duration_ms` 6.0 s, $0.0012 |

`init` shows `plexus` `status: connected` in all HTTP runs. Server log shows plain `POST /mcp 200` (the path is rewritten internally, so access logs don't show the tenant segment).

## 4. Permissions and wildcard

- **`--allowedTools "mcp__plexus__*"` works** (runs 2 and 4). Comma-joined exact names also work (run 1). Quote the argument so git-bash doesn't glob it.
- **A `--permission-mode` is not needed if `--allowedTools` covers the tools.** Default mode is `default` (`init.permissionMode`).
- **Without `--allowedTools`, MCP tools are blocked in `-p` mode** (nothing to prompt): the tool result is `Claude requested permissions to use mcp__plexus__echo, but you haven't granted it yet.` (`is_error: true`), `result.permission_denials` lists both calls, exit code is still 0 and `subtype` is still `success`. A harness must check `permission_denials` and the `is_error` flag, not just the exit code.
- Tool-name format: `mcp__<server key in mcp.json>__<tool>` → `mcp__plexus__echo`, `mcp__plexus__add`. Server key `plexus` is what matters; the FastMCP/`MCPServer` name is irrelevant to this.
- Haiku first calls the built-in `ToolSearch` (`select:mcp__plexus__echo,mcp__plexus__add`) to load the deferred MCP tool schemas, then calls the tools. That costs a turn: the 2-call task took **4 turns**, so `--max-turns 5` leaves just one spare. Use ≥ 8 for real work.

## 5. Tenant binding: what worked, and the replay caveat

| Transport | Binding | Evidence |
|---|---|---|
| stdio | `--tenant acme` argv → module global. One process per Claude connection, so it is truly per-connection. | run 1 |
| HTTP path | `/mcp/t/<tenant>` → ASGI middleware → `x-plexus-tenant` header → `ctx.headers` in the tool | run 2; SDK client check |
| HTTP header | `headers` in mcp.json → `ctx.headers` | run 4; SDK client check |

`ctx.headers` (mcp 2.x `Context.headers`) returns the headers of the *current* request, so it is correct per call even with concurrent clients; I used it rather than a `ContextVar` set in middleware because the stateful session task is created at `initialize` and would otherwise see stale contextvars (not tested, avoided).

**Caveat found with curl (SDK default = stateful sessions):** the tenant is evaluated **per request, not per session**. Initialize on `/mcp/t/acme`, then replay the returned `mcp-session-id` against `/mcp/t/evil` → the tool ran as `tenant=evil`. The `TenantPathMiddleware` above fixes this by pinning `session-id → tenant` at initialize and returning **403** on mismatch (verified with curl: same session on `acme` → 200, on `evil` → 403; SDK client on `acme` still works). The header variant is not pinned; if used, apply the same pin. The pin map is in-memory (lost on restart, which also drops the SDK sessions). **Not re-run through Claude after adding the pin** (run budget); the SDK-client and curl checks cover it, and Claude's runs 2 and 4 used the identical protocol path minus the pin.

Note this is a *routing* identity only. The tenant in the URL is not authenticated: anyone who can reach the port can claim any tenant. For Plexus, bind to `127.0.0.1` only (done) and, if it ever leaves loopback, add a token (`headers: {"Authorization": "Bearer ..."}` is supported in mcp.json, and the server can map token → tenant instead of trusting the path).

## 6. Gotchas (Windows / tooling)

- **mcp 2.x API rename** (§0). Also the transport dependency is `httpx2`, not `httpx`.
- **Paths in `mcp.json`:** use absolute `C:/...` with forward slashes (valid JSON, no escaping). The `uv` command must be absolute: `~` and `$UV` are not expanded in the JSON. `uv run --directory <dir>` makes the server independent of Claude's cwd.
- **Env handling:** `env -u ANTHROPIC_API_KEY claude ...` (git-bash) works to force subscription auth. stdio servers inherit Claude's environment.
- **stdout is the protocol channel for stdio:** never `print()` in the server (logging goes to stderr). Nothing was printed in the spike, and stderr stayed empty.
- **Ambient MCP servers load too.** Without `--strict-mcp-config`, `init.mcp_servers` had **37** entries (user plugins and claude.ai connectors, many `needs-auth`/`failed`) and ~12 s of start-up overhead. `--strict-mcp-config` → exactly 1 entry (`plexus`) and runs 3–4 were ~8–9 s wall. Use it for any scripted run, both for speed and for isolation (the model can't wander into Slack/Gmail tools).
- **Shell backgrounding:** the Hermes terminal tool rejects a trailing `&`; start the HTTP server with its `background=true` option. `uv run` leaves a parent `uv.exe` plus the Python child, so the listener PID (`netstat -ano | grep 8765`) is not the PID the launcher reports; kill with `taskkill /PID <pid> /T /F` (single slash; `//PID` is only for MSYS-converted shells and fails here).
- **Exit code lies:** a permission denial still exits 0 / `success` (§4). Parse `stream-json` (`type=result`, `permission_denials`, `tool_result.is_error`).
- `stream-json` requires `--verbose` with `-p` (as in the command above).
- **First stdio connect** pays a `uv run` env check on every launch (~1–2 s). If this matters, call `.venv/Scripts/python.exe server.py` directly as `command` (not tested).

## 7. Recommended setup for Plexus

1. **Transport:** use **stdio** for the headless Claude Code agent runs (one server process per Claude session, `--tenant <id>` argv gives hard per-connection isolation, no ports, no auth surface). Use **streamable HTTP** (`/mcp/t/<tenant>` + session pinning, loopback only) for the long-lived Plexus service / View API process that other clients share, so there is no per-session start-up cost.
2. **Server:** `from mcp.server.mcpserver import MCPServer, Context`; pin `mcp>=2.3,<3`. Resolve tenant in a single `_tenant(ctx)` helper that every tool calls; never accept `tenant` as a tool argument (the model could set it).
3. **Config:** generate `mcp.json` per run in code (json.dump, absolute forward-slash paths) so the tenant is baked in; keep the server key `plexus` so tools are `mcp__plexus__<tool>`.
4. **Invocation template:**
   ```bash
   env -u ANTHROPIC_API_KEY claude -p "<prompt>" --mcp-config <abs mcp.json> --strict-mcp-config \
     --allowedTools "mcp__plexus__*" --max-turns 8 --model haiku --output-format stream-json --verbose
   ```
   Add `--permission-mode` only if non-MCP tools (Bash/Edit) are needed; it was not needed for MCP tools.
5. **Harness checks:** after the run assert on `system/init` (`plexus` is `connected`), `result.subtype == "success"`, `permission_denials == []`, and that each expected `mcp__plexus__*` `tool_use` has a non-error `tool_result`.
6. **Budget:** expect ~8–10 s wall per headless run with `--strict-mcp-config`, ~$0.001–0.005 on haiku for a 2-tool task.

## Runs used

4 Claude runs total (stdio ×1, HTTP-path ×1, HTTP-header ×2 incl. the permission-denied probe), all haiku, ≤ 5 turns, `ANTHROPIC_API_KEY` unset. Total cost ≈ $0.011.
