# Plexus

One shared graph brain for AI agent teams, the memory and coordination layer that Claude Code, Hermes and other
harnesses lack. Agents connect over MCP. Every memory, task, handoff and decision is a node in FalkorDB, so the
team remembers across sessions, works without stepping on each other, and can always answer *"why?"* and *"what
did we know then?"*

Built for Graph Hacks (WeMakeDevs × FalkorDB), **Track 02: Agent Memory and Coordination**.

## Setup

You need **Docker with Compose v2** and nothing else (no Python, no Node). About 3 GB of images are built the first time.

```bash
git clone <this repo> plexus && cd plexus
cp .env.example .env                    # optional: the defaults work; edit it only if a host port below is already taken
docker compose up -d --wait             # builds and starts FalkorDB 6.0.2, the View API, the MCP server and the View
docker compose run --rm plexus-cli demo replay acme-claude-sonnet --tenant demo    # load the recorded real Claude Code run
```

| Open | What |
|---|---|
| http://localhost:5180 | **The View.** Pick tenant `demo` in the header: Explorer, Flow, Time Machine, Why, Inventory and **Results** (the Crucible benchmark: L1, L2, L4, ablation) |
| http://localhost:3000 | FalkorDB Browser (the raw graph: graph `plexus_t_demo`) |
| http://localhost:8080/api/tenants | the read-only View API (`/api/demo/inventory`, `/api/demo/graph`, `/api/results`, ...) |
| http://localhost:8765/mcp/t/demo | the MCP server (streamable HTTP, tenant `demo` pinned by the path) |

The replay restores a recording of three unmodified Claude Code agents (planner, researcher, builder) building a fictional
"Acme Notes API": 247 nodes, 708 edges. `docker compose run --rm plexus-cli demo list` shows the other recordings.
Ports are `FALKORDB_PORT`, `FALKORDB_BROWSER_PORT`, `PLEXUS_API_PORT`, `PLEXUS_MCP_PORT` and `PLEXUS_VIEW_PORT` in `.env`; after
changing `PLEXUS_API_PORT` or `PLEXUS_VIEW_PORT` run `docker compose up -d --build` (the View bakes the API address into its bundle).

**More to try** (all synthetic data; no LLM and no credentials are involved in any of it):

```bash
# watch the Flow page while scripted agents play the whole scenario (builder killed, task reclaimed, style guide v1 -> v2)
docker compose run --rm plexus-cli demo live --scripted --tenant live --speed 4
# cut DEPENDS_ON / BASED_ON / DERIVED_FROM / READ in a copy of the tenant and see which features break (docs/demo.md)
docker compose run --rm plexus-cli demo ablation --tenant demo
# connect your own Claude Code to the running MCP server (tools: recall, why, knew_at, claim_next_task, ...)
claude mcp add --transport http plexus http://127.0.0.1:8765/mcp/t/demo
# the benchmark itself (L1 + L4 + ablation; ~20 min full, --quick ~2 min): results land in plexus/src/plexus/crucible/results/
docker compose --profile bench run --rm crucible all --quick
docker compose down -v                  # stop and delete everything
```

The Results page reads `plexus/src/plexus/crucible/results/latest-all.json` (L1 + L4 + ablation from the compose run, merged with
the full L2 run), mounted into the API as `PLEXUS_RESULTS_PATH`. `docs/BASELINE.md` explains what each number means and what it does not.

<details><summary>Without Docker for the app (Python 3.12 + <code>uv</code>, Node 22+): contributors and the full test suite</summary>

```bash
docker compose up -d falkordb                       # or scripts/agent_db.sh <slot> for a throw-away test database
cd plexus && uv sync
FALKORDB_PORT=6379 uv run plexus demo replay acme-claude-sonnet --tenant demo
FALKORDB_PORT=6379 uv run plexus-api &             # View API on :8080
cd ../plexus-view && npm ci && npm run dev         # View on http://localhost:5180 (VITE_FIXTURES=1 for the built-in dataset)
cd ../plexus && uv run plexus mcp-config --tenant demo   # an MCP config for Claude Code for this checkout (docs/mcp.md)
```

Quick dev loop (see `docs/PLAN.md` and `CLAUDE.md`; the full gate and the owner's manual checklist are in `docs/TESTING.md`):

```bash
bash scripts/agent_db.sh 10                                   # FalkorDB 6.0.2 on 127.0.0.1:6310
cd plexus && PLEXUS_TEST_DB_PORT=6310 uv run pytest -q        # throwaway graphs, deleted in teardown
bash ../scripts/agent_db.sh rm 10
```

</details>

## Docs

- `docs/graph-model.md`: graph data model (diagram, labels, edges, indexes)
- `docs/queries.md`: index of every Cypher query
- `docs/TESTING.md`: Definition of Ready for Testing with evidence, and the owner's manual test checklist
- `docs/demo.md`, `docs/mcp.md`: the demo scenario, the ablation demo, the MCP server
- `docs/AI_USAGE.md`: AI disclosure
