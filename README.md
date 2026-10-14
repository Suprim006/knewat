# Plexus

One shared graph brain for AI agent teams, the memory and coordination layer that Claude Code, Hermes and other
harnesses lack. Agents connect over MCP. Every memory, task, handoff and decision is a node in FalkorDB, so the
team remembers across sessions, works without stepping on each other, and can always answer *"why?"* and *"what
did we know then?"*

Built for Graph Hacks (WeMakeDevs × FalkorDB), **Track 02: Agent Memory and Coordination**.

## Setup

TBD.

Quick dev loop for contributors (see `docs/PLAN.md` and `CLAUDE.md`):

```bash
bash scripts/agent_db.sh 10                                   # FalkorDB 6.0.2 on 127.0.0.1:6310
cd plexus && PLEXUS_TEST_DB_PORT=6310 uv run pytest -q        # throwaway graphs, deleted in teardown
bash ../scripts/agent_db.sh rm 10
```

## Docs

- `docs/graph-model.md`: graph data model (diagram, labels, edges, indexes)
- `docs/queries.md`: index of every Cypher query
- `docs/AI_USAGE.md`: AI disclosure

## Live demo

One container (FalkorDB + API + MCP over HTTP + the View) on Render Free: **URL: TBD after the owner deploys it**
(`docs/deploy.md` has the click-by-click steps and the uptime pinger). The `demo` and `demo_scripted` tenants are
restored from the recordings on every boot and are read-only; point your own agent at `https://<host>/mcp/t/team_<name>`
(`claude mcp add --transport http plexus https://<host>/mcp/t/team_alice01`) to write. Everything in a `team_*` tenant is
public and deleted after 24 h idle, so store nothing private. Verified locally under `-m 512m --cpus 0.5`: boot in
5 to 14 s, peak 322 MiB (`docker stats`), 40/40 checks (`deploy/verify.py`).
