# Cypher review: `plexus/queries/view/` + `plexus/queries/activation/` (14 + 8 = 22 files, 551 lines)

> **STALE (2026-10-18):** the numbers in this document were measured on builds before the current main (7618d18) and are not valid for it until re-run. Build per number: [docs/NUMBERS_STATUS.md](../../NUMBERS_STATUS.md).

Read-only audit on `feature/neuro-memory-research` (HEAD e126875), done by the orchestrator (delegation cap = 2
subagents). Same method and live setup as `relay-staleness.md` (throw-away `audit_orch_*` graphs on plexus-db-13, all
deleted). This branch changed `activation/activation.cypher`, `activation/pin.cypher` and added `activation/entity_fan.cypher`.

## SUMMARY

| Severity | Count | Items |
|---|---|---|
| CONFIRMED BUG (semantic, live) | 1 | `activation/activation.cypher` L27 (this branch): `artifacts_ok` counts VERIFIED_BY **paths** over **every** FOR task of the decision, not "artifacts FOR the done tasks with an independent VERIFIED_BY" as the header (L4) and `docs/forgetting.md` say. Fixture: 1 artifact on the done task verified by 2 agents + 1 artifact on an open task → `artifacts_ok = 3`, header semantics give 1. It feeds salience at weight 1.0 each, so it can push a fact over `SALIENCE_PROTECT = 0.5` on its own. |
| SUSPECTED, NOT CONFIRMED | 0 | — |
| BOUNDEDNESS RISK | 2 (low) | `view/step_agents` reads every Step with `n <= $n` (header says "bounded by the number of agents" — only the output is); `view/scope_lookup` is a `Node By Label Scan` of all Scopes (live PROFILE) because of the `OR` |
| SIMPLIFICATION | 2 | `view/subgraph` (121), `view/inventory_edges` (75), `view/inventory_nodes` (41), `view/inventory_keys` (40) are per-label/per-type copies whose length is inherent to the plan shape; generate them from one label/type list (as `gen_impact_queries.py` does) rather than shorten by hand; `scope_lookup` split into two index-seek branches |
| CLARITY | 4 | `entity_fan` header omits "zero rows when the entity has no active fact" (caller maps it to 0, fine); `entity_fan` fan is global while recall's fan is per searched scopes; `maybe_duplicates` "at most 5 per fact" is a write-side invariant, not enforced here; `restore` taint check is `*1..5` while forget/quarantine cascades go to 12 |
| CLEAN (no correctness/boundedness finding) | 19 files | listed at the end |

Traps checked live and not reproduced: `activation.cypher` nested comprehensions `tasks_done` / `artifacts_ok` both over
`(d)-[:FOR]->(:Task)` (two comprehensions over the same pattern) returned non-empty values (`tasks_done = 1` correct; the
`artifacts_ok` problem is a definition issue, not the empty-list trap). `view/subgraph`'s `OPTIONAL MATCH … WHERE b IN ns`
after `collect` (big-write quirk 1) returned all edges (2,000/2,000 at 550 nodes). `subgraph` carries `ns` as a grouping
key (plan-shape 7b) but measured 90 ms server time at the API maximum (`GRAPH_LIMIT_MAX = 2000`, 2,001 nodes, 1,964 edges)
— not a problem at the cap.

---

## activation/

### activation.cypher (50 lines) — changed by this branch
- **CONFIRMED BUG (semantic), L27:** `artifacts_ok: size([(d)-[:FOR]->(:Task)<-[:FOR]-(:Artifact)-[:VERIFIED_BY
  {independent: true}]->(:Agent) | 1])` counts one per *path*: (i) the Task is not restricted to `status: 'done'`,
  (ii) an artifact verified independently by k agents counts k times. Live fixture (decision d1 FOR done t1 and open t2;
  artifact x1 FOR t1 verified by 2 agents; x2 FOR t2 verified by 1) → `artifacts_ok = 3`, `tasks_done = 1`. The header
  and `docs/forgetting.md` ("independently verified artifacts of the decisions' tasks") imply 1 (or 2 if "the decisions'
  tasks" means all tasks). In `service.salience_of` this is `SALIENCE_W["artifacts_ok"] = 1.0` per unit, so one
  artifact re-verified twice alone gives salience 1 − e^-2 = 0.86 ≥ 0.5 → swept-protection and, in the default `mult`
  mode, the `max(A, A0)` floor (see `BRANCH_REVIEW.md` finding 1). Proposed fix (one comprehension, distinct artifacts on
  done tasks):
  ```
  artifacts_ok: size([(d)-[:FOR]->(:Task {status: 'done'})<-[:FOR]-(x:Artifact)
                      WHERE (x)-[:VERIFIED_BY {independent: true}]->(:Agent) | x.id])
  ```
  Caveat: a `WHERE` inside a comprehension is on the trap list only when it mixes a property and a `$param`; this one
  is a pattern predicate, but it must be tested on the full fixture. An artifact FOR two done tasks of the same
  decision would still count twice; if that matters, return the ids and count distinct in Python. Also decide whether
  the restriction to done tasks is wanted (header) or not (code) — the SQL arm (`crucible/l5/sql_arm.py`) mirrors the
  code, so the §5.4 tie is unaffected either way.
- Otherwise CLEAN: the 8 comprehensions are each over a different relationship type, in one WITH before the READ
  aggregation, as the header documents. `sources` uses `DERIVED_FROM*1..3` in a comprehension (path enumeration; bounded
  by 3 hops and only used as "any high-trust", so duplicates are harmless).

### entity_fan.cypher (10 lines) — new
- CLEAN for correctness. Zero rows also when the entity exists but has **no active fact** (the grouping `count` with
  keys `e.id, e.name` and zero input rows returns zero rows). `ActivationService._fan` maps no row to 0, which is the
  right value, so this is CLARITY only: add it to the `returns:` line.
- CLARITY: the fan here counts active facts in **all** scopes; `engram/recall_entities` counts current facts in the
  **searched** scopes. `memory_strength.entity_lift` therefore can differ from the lift recall actually applied (also
  noted by the engram audit for `recall`'s `fan_e`). Say "global fan" in the header or pass a scope.

### novelty.cypher (16 lines)
CLEAN (post-filter after the vector call is documented).

### pin.cypher (16 lines) — changed by this branch
CLEAN. Two mutually exclusive FOREACH branches; `SET` with a CASE reading `f.salience` first. Note for the docs: unpin
removes a cached salience even if it was not set by the pin (there is no other writer today, so fine).

### restore.cypher (20 lines)
- CLEAN for correctness under its own contract. L16 `*1..5` in a comprehension enumerates paths (fan-in 3 at depth 5 =
  243 paths; fine).
- CLARITY: the taint guard is 5 hops while `lineage/forget_source` / `quarantine` cascade up to 12 (default 8). The header
  says the guard only covers data from before the cascades included dormant facts, so the gap is old data at depth 6-12
  only — say so, or align the depth.

### scope_facts.cypher (11 lines)
CLEAN. `ORDER BY created_at … LIMIT $scan` reads all active facts of the scope (inherent; caller caps scan at 5,000).

### suspect_reason.cypher (19 lines)
CLEAN.

### sweep_apply.cypher (28 lines)
CLEAN; the documented one-WHERE + single-OPTIONAL-MATCH-last shape. Note (Python, not Cypher): D-013 added
"salience ≥ 0.5 protects", checked in Python before the ids are passed; the in-statement re-check does not include it.
A fact that became salient between listing and applying (a new verification, a second using agent) can still be swept.
Low impact (sweeps are reversible); worth one header line.

## view/

### flow.cypher (17 lines)
CLEAN. `ToolCall(at)` index range, LIMIT before the OPTIONAL MATCHes.

### indexes.cypher (8), labels.cypher (8), relationship_types.cypher (8)
CLEAN.

### inventory_edges.cypher (75 lines)
- CLEAN for correctness; the 35 types match exactly the relationship types used anywhere in `plexus/queries` (checked by
  grep), and the scan fallback covers drift.
- SIMPLIFICATION: length is inherent (one O(1) count per type; a `MATCH ()-[r]->() RETURN type(r), count(r)` is O(edges),
  which is what the `_scan` twin is for). The maintainable fix is generation from one list shared with
  `inventory_nodes`, `inventory_keys` and `subgraph` (18 labels × 3 files + 35 types today, kept in sync by tests).
  Confidence the generated output is identical: high (pure text); value: medium (removes 4 hand-synced lists).

### inventory_edges_scan.cypher (8), inventory_nodes_scan.cypher (8)
CLEAN (documented O(n) fallbacks; `labels(n)[0]` is fine while no node carries two labels).

### inventory_keys.cypher (40 lines), inventory_nodes.cypher (41 lines)
CLEAN; 18 labels match the labels used in the queries. Same generation note as `inventory_edges`.

### inventory_memory.cypher (15 lines)
CLEAN. Six `CALL {}` counts, no double counting between `marked` and `due`.

### maybe_duplicates.cypher (12 lines)
CLEAN. CLARITY: "at most 5 per fact" is the write-side `MAYBE_CAP` of `engram/assert_fact`, not enforced here (and the
engram audit found that cap keeps storage order, not nearest-first).

### scope_lookup.cypher (10 lines)
- BOUNDEDNESS (low, live PROFILE): `MATCH (s:Scope) WHERE ($id <> '' AND s.id = $id) OR (…)` plans a `Node By Label
  Scan` of every Scope, on every read tool call that names a scope. Scopes are few today; they grow if callers create
  per-session/per-task scopes.
- SIMPLIFICATION (safe): two gated branches, each an index seek (`Scope(id)` and `Scope(name)` are indexed):
  ```
  MATCH (s:Scope {id: $id}) WHERE $id <> '' RETURN s.id AS id, s.kind AS kind, s.name AS name
  UNION
  MATCH (s:Scope {name: $name}) WHERE $id = '' AND s.kind = $kind RETURN s.id AS id, s.kind AS kind, s.name AS name
  ```
  (the caller keeps the first row; `LIMIT 1` per branch). Confidence high; verify the plan with PROFILE.

### step_agents.cypher (10 lines)
BOUNDEDNESS (low, by reading): `s.n <= $n` is a `Step(n)` range read over every Step up to n — it grows with history,
not with the number of agents as the header says; `LIMIT 200` bounds only the output. Read-only, View only.

### subgraph.cypher (121 lines)
- CLEAN for correctness (live: 2,000/2,000 edges recovered; 18 branches = 18 labels).
- Length is inherent to plan-shape item 6b (one index range seek per label; an unlabeled scan is an All Node Scan).
  Measured 90 ms at the 2,001-node API maximum with ~2,000 edges, so carrying `ns` as a grouping key (L107) is not a
  practical problem at the cap. SIMPLIFICATION = generate the 18 branches (see `inventory_edges`); do not hand-collapse.

## Clean files (19 of 22)
activation: entity_fan (clarity only), novelty, pin, restore (clarity only), scope_facts, suspect_reason, sweep_apply —
view: flow, indexes, inventory_edges, inventory_edges_scan, inventory_keys, inventory_memory, inventory_nodes,
inventory_nodes_scan, labels, maybe_duplicates (clarity only), relationship_types, subgraph.
Files with a non-clarity finding: `activation/activation` (confirmed semantic bug), `view/scope_lookup`, `view/step_agents`
(low boundedness).
