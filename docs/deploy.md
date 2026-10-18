# Public deployment: one container on Render Free

One Docker image runs the public demo: FalkorDB 6.0.2, the read-only View API with its **Cypher console**, and the static
`knewat-view`. It reseeds the two synthetic demo tenants from the recordings on every boot, so it needs no disk and no
external database. **The MCP server is not deployed** until it is stable (decision record: `docs/DECISIONS.md` D-016, which
supersedes the MCP part of D-006). The earlier image that also served a public `/mcp` endpoint is in git history at `7cca016`;
its measurements (peak 332 MiB, 40 checks, 55 guard tests) described that image and are not repeated here.

```
Internet ──https──> Render (Cloudflare + proxy) ──> :$PORT (10000) inside the container
                      uvicorn, one process (deploy/app.py)
                        /                         static knewat-view (dist/, SPA fallback)
                        /healthz, /api/*, /docs   View API (FastAPI), per-IP rate limit
                        POST /api/{tenant}/cypher the Cypher console (own bucket, 16 KiB body cap)
                      redis-server + falkordb.so  127.0.0.1:6379   (never published, never bound to 0.0.0.0)
```

| File | What |
|---|---|
| `deploy/Dockerfile` | 4-stage build: Node builds the View, FalkorDB stage, Python venv, slim runtime (no embedding model) |
| `deploy/Dockerfile.dockerignore` | keeps the repo-root build context small |
| `deploy/entrypoint.py` | supervisor: start redis, wait `loading:0`, reseed, run uvicorn on `$PORT` |
| `deploy/app.py` | ASGI wrapper: View API + static files. No MCP route |
| `deploy/guard.py` | `ApiRateLimit` (GET bucket, POST/Cypher bucket and body cap); also holds the MCP guard classes the image does not use (D-016) |
| `deploy/smoke.py` | stdlib HTTP smoke test: used by CI against the image and by `live-smoke.yml` against the live URL |
| `deploy/verify.py` | the local gate: the image under Render's limits, memory, `smoke.py`, Cypher rate limit and timeout, restart |
| `deploy/tests/` | unit tests for the guard and the app wrapper (no database) |
| `deploy/bench_audit_modes.py` | scripted benchmark of the audit modes (`recall` throughput, no LLM), see `docs/mcp.md` "Audit modes" |
| `deploy/screenshots/` | the View served from the container (taken on the earlier image) |
| `render.yaml` | Render Blueprint |
| `.github/workflows/ci.yml`, `live-smoke.yml` | the pipeline below |

## The Cypher console

`POST /api/{tenant}/cypher` with `{"query": "...", "params": {...}}` (the View's **Cypher** page calls it). Response:
`columns`, `rows`, `row_count`, `truncated`, `run_time_ms`; nodes, edges and paths come back as objects with a `_type` key,
vector properties as `"<vector, 384 dims>"`. Errors are `{"detail": ...}`: 400 (invalid or refused Cypher, with the database's
message), 404 (unknown tenant), 408 (timed out), 413 (query over 4,000 characters, params over 8 KB, body over 16 KiB), 429
(rate limit, with `Retry-After`), 503 (database unavailable).

| Layer | Behaviour | Where |
|---|---|---|
| Rate limit | 20 queries/min per client IP, 120/min for everyone (429); GETs have their own bucket, 300/min per IP | `deploy/guard.py`; `KNEWAT_CYPHER_RATE_PER_MIN`, `KNEWAT_CYPHER_GLOBAL_RATE_PER_MIN`, `KNEWAT_API_RATE_PER_MIN` |
| Body cap | 16 KiB, on `Content-Length` and while streaming (413) | `KNEWAT_CYPHER_MAX_BODY_BYTES` |
| Text check | no `LOAD` (FalkorDB's `LOAD CSV` reads files and URLs); `CALL` only to `db.labels`, `db.relationshipTypes`, `db.propertyKeys`, `db.indexes`, `db.constraints`, the fulltext / vector `query*` procedures, `dbms.procedures` / `dbms.functions` and `algo.*`. Comments and string literals are skipped by a scanner, so a keyword hidden in either is no bypass | `knewat/src/knewat/api/routes_cypher.py` |
| Read-only server | `GRAPH.RO_QUERY`: the server refuses every `CREATE`, `SET`, `DELETE`, `MERGE`, `REMOVE` whatever the text says | `GraphClient.ro_text` |
| Time and memory | 3 s timeout per query (kept below the Redis client's 5 s socket timeout; at 5 s the client's timeout raced the server's reply and a runaway query sometimes showed as a 503); `QUERY_MEM_CAPACITY` 64 MB, 2 query threads | `routes_cypher.TIMEOUT_MS`, `FALKORDB_ARGS` |
| Result size | at most 500 rows leave the process (`truncated: true`) | `routes_cypher.MAX_ROWS` |

Not covered: an expensive but valid read (`algo.*`, a wide traversal) is bounded by the timeout and memory cap only, so a client
can keep a query thread busy until its bucket runs out; the demo graphs are about 250 nodes. Run locally, the console also reads
private tenants (`byo`) for whoever can reach port 8080. The container has no credentials and no LLM (D-002/D-003); the only
data is synthetic.

Other controls: redis binds `127.0.0.1` only; no AOF, no RDB; `--maxmemory 100mb` with `noeviction` (a full database refuses
writes, never evicts a graph); non-root user. The client IP comes from `CF-Connecting-IP` on Render (`RENDER=true`): confirmed
only from third-party reports of a live Render service, not on Render itself. Override with `KNEWAT_CLIENT_IP_HEADER` or
`KNEWAT_XFF_HOPS`.

## The pipeline

```
push / PR ──> .github/workflows/ci.yml ──> green ──> Render builds deploy/Dockerfile and deploys (autoDeployTrigger: checksPass)
                 python: ruff, View API + query + docs tests on a FalkorDB 6.0.2 service, deploy tests
                 view:   lint, typecheck, vitest, production build
                 image:  builds the Render image, runs it with -m 512m --cpus 0.5, runs deploy/smoke.py

every 10 min ──> .github/workflows/live-smoke.yml ──> deploy/smoke.py against $RENDER_URL (health check and keep-awake)
```

- A red CI run on a commit means Render does not deploy it; the previous deploy keeps serving.
- `buildFilter` in `render.yaml` skips the rebuild for pushes that touch only docs, tests or benchmark code.
- CI runs a targeted slice, not the 1,800-test suite or the benchmarks; those run on the owner's machine (`docs/TESTING.md`).
- The workflows have not run yet: the repo has no GitHub remote.

## Deploy on Render: click by click (owner)

Needs the repo on GitHub, **public** (hackathon requirement), with `.github/workflows/ci.yml` on `main`. The repo has no
remote yet: create the GitHub repo, then `git remote add origin <url>` and `git push -u origin main`. I could not create the
Render service (no account access); `render.yaml` follows Render's [Blueprint spec](https://render.com/docs/blueprint-spec) and
was never run on Render.

1. <https://render.com> → **Get Started** → **Sign up with GitHub**. A free web service should not ask for a card.
2. **New +** → **Blueprint** → connect the repo (use *Configure account* if it is not listed).
3. Branch `main`; Render finds `render.yaml` and shows one service, `knewat-demo`, plan **Free**. **Deploy Blueprint**.
4. The first build takes 5 to 10 minutes. In **Logs** wait for
   `reseeded 'acme-claude-sonnet' -> tenant 'demo': 247 nodes, 708 edges, matches meta.json=True` and `boot complete`.
5. The URL is at the top of the service page (normally `https://knewat-demo.onrender.com`). If it differs, edit
   `KNEWAT_CORS_ORIGINS` in **Environment** (only cross-origin callers need it; the View is same-origin).
6. Check it from your machine: `python deploy/smoke.py https://<host> --wait 600` (prints PASS or FAIL per check, exit 1 on failure).
7. **GitHub → Settings → Secrets and variables → Actions → Variables → New repository variable**: `RENDER_URL` =
   `https://<host>`. `live-smoke.yml` then pings the site every 10 minutes: a health check that also keeps the service awake
   (Render Free sleeps after 15 idle minutes; the first request after that takes about a minute).
8. Confirm the service's **Settings → Build & Deploy → Auto-Deploy** reads *After CI checks pass* (the Blueprint sets it).
   Roll back from the **Events** tab.

Free instance hours are 750 per workspace per month: one always-awake service uses about 744, so keep it the only free web
service. Check <https://render.com/docs/free> before relying on that. If the build fails with `Killed`, the free build machine
ran out of memory: build the image locally and use Render's prebuilt-image runtime, or take the D-006 fallbacks (Railway Hobby,
or a free VM with `docker compose`).

## Local verification (the gate)

```bash
docker build -f deploy/Dockerfile -t knewat-deploy .
cd knewat && uv run python ../deploy/verify.py          # runs the image under Render's limits; removes the container
cd knewat && uv run pytest ../deploy/tests -q -c ../deploy/tests/pytest.ini --rootdir ../deploy     # guard + app unit tests
python deploy/smoke.py http://127.0.0.1:10000            # against any running container
```

Measured on Windows 11 / Docker Desktop (WSL2), image `knewat-deploy` built from the working tree of the commit that adds this
section (base `7cca016`), `-m 512m --cpus 0.5`: **36/36 checks passed**, no traceback in the logs. Other containers were
running on the same host, so timings vary between runs.

| Check | Result |
|---|---|
| Boot, `docker run` to `/healthz?deep=1` = 200 | 3.8 s (4.5 s in an earlier run; the entrypoint reports 2.5 to 3.3 s) |
| Restart to healthy, both demo tenants reseeded | 4.2 s (25.8 s in an earlier run while the host was busy) |
| Demo tenants after boot | `demo` 247 nodes / 708 edges, `demo_scripted` 199 / 581 |
| Image size | 447 MB (510 MB before: the baked embedding model is gone) |
| Smoke (25 checks) | View, SPA fallback, tenants, inventory, graph, results, 404s, MCP not served; Cypher: counts per label agree with the inventory, node / edge / path values, `CALL db.labels()`, parameters, 500-row cap, `CREATE` / `SET` / `DELETE` / `LOAD CSV` / unlisted `CALL` refused, syntax errors a 400, unknown tenant a 404, GET a 405, `demo` unchanged afterwards |
| Runaway `MATCH (a),(b),(c),(d) RETURN count(*)` | 408 after 3 s; 10 in a row all 408; `/healthz` fine afterwards |
| 20 KiB body | 413 |
| 40 queries in a burst | 429 once the bucket empties, `Retry-After` present, the View API unaffected |
| Flow SSE | events delivered in 3 s |

Memory (limit 512 MiB): `docker stats` peak **83 MiB**, cgroup peak **88 MiB** after the rate-limit burst (python 63 MiB RSS,
redis 43 MiB). The earlier MCP image peaked at 322 MiB, almost all of it the embedding model, so this one has ample headroom on
Render's 512 MiB. `deploy/verify.py` prints every `MEM` snapshot and a final `REPORT` JSON.

## Open points

- **Not verified on Render itself:** the deploy, `autoDeployTrigger: checksPass` with GitHub Actions, `buildFilter`,
  `CF-Connecting-IP`. Render's CPU is shared and slower than a quiet 0.5 CPU slice, so expect a longer cold start there.
- `demo_scripted`, not `demo-scripted`: tenant names match `^[a-z0-9_]{1,48}$`.
- Reseed calls `knewat.demo.replay.replay(..., reset=True)` in-process and fails the boot if a restored inventory differs from
  the recording's `meta.json`. If redis exits, the process exits and Render restarts the container.
- Re-enabling MCP later: mount `build_server(...).streamable_http_app` behind `PublicGuard` in `deploy/app.py` (the classes are
  still in `deploy/guard.py`), restore the embedding-model bake in the Dockerfile, and re-measure.
