# Track 02 project ideas (Graph Hacks: Agent Memory and Coordination)

Based on: [landscape/1-agent-products.md](landscape/1-agent-products.md), [landscape/2-memory-layers.md](landscape/2-memory-layers.md), [landscape/3-coordination.md](landscape/3-coordination.md), [use-cases.md](use-cases.md), [../reference/FALKORDB_REFERENCE.md](../reference/FALKORDB_REFERENCE.md).
Everything below is design inference. The gaps it relies on are cited in the landscape files.

## The gaps worth attacking (consolidated)

| # | Gap | Who has it | Where it's documented |
|---|---|---|---|
| G1 | **Handoffs, claims and decisions are not first-class, queryable objects.** Subagents return self-reported summaries; no system or benchmark models Task, Handoff or Decision | Hermes, Claude Code agent teams, LangGraph, CrewAI, Letta | L1 §3.10, L2 §4.4, L3 §4.1–2 |
| G2 | **No consistency story for concurrent writers:** dedup races, last-writer-wins blocks, "designate one owner" | Mem0 #6515, Letta shared blocks, Hermes profiles | L2 §4.1, L1 §3.12 |
| G3 | **No temporal validity:** stale facts stay "current", and invalidation is judged by an LLM and inconsistent | Hermes (first-hand: the Docker fact), ChatGPT, Claude Code, Graphiti #1841 | L1 §3.1, L2 §4.2 |
| G4 | **Memory isn't scoped:** global or per-repo, with no tenant, project or agent boundary | Hermes (first-hand: FlyerHR notes injected here), Claude, Windsurf | L1 §3.3 |
| G5 | **No conflict detection between agents' facts.** A 2026 position paper says no detector exists | CrewAI (leaves it to an LLM), everyone else | L3 §3, §4.3 |
| G6 | **Provenance and "why recalled" are partial or missing**, so precise forgetting and poisoning containment are impossible | ChatGPT, Gemini, OpenClaw, Mem0; the MAPLE-Guard and Misattribution papers | L1 §3.5–6, L3 §3 |
| G7 | **Procedural memory doesn't learn from outcomes** (it counts usage, not success) | Hermes curator, Claude skills | L1 §3.9, L2 §4.5 |
| G8 | **No benchmark covers concurrency, handoffs, tenant leaks or invalidation** | LoCoMo, LongMemEval, MemoryAgentBench | L2 §3 |

Competitors already seen in Graph Hacks 2026 ([use-cases.md](use-cases.md)):
- **MERIDIAN:** 4 agents, a graph per tenant, an ablation demo.
- **GraphMem:** planner and coder coordinating through the graph, but no code yet.
- **ZeroCapital:** the three memory types plus a trace.

Per-tenant graphs and basic supersession are **table stakes**. G1, G2, G5, G6 and G8 are the least covered.

---

## Idea 1 — **Relay**: a graph-native coordination layer for agent teams (MCP-first)

**Pitch:** "Git for multi-agent work state." Any agent harness (Hermes, Claude Code, a LangGraph app) connects over MCP and gets atomic task claims with leases, verifiable handoffs, a decision log, and contradiction alerts. All of it lives in FalkorDB and can be queried across sessions.

**Fills:** G1, G2, G4, G5, plus part of G3 and G6.

**Why FalkorDB is essential (rule R2):**
- Each claim or lease is one atomic compare-and-set Cypher write. Writes to a graph run one at a time, so there are no double claims.
- "Who decided X, based on which facts, handed to whom" is a multi-hop path.
- Each workspace or tenant gets its own graph with ACL.
- Readers get parallel snapshot reads while agents write.
- Without the graph there is no coordination state at all.

**Graph model (sketch):**
```
(:Agent {id, role, harness})  (:Task {id, title, status, lease_until, version})
(:Agent)-[:CLAIMED {at, lease_until}]->(:Task)       (:Task)-[:DEPENDS_ON]->(:Task)
(:Handoff {id, at, note})-[:FROM]->(:Agent), -[:TO]->(:Agent), -[:FOR]->(:Task), -[:CARRIES]->(:Artifact)
(:Decision {id, text, at})<-[:DECIDED]-(:Agent); (:Decision)-[:BASED_ON]->(:Fact); (:Decision)-[:FOR]->(:Task)
(:Fact {id, subject, predicate, value, valid_from, valid_to})-[:ASSERTED_BY]->(:Agent)
(:Fact)-[:SUPERSEDES]->(:Fact)   (:Fact)-[:CONTRADICTS]->(:Fact)   (:Artifact)-[:VERIFIED_BY]->(:Agent)
(:Step {n, at})-[:BY]->(:Agent); (:Step)-[:READ]->(:Fact)          // enables "what did X know at step N"
```

**MCP tools:**
- `claim_next_task`
- `heartbeat`
- `handoff`
- `record_decision`
- `assert_fact` (returns any contradictions)
- `recall(as_of)`
- `why(decision)`
- `who_knew(fact, at)`

**3-minute demo:**
1. Three agents work on a small synthetic project: a planner, a researcher and a builder. The planner is Hermes over MCP. The live graph is visible in Browser or our UI.
2. We kill the builder mid-task. Its lease expires and the researcher reclaims the task. The graph shows the reclaim chain.
3. Two agents assert conflicting facts. A `CONTRADICTS` edge appears and the planner resolves it with a decision that records what it was based on.
4. "Why did the build use API v2?" returns one Cypher path: decision ← facts ← agents ← steps.
5. Load test: 100 simulated agents race for 500 tasks. FalkorDB gives 0 double claims; a naive JSON/file blackboard run shows real duplicates. We report p50/p99 latency and throughput.
6. Ablation: cut the edges and every capability fails.

**4-day scope (solo plus subagents):**
- **Day 1:** graph model, 10–12 core queries, Python service, MCP server.
- **Day 2:** the agents, leases, reclaim and contradictions.
- **Day 3:** time travel (step N), UI, load test, ablation.
- **Day 4:** deploy, README, video.

**Risks:**
- The demo needs real agents running.
- Coordination is less visual than memory, so the UI matters.

---

## Idea 2 — **Engram**: temporal, scoped, outcome-aware memory for agents ("the memory Hermes wishes it had")

**Pitch:** a memory service that holds episodic, semantic and procedural memory in one linked graph.
- **Episodes:** turns chained in sessions.
- **Facts:** valid over a time window, superseded rather than overwritten.
- **Procedures:** skills with outcome edges, so the agent learns which playbook actually works.

Memory is scoped (user, project, global) with controlled inheritance. Retrieval is a top-k query within a budget, so the store never hits a cap. Every recalled item comes with its "why" path.

**Fills:** G3, G4, G6, G7, plus all three memory types and persistent history.

**Why FalkorDB is essential:**
- Hybrid recall in one query: vector seed → graph expansion → validity filter.
- One graph per user or tenant.
- Supersession and provenance are edges.
- Precise forgetting is a `DERIVED_FROM` cascade.
- Consolidation uses PageRank (salience) and label propagation (clusters) without LLM calls.

**Graph model (sketch):**
```
(:Session)-[:HAS_TURN]->(:Episode {role, text, at, embedding})-[:NEXT]->(:Episode)
(:Fact {subject, predicate, value, valid_from, valid_to, recorded_at, embedding})-[:DERIVED_FROM]->(:Episode)
(:Fact)-[:SUPERSEDES]->(:Fact); (:Fact)-[:DUPLICATES|CONTRADICTS]->(:Fact); (:Fact)-[:ABOUT]->(:Entity)
(:Fact)-[:IN_SCOPE]->(:Scope {kind: user|project|global}); (:Scope)-[:INHERITS]->(:Scope)
(:Procedure {name, steps})-[:USED_IN]->(:Run)-[:RESULTED_IN]->(:Outcome {success})
(:Recall {at, query})-[:RETURNED {rank, path}]->(:Fact)        // the "why recalled" audit
```

**3-minute demo:** replay three *real* Hermes memory failures from this project, first as they happened and then with Engram:
1. **Stale fact.** "Docker won't start" becomes "Docker works", and the old fact is superseded with validity dates.
2. **Project leak.** FlyerHR notes no longer appear in the FalkorDB project, because scopes keep them apart.
3. **Duplicates.** Three near-duplicate user entries are caught at write time and merged.

Then:
- Two users stay fully isolated, each in their own graph.
- A procedure's success rate changes the agent's choice.
- "Forget everything from session X" removes the derived facts precisely.

**Risks:**
- This is the most crowded idea space (Graphiti, Mem0 and Cognee already run on FalkorDB).
- It must look clearly better than Graphiti. The edge is scopes, outcomes and LLM-free consolidation and writes.

---

## Idea 3 — **Quarantine**: provenance-tracked shared memory that contains poisoning

**Pitch:** agents promote private memories into shared memory only through a trust gate. Every memory keeps its `DERIVED_FROM` lineage back to its source. When one source turns out to be poisoned (for example a prompt-injected web page), a single traversal:
- finds every fact derived from it, any number of hops away;
- finds every agent that read those facts;
- finds every decision based on them.

It then quarantines them and replays the affected decisions.

**Fills:** G6 and G5, plus shared state. It's a security angle: OWASP ASI06, and MAPLE-Guard reports attacks spreading to 60–80% of agents over 8 hops.

**Why FalkorDB is essential:** finding the blast radius is a variable-length traversal over lineage, and quarantine is a single atomic write. The whole idea is a graph problem.

**Graph model:**
```
(:Source {uri, trust})<-[:DERIVED_FROM]-(:Fact)<-[:DERIVED_FROM*]-(:Fact)
(:Agent)-[:READ {at}]->(:Fact); (:Decision)-[:BASED_ON]->(:Fact); (:Fact)-[:PROMOTED_BY]->(:Agent)
(:Fact {scope: private|shared, status: active|quarantined, trust})
```

**Demo:**
1. A research agent ingests 5 synthetic sources, one of them poisoned.
2. Its facts spread through 3 agents and 2 decisions.
3. We flag the source, and one query lights up the blast-radius subgraph.
4. Quarantine runs, the affected decisions re-run, and the result is correct.
5. Metrics: the share of poisoned facts contained, compared with a flat vector store where lineage is lost.

**Risks:**
- Narrower against the track wording. It covers shared state and memory updates, but procedural memory and concurrency are weaker.
- Best used as **a feature inside Idea 1 or 2**, or as a bold standalone entry.

---

## Idea 4 — **Crucible**: an open multi-agent memory benchmark plus a FalkorDB reference implementation

**Pitch:** the first benchmark for what LoCoMo and LongMemEval ignore:
- concurrent writers (duplicates and lost updates);
- conflicting facts (detection and resolution);
- tenant-leak probes;
- handoff accuracy;
- invalidation correctness;
- "what did X know at T".

It ships with a FalkorDB reference memory layer and baseline adapters (JSON file, SQLite, a vector store, and optionally Mem0 or Graphiti).

**Fills:** G8, and proves G2, G3 and G5 with numbers.

**Rule risk (R2/R3):** a benchmark harness still works without FalkorDB. **Don't enter this alone.** Ship it as the evaluation suite of Idea 1 or 2, where it's a strong differentiator and gives a "results" slide.

---

## Applied variant (optional skin for Idea 1 or 2) — **HR Ops crew for multi-tenant companies**

Leave, payroll and policy agents for several synthetic companies, one graph per company. They share employee context through handoffs, keep the history of each employee conversation, and use playbooks ("approve leave", "payroll correction") whose success rates update.

This uses your FlyerHR domain knowledge and gives judges a concrete business story. It is less novel technically, so use it only as the demo's scenario, not the pitch.

---

## Scoring (1–5, my judgement)

| | Memory types | History | Shared state / handoffs | Concurrency | Per-tenant | Novelty | Demo clarity | Fits 4 days | Graph is essential |
|---|---|---|---|---|---|---|---|---|---|
| **1 Relay** | 3 | 3 | **5** | **5** | 4 | **5** | 4 | 4 | **5** |
| **2 Engram** | **5** | **5** | 3 | 3 | **5** | 3 | **5** | 4 | 4 |
| **3 Quarantine** | 3 | 3 | 4 | 3 | 3 | **5** | 4 | 4 | **5** |
| **4 Crucible** | 3 | 2 | 3 | **5** | 4 | 4 | 3 | 3 | 2 (alone) |

## Recommendation

**Build Relay (Idea 1) as the core, with an "Engram-lite" memory module, and use Crucible's tests as the proof.**
- **Engram-lite:** facts with validity windows and supersession, episodes and sessions, scopes, and procedures with outcome counts.
- **Crucible's tests:** concurrency, contradictions and tenant leaks, with numbers.
- **Stretch:** if Day 3 goes well, add Quarantine's blast-radius query as a final demo moment.

That covers all five Track 02 focus areas. It leads with the least-contested gaps (handoffs, concurrency, decision provenance), which differentiates it from MERIDIAN, GraphMem and ZeroCapital. Hermes and Claude Code can be its real MCP clients, which makes a strong story: "we fixed the coordination problems we hit while building this."

**Decision needed before 00:16 NPT:** pick an idea (or this combination), and optionally a demo scenario (a generic software team or the HR Ops skin).

---

## Owner decision (2026-10-14): combined project, working name **Plexus**

The owner chose the combined scope instead of Relay alone. **Plexus** is one graph and one MCP server with the following modules:

| Module | From idea |
|---|---|
| **Engram** (memory) | 2 |
| **Relay** (coordination) | 1 |
| **Lineage** (provenance, "why", time travel, forget/quarantine) | 3 |
| **Crucible** (benchmark proof) | 4 |
| **Time Machine UI** | (new) |

Authoritative scope, MVP and stretch cut lines: `CLAUDE.md` §4 and `docs/DECISIONS.md` D-001. Evaluation plan: `docs/BASELINE.md`.
