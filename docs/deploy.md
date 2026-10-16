# Public deployment: one container on Render Free

One Docker image runs everything the live demo needs: FalkorDB 6.0.2, the read-only View API, the MCP server over
streamable HTTP (for "bring your own agent") and the static `plexus-view`. It reseeds the demo tenants from the
recordings on every boot, so it needs no disk and no external database. Decision record: `docs/DECISIONS.md` D-006.

```
Internet ──https──> Render (Cloudflare + proxy) ──> :$PORT (10000) inside the container
                      uvicorn, one process (deploy/app.py)
                        /                      static plexus-view (dist/, SPA fallback)
                        /healthz, /api/*       View API (GET only), per-IP rate limit
                        /mcp, /mcp/t/<tenant>  PublicGuard -> TenantPathMiddleware -> MCP streamable HTTP
                      redis-server + falkordb.so  127.0.0.1:6379   (never published, never bound to 0.0.0.0)
```

Files (all under the P6 ownership; nothing in `plexus/src` or `plexus-view` is changed):

| File | What |
|---|---|
| `deploy/Dockerfile` | 4-stage build: Node builds the View, FalkorDB stage, Python venv + baked model, slim runtime |
| `deploy/Dockerfile.dockerignore` | keeps the repo-root build context small |
| `deploy/entrypoint.py` | supervisor: start redis, wait `loading:0`, reseed, start the sweeper thread, run uvicorn on `$PORT` |
| `deploy/app.py` | ASGI wrapper that mounts the View API, the MCP app and the static files |
| `deploy/guard.py` | public-safety middleware and the idle sweeper |
| `deploy/verify.py` | the local gate (below); `deploy/tests/` = unit tests for the guard (55, no database) |
| `deploy/bench_audit_modes.py` | scripted benchmark of the audit modes (`recall` throughput, no LLM), see `docs/mcp.md` "Audit modes" |
| `deploy/screenshots/` | the View served from the container under `-m 512m --cpus 0.5` |
| `render.yaml` | Render Blueprint (Docker web service, free plan, `/healthz`) |

## Image: why `python:3.12-slim` + files copied from the FalkorDB image

`falkordb/falkordb:6.0.2` is 488 MB (Debian 13, redis, `falkordb.so`, and a bundled Node browser) and has no Python, so
building `FROM` it would still add about 250 MB of Python, uv and ML wheels (about 740 MB). `redis-server` (4.9 MB) and
`falkordb.so` (62 MB) only need libssl3, libz, libzstd and libstdc++, which `python:3.12-slim` (same Debian 13,
digest-pinned like `plexus/Dockerfile`) already has. So the runtime stage copies just those two files out of the official
image: same module build, same redis 8.10.2, no browser. **Final image: 510 MB on disk.** The runtime runs as uid 10001.

## Deploy on Render: click by click (owner)

Needs a GitHub account with this repo **public** (hackathon requirement) and the `p6-deploy` work merged to `main`.
I could not create the service (no Render account access), so these steps follow Render's dashboard and
[Blueprint docs](https://render.com/docs/blueprint-spec); `render.yaml` was validated against Render's published JSON
schema (0 errors) but never run on Render.

1. Go to <https://render.com> → **Get Started** → **Sign up with GitHub** and authorize Render. Free web services do not
   ask for a card (D-006; if Render asks for one for your account, stop and use the fallback at the end).
2. Dashboard → **New +** → **Blueprint**.
3. **Connect a repository**: pick `<you>/<repo>` (use *Configure account* if the repo is not listed, grant it access).
4. Branch: `main`. Render finds `render.yaml` in the repo root and shows one service, `plexus-demo`, plan **Free**.
5. Click **Deploy Blueprint**. The first build takes about 5 to 10 minutes (npm + uv + a 67 MB model download). Open the
   service → **Logs** and wait for:
   `reseeded 'acme-claude-sonnet' -> tenant 'demo': 247 nodes, 708 edges, matches meta.json=True` then
   `boot complete in …s; serving on 0.0.0.0:10000` and Render's `Your service is live`.
6. The URL is at the top of the service page, normally `https://plexus-demo.onrender.com` (a suffix is added if the name
   is taken). If it differs, edit `PLEXUS_CORS_ORIGINS` in **Environment** to your URL (only needed for cross-origin
   callers; the View itself is same-origin).
7. Check it:
   ```bash
   curl -s https://<host>/healthz                       # {"status":"ok"}
   curl -s https://<host>/api/tenants                   # demo, demo_scripted
   curl -s https://<host>/api/demo/inventory | head -c 200
   ```
   then open `https://<host>/` in a browser: Explorer, Flow, Time Machine, Why, Inventory and Results load the `demo` tenant.
8. **Keep it awake.** Render Free spins a service down after 15 minutes without inbound traffic and wakes it on the next
   request (about a minute, plus the reseed). A restart or redeploy also drops every `team_*` graph (no disk). To avoid
   the cold start during judging, add an external pinger (free, no card):
   - **UptimeRobot** (<https://uptimerobot.com>): sign up → **+ New monitor** → type **HTTP(s)** → URL
     `https://<host>/healthz` → interval **5 minutes** (the free plan's minimum; anything under 15 works) → **Create monitor**.
   - or **cron-job.org**: **Create cronjob** → URL `https://<host>/healthz` → schedule *every 10 minutes* → **Create**.

   Free instance hours are 750 per workspace per month: one always-awake service uses about 744, so keep this the only
   free web service in the workspace. Check <https://render.com/docs/free> before relying on that after Oct 2026.
9. **Updating:** push to `main`; `autoDeployTrigger: commit` redeploys. Roll back from the service's **Events** tab.

Manual setup instead of the Blueprint: **New + → Web Service → Public Git Repository** → paste the repo URL → Language
**Docker** → Branch `main` → **Dockerfile Path** `./deploy/Dockerfile`, **Docker Build Context Directory** `.` →
Instance Type **Free** → **Advanced**: Health Check Path `/healthz`, add the env vars from `render.yaml` → **Create Web Service**.

Connect an agent (the public MCP endpoint, write tenant of your choice `team_` + 4 to 24 of `a-z0-9`):

```bash
claude mcp add --transport http plexus https://<host>/mcp/t/team_alice01
```
```json
{ "mcpServers": { "plexus": { "type": "http", "url": "https://<host>/mcp/t/team_alice01" } } }
```

If the build or memory fails on Render, the D-006 fallbacks apply (Railway Hobby, or an always-free VM with
`docker compose`); a build error with `Killed` means the free build machine ran out of memory: build the image locally
and use Render's prebuilt-image runtime, or deploy elsewhere.

## Public safety

The MCP endpoint is public, so the wrapper is deny-by-default. Implemented in `deploy/guard.py`, unit-tested
(`deploy/tests/test_guard.py`) and exercised against the real container (`deploy/verify.py`).

| Control | Behaviour | Env var (default) |
|---|---|---|
| Write tenants | only `team_[a-z0-9]{4,24}` may be written through MCP | n/a |
| Readable, read-only demo tenants | `demo` and `demo_*`: the handshake and `tools/list` work, and a `tools/call` of one of the 14 **read tools** (`OBSERVER_TOOLS`: `recall`, `fact_history`, `as_of`, `why`, `why_recalled`, `who_knew`, `knew_at`, `ready_tasks`, `task_status`, `blocked_by_failure`, `best_procedure`, `memory_strength`, `facts_to_verify`, `docs_to_update`) is forwarded. Any other call is answered with a one-line tool error ("read-only demo tenant: writes are disabled; reads are allowed … connect to /mcp/t/team_<name>") and never reaches Plexus; so is a JSON-RPC batch. Enforcement is two gates: the allowlist here, and the runtime, which serves `demo*` in audit mode **`off`** (`deploy/app.py` puts `demo*=off` first in `PLEXUS_AUDIT_MODES`): a read writes nothing at all (no Step, no `ToolCall`, no `READ` edge, so a visitor cannot change ranking), a write is refused, and the database client is read-only. A test keeps the allowlist equal to the set of tools declared `kind="read"`. | `PLEXUS_AUDIT_MODES` (`demo*=off` forced) |
| No graph creation by a request | a `demo*` tools/call is forwarded only if that tenant's graph already exists (the guard's graph listing), and the runtime refuses an `off` tenant without a graph instead of applying the schema. `/mcp/t/demo_x1` creates nothing, whatever the name. | n/a |
| Demo read rate | a `recall` embeds its query (about 47/s for the whole process, `docs/BASELINE.md`), so forwarded demo reads spend a second, smaller bucket: 30/min per client IP and 120/min in total, 429 with `Retry-After`. Handshakes and refused writes do not spend it. | `PLEXUS_DEMO_RATE_PER_MIN` (30), `PLEXUS_DEMO_GLOBAL_RATE_PER_MIN` (120) |
| Everything else | any other tenant name: 403 with the allowed pattern | n/a |
| Rate limit | token bucket per client IP on `/mcp` (60 requests/min, burst 60), plus a global bucket (600/min) as backstop; 429 with `Retry-After`. `/api` has its own bucket (300/min per IP). The SSE stream counts once when it opens. | `PLEXUS_RATE_PER_MIN`, `PLEXUS_GLOBAL_RATE_PER_MIN`, `PLEXUS_API_RATE_PER_MIN` |
| Body cap | 512 KiB: `Content-Length` and streamed bodies, 413 (the SDK's own cap is set to the same value) | `PLEXUS_MAX_BODY_BYTES` (524288) |
| Graph cap | at most 50 tenant graphs (demo ones count); a request for a new `team_` tenant over the cap gets 503, existing tenants keep working | `PLEXUS_MAX_TENANTS` (50) |
| Idle sweep | a thread deletes `team_*` graphs with no MCP traffic for 24 h, every 10 min. `demo*` is never swept. | `PLEXUS_TEAM_IDLE_HOURS` (24), `PLEXUS_SWEEP_INTERVAL_S` (600) |
| MCP sessions | idle timeout 10 min, at most 200 open sessions, at most 64 concurrent connections | `PLEXUS_MAX_CONCURRENCY` (64) |
| Database | redis binds `127.0.0.1` only (the single published port is the app's `$PORT`); no AOF, no RDB; `--maxmemory 100mb` with `noeviction` (a full database refuses writes, it never evicts a graph or kills the container); FalkorDB `QUERY_MEM_CAPACITY` 64 MB, 2 query threads, 100 queued queries | `PLEXUS_REDIS_MAXMEMORY` (100mb), `FALKORDB_ARGS` |
| Process | non-root user; `MALLOC_ARENA_MAX=2`; embeddings on 1 thread (S2) | `PLEXUS_EMBED_THREADS`, `FASTEMBED_THREADS` (1) |

What this does **not** do, on purpose or by limitation:

- **Tenant names are routing, not authentication.** Anyone who knows `team_alice01` can read and write it, and the View
  lists every tenant, so everything in a `team_*` graph is public. Tell users to put nothing private in it.
- **The client IP is only as good as the proxy.** On Render (`RENDER=true`) the guard reads `CF-Connecting-IP`, which
  Cloudflare sets and overwrites. I confirmed that from third-party reports of a live Render service, not on Render
  itself, and a custom domain may differ. Override with `PLEXUS_CLIENT_IP_HEADER` or `PLEXUS_XFF_HOPS` (the Nth
  `X-Forwarded-For` entry from the right; Render sends `<client>, <cloudflare>, <internal>`, so 3). If the header is
  missing the guard falls back to the socket peer, and the global bucket still caps total load.
- **No per-tenant size limit.** A `team_*` tenant can fill the 100 MB database; the effect is that all `team_*` writes
  start failing until the idle sweep or a restart frees space. Demo reads keep working. (Not exercised in the gate.)
- The MCP SDK's DNS-rebinding Host allow-list is **off** (`deploy/app.py`): it protects loopback servers from browsers,
  and a public service is reached under whatever hostname the platform gives it.
- There are no credentials of any kind in the container, and no LLM (D-002/D-003): embeddings come from the baked local
  model. The only data is synthetic (the Acme recordings) plus whatever visitors write.

## Local verification (the gate)

```bash
docker build -f deploy/Dockerfile -t plexus-deploy .
docker run --rm -d --name plexus-deploy-test -m 512m --cpus 0.5 -e PORT=10000 -p 127.0.0.1:18100:10000 plexus-deploy
# or run the whole gate, which does exactly that and then the checks below, and removes the container:
cd plexus && uv run python ../deploy/verify.py
cd plexus && uv run pytest ../deploy/tests -q -c ../deploy/tests/pytest.ini      # guard unit tests (55)
```

Run on Windows 11 / Docker Desktop (WSL2, 12 logical CPUs on the host, capped to 0.5 CPU for the container), image
`plexus-deploy` with the image contents of commit `c9234d8`. **40/40 checks passed**, and nothing in the container logs was an
error. Other agents were using the same Docker host while this ran, so timings vary between runs (ranges given).

| Check | Result |
|---|---|
| Boot, `docker run` to `/healthz?deep=1` = 200 | **5.1 s, 7.5 s, 8.0 s, 14.4 s** over four runs (the entrypoint itself reports 3.4 to 8.2 s: redis ready in about 1.5 s, both reseeds in under 0.1 s, the rest is Python imports on 0.5 CPU) |
| Restart (`docker restart`) to healthy, demo reseeded | 5.2 to 12.1 s |
| `demo` tenant after boot | 247 nodes / 708 edges, `demo_scripted` 199 / 581: identical to the recordings' `meta.json` |
| `/` and `/explorer` | View HTML (SPA fallback), hashed JS asset 200, unknown file 404 |
| Explorer / Flow / Time Machine / Why / Inventory / Results data | `/api/demo/graph` (247 nodes, 708 edges), `/flow` (83 tool calls), `/step/1`, `/why/<decision>`, `/recall/<id>`, `/inventory`, `/api/results`: all 200 with data. `/api/demo/stream` SSE delivered 83 events in 3 s |
| Headless browser | the real View pages rendered from the container: `deploy/screenshots/{explorer,flow,why,inventory}.png` (Explorer shows "51 of 247 nodes", Why shows a decision with its facts, agents, steps and sources) |
| MCP on `/mcp/t/team_test01` (mcp SDK client) | `start_session`, `assert_fact`, `recall` all succeed (29 tools listed); the recalled fact is the one just asserted; first recall 0.03 to 0.09 s with the model prewarmed |
| 4 concurrent agents, own tenants, 5 `assert_fact` + 3 `recall` each | 32/32 calls ok in 3.7 to 4.7 s |
| Write to `/mcp/t/demo` | rejected with the read-only message; `demo` still 247/708 afterwards |
| `/mcp/t/acme`, `team_x`, `default` | 403 |
| Body 600 KiB | 413 |
| Rate limit | 429 after 53 to 55 requests of a 90-request burst from one IP, `Retry-After` present, View API unaffected |
| Restart | demo tenants reseeded, `team_test01` gone (ephemeral by design) |
| Graph cap (second container, `PLEXUS_MAX_TENANTS=4`) | the 3rd `team_` tenant gets 503, existing ones keep working, after the sweep a new one fits |
| Idle sweep (second container, idle limit 6 s, sweep every 4 s) | both idle `team_` graphs deleted from the real FalkorDB, `demo`/`demo_scripted` untouched |
| Ports | redis listens on `127.0.0.1:6379` only; the app on `0.0.0.0:10000`; `docker port` shows only `10000` |

### Memory (limit 512 MiB)

| Moment | `docker stats` (cgroup, excl. cache) | cgroup peak | RSS python / redis |
|---|---|---|---|
| just after healthy (model loading in the background) | 75 to 106 MiB | 114 to 172 MiB | 110 / 40 MiB |
| idle, embedding model prewarmed | 299 to 316 MiB | 317 to 322 MiB | 333 to 335 / 40 to 41 MiB |
| after the first MCP `recall` | 305 to 316 MiB | 317 to 322 MiB | 336 / 45 to 46 MiB |
| after 4 concurrent agents, 20 writes + 12 recalls | 312 to 322 MiB | 320 to 332 MiB | 336 to 337 / 52 to 54 MiB |
| after the 90-request rate-limit burst | 314 to 322 MiB | 321 to 332 MiB | 335 to 337 / 52 MiB |

**Peak: 322 MiB by `docker stats` and 332 MiB by cgroup `memory.peak` (sum of both processes' RSS: 391 MiB, which
double-counts shared pages), against the 480 MiB threshold in the spec and the 512 MiB limit.** FalkorDB holds 17.5 MiB of
graph data for the two demo tenants (`INFO memory`), so redis stays at 40 to 54 MiB RSS. The cost is the Python process
(about 335 MiB), almost all of it the fastembed model plus onnxruntime (S2 measured 265 to 285 MiB for the model alone).
No fallback from D-006 is needed. Headroom is about 150 MiB; if Render's own accounting turns out higher, set
`PLEXUS_PREWARM=0` (the model then loads on the first tool call, no change to the steady state), lower
`PLEXUS_REDIS_MAXMEMORY`, or take the D-006 fallbacks.

Reproduce the raw numbers: `deploy/verify.py` prints every `MEM` snapshot and a final `REPORT` JSON.

## Deviations from the spec, and open points

- **`demo_scripted`, not `demo-scripted`.** A tenant name must match `^[a-z0-9_]{1,48}$` (`plexus/graph/tenancy.py`), so a
  hyphen is invalid.
- **Demo tenants are readable over MCP, writes refused (P9-e).** Before, every `tools/call` on `demo*` was refused
  because each call wrote an audit node; the audit modes (`docs/mcp.md`) give reads a no-write path (mode `off`), so a visitor's
  agent can `recall`, ask `why` and `as_of` against the demo graph. Not verified in the container (`verify.py` was not
  re-run for P9-e: it needs Docker and the full image); the unit tests (`deploy/tests`), the runtime tests and the Redis
  commandstats proof (`plexus/tests/mcp/test_audit_modes.py`) cover it. `verify.py`'s existing check (an `assert_fact`
  on `/mcp/t/demo` is refused with the read-only message and the graph is unchanged) still holds.
- **Reseed calls the same function the CLI does** (`plexus.demo.replay.replay(..., reset=True)`) in-process, instead of
  spawning `plexus demo replay` twice: one Python process instead of three saves boot time and memory on 0.5 CPU. It
  fails the boot if a restored inventory differs from the recording's `meta.json`.
- One Python process runs the app, the sweeper thread and the redis supervisor. If redis exits, the process exits and
  Render restarts the container (which reseeds).
- Added beyond the spec: a global rate bucket, an `/api` rate limit, `maxmemory`, a connection cap, MCP session caps.
- Not verified: the deployment on Render itself (no account access), `CF-Connecting-IP` there, the `maxmemory` refusal path.
- Chart numbers come from one machine; Render's CPU is shared and slower than a quiet 0.5 CPU slice, so expect a longer
  cold start there (it also pulls the 510 MB image).
