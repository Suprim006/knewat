# What a graph database is actually good for in an agent team (and what it isn't)

*Draft for the Graph Hacks best-blog side prize. Project: Plexus, Track 02 (Agent Memory and Coordination). Replace `<REPO_URL>` and `<RENDER_URL>` before posting.*

Run three Claude Code agents on one project and the same problems appear fast. The researcher writes a note the builder never
reads. The builder dies halfway through a task and nobody notices. A style guide changes mid-run and one agent keeps working
from the old one. And when you ask "why did we pick v2?", the answer is whatever the transcripts happen to say.

Today's tools mostly solve memory with text files and coordination with a shared task list. Both are readable and need no
infrastructure, and both are hard to query. I wanted to know whether putting all of it in one graph, and nothing else, would
change what an agent team can answer about itself, and where it would not help.

## The design

Plexus is an MCP server over FalkorDB 6.0.2. There is no LLM inside it: the agents are unmodified Claude Code processes, and
each of the 29 tools runs a fixed, parameterised Cypher statement. Three decisions carry most of the weight.

**One graph per tenant.** Each team gets its own graph, `plexus_t_<name>`, and the tenant is bound to the MCP connection, never
passed as a tool argument. Isolation is physical rather than a `WHERE tenant = ...` filter, and it fits FalkorDB: reads run in
parallel but writes to one graph are serialised, so spreading teams over graphs is both the isolation story and the scaling story.

**Facts have validity windows and are never overwritten.** A fact has `valid_from` and `valid_to` in epoch milliseconds (open-ended
is a sentinel, because FalkorDB stores no nulls). A new value closes the old fact and writes a `SUPERSEDES` edge. If two agents
assert different values for the same thing, a `CONTRADICTS` edge is written in the same statement and both stay active until
someone decides. "True now" and "true at T" are the same query with a different filter.

**Provenance is edges, written as work happens.** Every tool call creates a `Step` in the agent's chain and a `ToolCall` node
linked to what it created. Reads add `READ` edges to the facts returned; decisions are `BASED_ON` the exact facts the agent cites;
facts are `DERIVED_FROM` a `Source` document. That makes questions answerable:

```cypher
MATCH (d:Decision)-[:BASED_ON]->(f:Fact)-[:DERIVED_FROM]->(s:Source)
MATCH (f)-[:ASSERTED_BY]->(a:Agent)
OPTIONAL MATCH (f)-[:SUPERSEDES]->(old:Fact)
RETURN d.text, f.value, a.id, s.uri, old.value
```

On the recorded run (three real Claude Sonnet agents building a fictional "Acme Notes API": 83 tool calls, 247 nodes, 708 edges)
this returns the adopt-v2 decision, the v2 fact, the researcher, the style-guide file and the v1 fact it replaced. "What did
the builder know at step 17?" walks the builder's steps, their `READ` edges and the validity windows: v1 at step 17, v2 at step 38.
Coordination uses the same machinery. A claim is a single statement that finds a task whose `DEPENDS_ON` targets are all done
and whose lease is free or expired, so a dead agent's task is reclaimed and the `CLAIMED` edge records who lost it.

## Does the graph do real work?

I tested it by cutting edges. Delete `DEPENDS_ON`, `BASED_ON`, `DERIVED_FROM` and `READ` from a copy of the graph and rerun the
features: 7 of 7 capabilities that use those edges break (dependency-aware claims, `why`, `knew_at`, forget-by-source, and so
on), and 5 of 5 controls that do not use them are unaffected. With the edges gone, 181 tasks started before their dependencies
finished. The test is in the repo, and so is a command that shows it on any tenant.

## What the benchmark honestly showed

Crucible changes only the backend behind an identical tool API: locked flat files, SQLite, a vector store, and Plexus. I built
the baselines to be competent, and the results were less flattering than the pitch.

- **Correctness under concurrency: a four-way tie.** Zero double claims, lost updates or tenant leaks in every backend. A file lock
  or a SQLite transaction is enough for exclusive claims.
- **Speed: SQLite wins the median claim** at every worker count (0.82 ms against 571 ms at 200 workers), though its tail is worse.
  Plexus's server time stays at 1-4 ms; the rest is FalkorDB's per-graph write queue. Spreading 50 workers over 1, 4 and 16 tenant
  graphs took Plexus from 678 to 1,174 ops/s (+73%); SQLite went 1,103 → 1,480 → 500.
- **Provenance questions: a tie, then a modest gap.** On 43 questions about one project, Plexus and two LLM-over-files baselines all
  scored 43 of 43, because the history fits in the context; the difference was cost (13-16k tokens and about five seconds per
  question, against milliseconds and no tokens). On a pre-registered test with 20 sprints of history, 10-17 times the context
  budget, Plexus scored 36 of 36, SQLite 32, files 30 and the vector store 23. A paired sign test gives p = 0.031 against files and
  p = 0.125 against SQLite, which I cannot tell from noise at 36 questions and one run each.

The caveats matter as much as the numbers: synthetic data, one model, a single-node database. Plexus answers with hand-written
Cypher per question family, which flatters it; every question names its sprint, which flatters retrieval; and I did not ask
questions that aggregate across sprints, where I expect a graph to help most. The fair summary is that the graph is competitive and
cheaper for provenance questions, with an accuracy edge that needs a bigger test.

## FalkorDB 6.0.2 lessons

- **Vector `score` is a distance.** Nearest-first is `ORDER BY score ASC`; the docs show DESC. There is no pre-filter, so scope and
  validity filters run after top-k, and I over-fetch (k×4) and retry.
- **No `datetime()`, no nulls.** Use epoch milliseconds, a sentinel for open `valid_to`, and `toJSON()` strings for maps.
- **`RESULTSET_SIZE` silently truncates rows** in the default image; set the module args explicitly.
- **A runaway write ignored `TIMEOUT` and crashed the server.** Bound every write with `UNWIND` sizes; `LIMIT` does not stop eager writes.
- **Some Cypher misbehaves quietly:** a list mixing a grouping key with `collect()` in one `WITH` returned `null`, and a node created
  earlier in the same statement cannot be matched later.
- **Plan shape matters.** A `*1..5` pattern anchored on the fact side scanned every fact; expanding level by level from the source
  fixed it, and tests now assert plan shape for hot queries.
- **Dumps are version-bound.** `DUMP`/`RESTORE` round-trips my recordings, but only on the version that wrote them.

## Try it

`docker compose up -d --wait`, replay the recording, open the View. Source: `<REPO_URL>`; live demo: `<RENDER_URL>`, where anyone can
point their own Claude Code at a `team_` tenant (public, wiped after a day idle). I built it with AI assistants and say so in
`docs/AI_USAGE.md`.
