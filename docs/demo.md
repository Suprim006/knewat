# Demo: "Acme Notes API" (scenario, scripted agents, real Claude agents, recordings)

A fictional team (planner, researcher, builder) specifies and builds the "Acme Notes API". Everything in the scenario is
synthetic. The same scenario can be played three ways, and all of them write to the same Knewat graph through the same
MCP tools (every call leaves a `ToolCall` and a Lineage `Step`):

| Mode | Command | Who plays the agents | Costs |
|---|---|---|---|
| Scripted | `knewat demo live --scripted` | deterministic Python, in-memory MCP client | nothing; 8 s at full speed |
| Real | `knewat demo live --claude` | three unmodified `claude -p` agents over stdio MCP | the owner's Claude subscription (about $0.70 notional for a Sonnet run) |
| Replay | `knewat demo replay <run>` | nobody: restores a recorded graph | nothing |

The public demo uses scripted runs and replays of the recorded real run; real LLM runs only appear in the video
(`CLAUDE.md` §5).

Code: `knewat/src/knewat/demo/` (`scenario`, `engine`, `scripted`, `orchestrator`, `recorder`, `replay`, `inventory`) and
`knewat/src/knewat/cli.py`. Data: `knewat/demo_data/acme/` (sources, `tasks.json`, `roles/*.md`) and
`knewat/demo_data/recordings/<run>/`.

## Run it

```bash
cd knewat && uv sync                         # once; adds the `knewat` command
export FALKORDB_HOST=127.0.0.1 FALKORDB_PORT=6379   # whichever FalkorDB you started (see docs/mcp.md)

uv run knewat demo seed --tenant demo                        # schema + the 5 starting documents as Source nodes
uv run knewat demo live --scripted --tenant demo --reset     # play the whole scenario (--speed 0 = no pauses)
uv run knewat demo inventory --tenant demo                   # node / edge counts per label / type
uv run knewat demo list                                      # the recordings
uv run knewat demo replay acme-claude-sonnet --tenant demo --reset   # restore a recording and verify its counts
uv run knewat demo live --claude --model sonnet --tenant demo_claude --reset --run-name my-run   # spends subscription
uv run knewat demo ablation --tenant demo                    # cut the edges in a copy and show what breaks (below)
uv run knewat mcp-config --tenant demo                       # an MCP config for Claude Code for this checkout (docs/mcp.md)
```

`--tenant` is the graph `knewat_t_<tenant>` (`^[a-z0-9_]{1,48}$`). `live` refuses a tenant that already has data unless
you pass `--reset`. With the View API on the same database (`uv run knewat-api`, then `knewat-view`) pick the tenant in the
UI and watch the run land; `--speed 1` (default) pauses 0.5 s per tool call, `--speed 4` pauses 0.125 s, `--speed 0` none.

Other `live` flags: `--kill-at N`, `--v2-at N` (when the faults fire, default 15 and 20), `--no-faults`, `--lease-ms`
(builder lease: 3000 ms scripted, 45000 ms claude), `--poison-at N` (stretch fault, below), `--embedder hash|fastembed`,
`--record RUN` (record the run when it ends; the real mode always records), and for `--claude`: `--max-turns`
(default 25 per agent turn), `--stop-after-turns N` (a cheap pilot), `--run-name`, `--mcp-command`.

## The scenario

**Sources** (`demo_data/acme/sources/`, each becomes a `Source` node when an agent registers it with `add_source`):

| File | Says | Read by |
|---|---|---|
| `01_product_brief.md` | what the service is, rate limit, owner | researcher, t01 |
| `02_api_style_guide_v1.md` | **API version v1**, cursor pagination | researcher, t01 |
| `03_infra_note.md` | PostgreSQL 16, Kubernetes, port 8080 | researcher, t04 |
| `04_security_note.md` | **auth: JWT bearer (RS256)** | researcher, t04 |
| `05_customer_request.md` | Globex wants **API-key auth** | planner, t05 |
| `06_api_style_guide_v2.md` | **API version v2** (supersedes v1), released mid-run | researcher, after the v2 fault |
| `07_forum_post_unverified.md` | anonymous claim "MongoDB 4, no auth" (trust 0.2) | only in the poison variant |

**Task DAG** (`tasks.json`; the planner creates the first 11 in one `create_tasks`, the 12th appears mid-run):

| Task | Role | Prio | Depends on |
|---|---|---|---|
| t01-gather-requirements | researcher | 50 | |
| t02-choose-api-version | planner | 45 | t01 |
| t03-design-endpoints | builder | 40 | t02 |
| t04-survey-infra-security | researcher | 35 | t01 |
| t05-choose-auth | planner | 30 | t04 |
| t06-write-db-schema | builder | 25 | t02, t04 |
| t07-implement-crud-spec | builder | 20 | t03, t05, t06 |
| t08-write-test-plan | researcher | 15 | t03 |
| t09-review-spec | planner | 12 | t07, t08 |
| t10-write-docs | researcher | 10 | t09 |
| t11-package-release | builder | 5 | t10 |
| t12-update-endpoints-for-v2 (added by the planner after v2) | builder | 60 | t03 |

**Scheduler** (`engine.py`, shared by scripted and real runs): one agent turn at a time. It reads the ready tasks, takes the
top one (the same order `claim_next_task` uses, so the agent's claim gets exactly that task), and gives the turn to the agent
of that task's role. A turn is one task: start a session if needed, claim, recall, assert facts with sources, record
decisions with `based_on`, complete, hand off. The harness only peeks at task state; agents act only through MCP tools.
Every Knewat tool call increments one **global step counter**, and each call passes it as `step`, so "step N" means the same
moment for every agent (scripted: by code; real: each prompt says which `step` number to start at, and the recorded run
followed it on 83 of 83 calls).

**Fault script** (`FaultScript`, keyed by global step):

1. **Builder killed at step 15.** From step 15 on, the first time the builder holds a claimed task and has worked on it, it
   dies before its next call (scripted: the call is not made; real: the `claude` process is killed). Its lease
   (`builder_lease_ms`) is left to expire; the scheduler waits for it, then the **researcher reclaims** the task:
   `(Agent researcher)-[:CLAIMED {reclaimed_from:'builder'}]->(Task)`. The builder is later restarted (a new `Session`).
2. **Style guide v2 published at step 20.** At the first turn boundary at or after step 20 the researcher registers the v2
   document and asserts `api_version = v2` (its own earlier v1 fact is superseded: `SUPERSEDES`, validity windows closed), then
   the planner records a decision to adopt v2 and creates task t12.
3. **Conflicting auth assertion** (part of t05, not timed): the researcher asserted JWT from the security note; the planner now
   asserts API key from the customer request. Different agents, different values, so Engram writes a `CONTRADICTS` edge and
   keeps both facts active; the planner's decision resolves it and is `BASED_ON` both.
4. **(stretch) Poisoned source**, `--poison-at N`: an unverified forum post claims `database = MongoDB 4`; the planner asserts it
   (contradicting the researcher's PostgreSQL fact) and records a decision on it; the researcher then `quarantine_source`s the
   post. The blast radius lists the fact, the readers and the decision; recall and `as_of` stop returning the poisoned fact.

## What happens, step by step (scripted run, 67 tool calls, 12 tasks)

| Steps | Who | What |
|---|---|---|
| 1-2 | planner | `start_session`, `create_tasks` (11 tasks) |
| 3-9 | researcher | t01: `add_source` brief + style guide v1; facts `purpose`, `api_version = v1`; complete |
| 10-12 | planner | t02: claim, `record_decision` "build against v1" `BASED_ON` the v1 fact, complete |
| 13-15 | builder | session, claims t03, recalls "API version" (reads **v1**) |
| 15 | fault | builder killed; lease expires |
| 16-20 | researcher | reclaims t03 (`reclaimed_from=builder`), writes an episode, completes, hands off to the builder |
| 20 | fault | style guide v2 published |
| 21-23 | researcher | `add_source` v2, `assert_fact api_version = v2` (**v1 superseded**), episode |
| 24-26 | planner | recall, decision "adopt v2" `BASED_ON` the v2 fact, `create_tasks` t12 |
| 27-32 | builder | restarted: new session, t12 (recall reads **v2**), complete, hand off |
| 33-38 | researcher | t04: infra + security sources; facts `database`, `auth_method = JWT` |
| 39-44 | planner | t05: customer request; `auth_method = API key` (**CONTRADICTS** JWT); decision based on both |
| 45-53 | builder | t06 schema, t07 CRUD spec (reads v2 + auth), hand off |
| 54-67 | researcher, planner, builder | t08 test plan, t09 review (`verify_artifact`, decision), t10 docs, t11 release |

The real run (`acme-claude-sonnet`) has the same shape with different step numbers, because LLM turns make a few more calls:
builder killed at step 17 (claim at 16, recall at 17), v2 published at 24, 83 calls. It was recorded with
`claude-sonnet`, 16 `claude -p` processes, 95 model turns, 0 permission denials, 0 errors.

## Aha queries

Replace `<t>` by the tenant. Use the Explorer in `knewat-view`, FalkorDB Browser, or the MCP tools (`why`, `knew_at`, `who_knew`).

**Why did the team move to v2?** `why(decision_id)` follows the decision's `BASED_ON` to the v2 fact, who asserted it, its source
document, the step that wrote it, and the v1 fact it superseded:

```cypher
MATCH (d:Decision) WHERE d.text STARTS WITH 'Adopt'
MATCH (d)-[:BASED_ON]->(f:Fact)-[:DERIVED_FROM]->(s:Source)
MATCH (f)-[:ASSERTED_BY]->(a:Agent)
OPTIONAL MATCH (f)-[:SUPERSEDES]->(old:Fact)
RETURN d.text, f.value, a.id, s.uri, old.value
// -> "Adopt style guide v2 ...", v2, researcher, acme-docs/06_api_style_guide_v2.md, v1
```

**Which decisions rest on a fact that is no longer true?** (the v1 decision)

```cypher
MATCH (d:Decision)-[:BASED_ON]->(f:Fact) WHERE f.status <> 'active' RETURN d.text, f.value, f.status
```

**What did the builder know at step 15, and at step 29?** (`knew_at` = the facts the agent had read that were still valid at that step.)
Scripted run: step 15 -> `api_version v1`; step 29 -> `api_version v2` (the v1 it read earlier is no longer valid). Real run: step 17 -> v1, step 38 -> v2.
`knew_at(agent_id=<any>, subject_agent="builder", step_n=15)`, or in Python `Lineage(client, graph).knew_at("builder", 15)`.

**Who reclaimed what?**

```cypher
MATCH (a:Agent)-[c:CLAIMED]->(t:Task) WHERE c.reclaimed_from <> ''
RETURN a.id AS reclaimer, t.id AS task, c.reclaimed_from AS from_agent
// -> researcher, t03-design-endpoints, builder
```

**Where do the agents disagree?**

```cypher
MATCH (a:Fact)-[:CONTRADICTS]->(b:Fact), (a)-[:ASSERTED_BY]->(x:Agent), (b)-[:ASSERTED_BY]->(y:Agent)
RETURN a.value, x.id, b.value, y.id   // API key (planner) vs JWT (researcher)
```

**What was the exact order of work?** `GET /api/<t>/flow` (ToolCalls with step numbers), or
`MATCH (c:ToolCall) RETURN c.step, c.agent_id, c.tool ORDER BY c.at`.

**What would quarantine have cost?** run with `--poison-at 40`, then read the `quarantine` event printed by the CLI
(`blast_radius`: fact ids, readers, decision ids).

## Ablation demo (`knewat demo ablation`)

"Does the product still work if you take the graph's edges away?" Run it on a tenant that holds a finished run
(for example `uv run knewat demo replay acme-claude-sonnet --tenant demo` first):

```bash
uv run knewat demo ablation --tenant demo           # keeps the stripped copy as tenant 'demo_ablated'; add --drop to remove it, --json for machines
```

It `GRAPH.COPY`s `knewat_t_demo` to `knewat_t_demo_ablated`, deletes `DEPENDS_ON`, `BASED_ON`, `DERIVED_FROM` and `READ` there
(the bounded `crucible/strip_edges` query), and runs the same probes on both graphs. Read-only probes (`why`, `knew_at`,
`who_knew`) run on the two graphs directly. Probes that write (claims, `forget_source`) run on throw-away copies of both, with the
tasks put back to `open`, and those copies are dropped at the end. The original tenant is never written: node and edge counts are
compared before and after and the command exits 1 if they differ (it also exits 1 if a feature does not work on the intact graph,
if an edge-dependent feature does not break, or if a control breaks). Output on `acme-claude-sonnet`:

```text
Feature                     Needs         Intact (demo)                                                           Edges removed (demo_ablated)
why(decision)               BASED_ON      works: 3 supporting fact(s), 2 agent(s), 3 source(s)                    BROKEN: 0 supporting fact(s), 1 agent(s), 0 source(s)
knew_at(agent, step)        READ          works: 5 fact(s) read by builder (step 83)                              BROKEN: 0 fact(s) read by builder (step 83)
who_knew(fact)              READ          works: 3 agent(s) read it                                               BROKEN: 0 agent(s) read it
dependency-aware claim      DEPENDS_ON    works: 1 task(s) claimable on a fresh board, 0 with unmet dependencies  BROKEN: 12 task(s) claimable on a fresh board, 11 with unmet dependencies
blocked_by_failure(task)    DEPENDS_ON    works: 11 task(s) blocked behind t01-gather-requirements                BROKEN: 0 task(s) blocked behind t01-gather-requirements
forget by source (cascade)  DERIVED_FROM  works: forgot 1 fact(s), flagged 2 decision(s)                          BROKEN: forgot 0 fact(s), flagged 0 decision(s)
exclusive claims            (control)     works: 1 claim(s), 0 claimed twice                                      works: 12 claim(s), 0 claimed twice
supersession history        (control)     works: 1 SUPERSEDES edges                                               works: 1 SUPERSEDES edges
6 of 6 edge-dependent features break; 2 of 2 controls are unaffected
```

Open tenant `demo_ablated` in the View next to `demo` to see the same graph without the four edge types. This is the live
counterpart of the Crucible ablation numbers (`docs/BASELINE.md`, `layers.ablation` in the Results page). Code:
`knewat/src/knewat/demo/ablation.py`, queries `knewat/queries/demo/`, test `knewat/tests/demo/test_ablation.py`.

## Recordings

`knewat demo live ... --record RUN` and every `--claude` run write `demo_data/recordings/<RUN>/`:

| File | Content |
|---|---|
| `graph.dump` | Redis `DUMP` of the tenant graph, taken from a `GRAPH.COPY` named `rec_<run>` (dropped afterwards). Includes nodes, edges, properties, vectors and indexes |
| `meta.json` | run, mode, FalkorDB version (`60002` = 6.0.2), inventory (counts per label / edge type), steps, faults, events, tool-call counts, turn list; for real runs also model, token usage, notional cost, permission denials, per-turn results and `step_numbering` |
| `calls.json` | every counted tool call `{step, agent, tool}` |
| `transcripts/NN-<agent>-<turn>.jsonl` | the raw `stream-json` of each `claude -p` process (init event reduced to useful keys, local paths removed) |

`knewat demo replay <run> --tenant T` `RESTORE`s the dump into `knewat_t_T` (`--reset` to overwrite) and checks that the node and
edge counts per label / type equal `meta.json` (exit code 1 if not). `DUMP`/`RESTORE` round-trips on FalkorDB 6.0.2 (tested for
every committed recording, with a working query, vector and index check), but a dump only restores on the version that wrote it.

| Run | Mode | Nodes | Edges | Notes |
|---|---|---|---|---|
| `acme-scripted` | scripted, fastembed | 199 | 581 | 67 steps; kill at 15, v2 at 20 |
| `acme-claude-sonnet` | 16 `claude -p` (sonnet) | 247 | 708 | 83 steps; kill at 17, v2 at 24; $0.698 notional, 0 denials |
| `pilot-haiku` | 4 `claude -p` (haiku), `--stop-after-turns 4` | 62 | 146 | the pilot: init, t01, t02, then the builder killed mid-t03 |

## Real-agent safety rules (what `orchestrator.py` enforces)

Each turn is `claude -p <assignment> --model M --max-turns 25 --mcp-config <run>/mcp.json --strict-mcp-config --allowedTools "mcp__knewat__*"
--tools "" --output-format stream-json --verbose --no-session-persistence --append-system-prompt <role prompt>` with
`ANTHROPIC_API_KEY` removed from the environment (so usage goes to the signed-in subscription; no `--bare`). `--tools ""` removes
every built-in tool, so the only things an agent can do are Knewat calls. The generated `mcp.json` starts the venv's `knewat-mcp`
(no `uv run`, which delays start-up) with `--tenant <run tenant>`. The orchestrator checks every `result` for `is_error`,
`subtype != success` and non-empty `permission_denials` (a blocked tool still exits 0) and aborts the run on the first failure;
a turn that ends without completing its task is tolerated once (the lease expires, the reclaimer takes over) and aborts the run
the second time. Knewat contains no LLM code and no credentials.

## Tests (no real Claude, no subscription)

`KNEWAT_TEST_DB_PORT=<port> uv run pytest tests/demo -q`:

- `test_scripted.py`: the run on a throwaway tenant: 12 tasks done, a `ToolCall` and `Step` for every call, v1 superseded by v2, one
  `CONTRADICTS` between two agents, `reclaimed_from='builder'`, 4 decisions with `BASED_ON`, `knew_at` v1 then v2, two runs give the same
  graph, poison variant quarantines the forum post.
- `test_faults.py`: faults fire at the configured steps and not when disabled.
- `test_recorder.py`: record -> replay round trip equals the original counts and keeps the facts, vectors and indexes; every committed
  recording replays to its `meta.json`.
- `test_orchestrator.py`: command line, environment, mcp config, prompts, transcript sanitising, and a full orchestrated run with a
  stand-in `claude` (`tests/demo/fake_claude.py`) including the kill, lease expiry, reclaim, v2 publication and a permission denial.
- `test_cli.py`: `seed`, `live --scripted --record`, `inventory`, `replay`, `list`.
