# Cypher review: `plexus/queries/relay/` + `plexus/queries/staleness/` (17 + 14 = 31 files, 544 lines)

Read-only audit on `feature/neuro-memory-research` (HEAD e126875). This bucket was reviewed by the orchestrator itself
(the run's delegation cap allowed only 2 subagents, used for `engram/` and `lineage/`). Method: every file read against
the three FalkorDB 6.0.2 skills (silent-wrong-answers, big-write quirks, plan-shape), `FALKORDB_REFERENCE.md` §2 and
`CLAUDE.md` §6-7; callers checked in `plexus/src/plexus/relay/` and `staleness/service.py` for caps
(`MAX_CHANGES = 200`, `MAX_AFFECTED = 2000`, `SCAN_CAP = 5000`, create_tasks ≤ 500 tasks).

Live checks: throw-away graphs `audit_orch_*` on plexus-db-13 (all deleted), queries loaded verbatim from the
`.cypher` files (comment lines stripped). Scratch scripts: `$TMPDIR/audit_orch*.py`, outside the repo.

## SUMMARY

| Severity | Count | Items |
|---|---|---|
| CONFIRMED BUG | 0 | — |
| CONFIRMED PERFORMANCE / BOUNDEDNESS (live PROFILE) | 1 pattern, 6 files | `x.id IN $list` with an **empty** list is a full scan of that label's id index, also inside serialised writes: `complete_task`, `fail_task` (empty `$artifact_ids`), `create_tasks` (empty `$ext_dep_ids`, the common case), `handoff` (empty artifact/fact lists), `record_decision` (empty `$fact_ids`, allowed), and the read-only `missing_refs`. Measured: 3,000 Artifacts → 3,000 records read by `complete_task` with no artifacts; 1 record with one id. |
| SUSPECTED, NOT CONFIRMED | 0 | Every trap suspected from reading was run live and did not reproduce (list below). |
| BOUNDEDNESS RISK (by reading) | 3 | `mark_changed` carries 4-9 lists as grouping keys through 10 aggregations (measured fine at the 2,000 cap, see section); `suspect_ids` takes an arbitrary `cap` sample before impact ranking; `docs_to_update` reads all Changes since `$since` (0 = all). |
| SIMPLIFICATION | 3 | `complete_task`/`fail_task` are 24/25-line near-copies; `docs_to_update` L10-12 two WITHs collapse to one; `mark_changed` 5-level hand-unrolled cascade could come from `gen_impact_queries.py` (like the 12-hop lineage cascades) — recommended only together with a depth decision, see section. |
| CLARITY | 6 | `mark_changed` header L8 "as lineage/forget_source does" is stale (forget_source is now 1..12 hops, default 8; mark_changed is fixed at 5); `task_status` two aligned `collect`s; `handoff`/`record_decision` silently ignore an unknown non-empty `step_id`; `source_by_uri` `LIMIT 1` without ORDER BY; `create_tasks` relies on caller dedup of `$ext_dep_ids`; `heartbeat` header fine but no agent existence check (by design). |
| CLEAN | 23 files | listed at the end |

### Traps checked live and NOT reproduced
- `mark_changed` L83 + L90 both `MERGE (ch)-[:TOUCHED]->(an)` for the same changed anchor in two FOREACHs (big-write
  quirk 6 says a second MERGE may not see the first): **one** TOUCHED edge per anchor (a1: 1, a2: 1).
- `mark_changed` L25 `OPTIONAL MATCH (sa:CodeAnchor {path: cp}) WHERE sa.symbol <> ''` after an aggregation (the quirk
  the header itself documents for L58-60): the file-level `cover` entry did reach the symbol anchor and its fact
  (`fact_ids: [f1, f2]`).
- `facts_to_verify` L27-28: two pattern comprehensions in one RETURN after two aggregations: both lists populated
  (`['/x.py#foo', 'doc://1']`).
- `missing_refs` L8/10/12, `create_tasks` L16, `handoff` L13: `OPTIONAL MATCH ... WHERE x.id IN $l` after a `collect`
  (quirk 1): all ids found, create_tasks with an external dep created 2 nodes + 2 edges, handoff wrote 3 CARRIES.
- `claim_next_task` L15-17 `OPTIONAL MATCH ... WHERE d.status <> 'done'` + count (the "WHERE on OPTIONAL MATCH drops the
  owning row" trap): a task whose only dependency is done was claimed.

---

## relay/

### agent_exists.cypher (7 lines)
CLEAN. One index seek; header matches.

### claim_next_task.cypher (23 lines)
CLEAN. Live: correct claim with a done dependency; ORDER BY … LIMIT 1 before the SET/CREATE (eager writes) as the header
says. Reads every `open`/`claimed` task through the `Task(status)` index (PROFILE: 2 records with 3,000 done tasks), so the
cost follows the open backlog, not history — acceptable and inherent to a global priority order.

### complete_task.cypher (25 lines)
- **CONFIRMED PERFORMANCE (live PROFILE), L14:** `OPTIONAL MATCH (e:Artifact) WHERE e.id IN $artifact_ids` with
  `$artifact_ids = []` (a completion without artifacts) is a `Node By Index Scan` over every Artifact: 3,000 records for
  3,000 artifacts, inside the serialised write. With one id it is 1 record. Same root cause as plan-shape skill item 4.
  Fix (skill item 4, keeps one row for the CAS check):
  ```
  // before
  OPTIONAL MATCH (e:Artifact) WHERE e.id IN $artifact_ids
  WITH a, t, count(e) AS duplicates
  // after
  UNWIND CASE WHEN size($artifact_ids) = 0 THEN [''] ELSE $artifact_ids END AS aid
  OPTIONAL MATCH (e:Artifact {id: aid})
  WITH a, t, count(e) AS duplicates
  ```
  Confidence: high that it removes the scan (same shape `view/maybe_duplicates` and `engram/recall` already use);
  `a, t` stay grouping keys so the row survives. Untested here.
- SIMPLIFICATION (optional, low value): `fail_task` is this file plus `t.fail_reason = $reason` and a different status.
  One `relay/finish_task` with `$status` and `$reason` would remove 25 lines; keep the two files if the separate names
  matter to the metering / tool-call audit (they do appear in `ToolCall.query_name`).

### create_tasks.cypher (30 lines)
- **CONFIRMED PERFORMANCE (live PROFILE), L16:** with `$ext_dep_ids = []` (a batch with no external dependency, the
  common case) the `x.id IN $ext_dep_ids` branch scans the whole Task id index (3,001 records for 3,001 tasks). Same fix
  pattern as `complete_task`; careful: L14-17 are key-less aggregations (always one row) — keep them key-less.
- CLARITY: the guard `size(found_ext) = size($ext_dep_ids)` (L18) is wrong if `$ext_dep_ids` has duplicates; the
  Python caller de-duplicates, but the header doesn't say so (it says it for `handoff`/`record_decision`). Add
  "de-duplicated" to the params line.
- Otherwise CLEAN: live run with one external and one in-batch edge created 2 nodes and 2 edges; zero-row behaviour of
  L24 (`collect` with no key → one row) matches the header.

### dependents_of.cypher (15 lines)
CLEAN. Bind-first plan shape (P9-b) as documented; caller bounds levels/nodes.

### existing_artifacts.cypher (7 lines), existing_tasks.cypher (7 lines)
CLEAN for correctness. Same empty-list scan as above, but these are read-only diagnostics on the reject path and callers
only call them with non-empty lists — no action.

### fail_task.cypher (26 lines)
Same CONFIRMED PERFORMANCE finding as `complete_task` (L14) and the same fix. See the simplification note there.

### handoff.cypher (21 lines)
- **CONFIRMED PERFORMANCE (live PROFILE), L11 and L13:** empty `$artifact_ids` → scan of all Artifacts; empty
  `$fact_ids` → scan of all Facts (3,000 each in the fixture). A handoff that carries only facts (or only artifacts)
  pays one full scan. Fix as above, once per list (two UNWIND+OPTIONAL MATCH+collect blocks).
- CLARITY: L10/L20 — a non-empty `$step_id` that does not exist silently writes no WROTE edge (the Handoff is still
  created). Fine for crash-consistency, but the header's "zero rows = some … does not exist" list should say step_id is
  best-effort.

### heartbeat.cypher (11 lines)
CLEAN. Holder of an expired-but-not-yet-reclaimed lease may still extend it; that is consistent with the claim rule.

### missing_refs.cypher (13 lines)
CLEAN for correctness (live: all four lists right). Empty-list scans as above, but read-only and only on the error
path.

### ready_tasks.cypher (14 lines)
CLEAN. Same readiness rule as `claim_next_task` (the two copies of L6-10 must stay in sync; a shared comment pointer
exists in the purpose line).

### record_decision.cypher (18 lines)
- **CONFIRMED PERFORMANCE (live PROFILE), L11:** `$fact_ids = []` is explicitly allowed ("a decision with no
  evidence") and scans every Fact (3,000 records). Fix as above.
- CLARITY: unknown non-empty `step_id` silently ignored (same as `handoff`).

### register_agent.cypher (9 lines)
CLEAN.

### reopen_task.cypher (12 lines)
CLEAN. Any registered agent may reopen (by design, header says so via "who retried").

### task_status.cypher (12 lines)
CLARITY (low): `collect(d.id)` and `collect(d.status)` are "aligned" only while no dependency has a null status
(`collect` skips nulls). Tasks are always created with a status, so this cannot misalign today; `collect({id: d.id,
status: d.status})` would make the alignment structural. Also relies on `ORDER BY` before `collect` preserving order
(works on 6.0.2, not guaranteed by openCypher).

### verify_artifact.cypher (13 lines)
CLEAN. MERGE after a WITH (quirk 3 respected); `independent` stored once and recomputed identically on later calls.

## staleness/

### anchor_mismatch.cypher (15 lines)
CLEAN. Deterministic change id makes it idempotent as documented.

### backdate.cypher (21 lines)
CLEAN. Decision list cut at `$max_flag` after a per-fact `collect(DISTINCT)` (bounded by one fact's decisions); MERGE
after WITH; `nw.valid_from` only moved when `$backdate`.

### backdate_point.cypher (10 lines)
CLEAN.

### docs_to_update.cypher (19 lines)
- BOUNDEDNESS (low): L7 reads every Change with `at >= $since`; `$since = 0` reads the whole change history, then L9
  recomputes the doc's own `max(dc.at)` once per (change, anchor, doc) row. Read-only with `LIMIT`, so cost not safety.
- SIMPLIFICATION (safe, small): L10-12 → `WITH ch, a, d, max(dc.at) AS doc_at WITH ch, a, d WHERE doc_at IS NULL OR
  ch.at > doc_at` (drops the boolean CASE and one WITH; a `WITH … WHERE` after an aggregation is the form the skills
  recommend). Confidence high.
- CLARITY: a change that touched two anchors described by the same doc yields two `changes` items with the same
  `change_id` (one per anchor), each consuming a `per_doc` slot. Intended (items carry `anchor`), but worth one header line.

### fact_for_verify.cypher (12 lines)
CLEAN. One comprehension (SUPERSEDES).

### facts_to_verify.cypher (31 lines)
CLEAN (live: two comprehensions after aggregations returned both lists; decision count and newest change right).

### mark_changed.cypher (93 lines)
- Correctness: CLEAN as far as I could test. Live: `cover` reaches symbol anchors (L23-26), TOUCHED is not duplicated
  despite L83/L90 both MERGEing it, suspect state and change id as documented.
- BOUNDEDNESS (measured, acceptable): lists `cc`, `srcs`, `srcs_all`, `aff`, `fa_list`, `l1..l4`, `fs`, `ds` are carried
  as grouping keys through every `WITH …, collect(...)` (L26-63) — the family of plan-shape item 7b that the lineage
  audit confirmed as quadratic in `quarantine`. Measured here with one Source and N facts DERIVED_FROM it (one level):
  N=500 18 ms, 1,000 44 ms, 2,000 148 ms (the `MAX_AFFECTED` cap), 4,000 candidates 299 ms with `truncated=true`.
  Mildly super-linear, well under the 5 s timeout at the cap. Not tested: deep (4-5 level) cascades with thousands of
  facts per level, where the level lists are carried longer — the read side is not capped (only the write is). Recommend
  a PROFILE test at 5 levels × 2,000 before raising `MAX_AFFECTED`.
- CLARITY (stale header) L8: "expanded level by level from the Source, as lineage/forget_source does" — forget_source
  is now a depth-gated 1..12 cascade (default 8), mark_changed is fixed at 5 levels, and `activation/restore`'s taint check
  is `*1..5`. So a fact 6-8 derivations from a changed file is **not** made suspect, but `forget_source` on that file
  would reach it. Not a bug by the current contract (5 is what the header promises), but the three depths should be one
  stated decision. `PLEXUS_REPORT.md` L224 is stale in the same way (reported by the lineage audit).
- SIMPLIFICATION (recommend with care): the L31-45 five-level unroll is a hand copy of what `gen_impact_queries.py`
  generates for lineage. Generating it (and making the depth a parameter) is the safe way to shorten it; hand-editing the
  93-line statement is high risk (it encodes quirks 1, 2, 5, 6 and 7 deliberately; the duplicated CodeAnchor MERGE at
  L70-74 / L85-89 is the required mutually-exclusive-branches form of quirk 6, not redundancy).

### mark_degraded.cypher (8 lines), set_review_date.cypher (8 lines)
CLEAN.

### source_by_uri.cypher (8 lines)
CLARITY (low): `LIMIT 1` without `ORDER BY`; if two Sources share a uri (nothing in the schema forbids it; `Source(uri)`
is a range index, not a constraint) the evidence Source picked is arbitrary. Add `ORDER BY s.created_at, s.id`.

### suspect_ids.cypher (11 lines)
BOUNDEDNESS/RANKING note: each branch is `LIMIT $cap` (5,000) with no order, so when more than 5,000 facts are suspect,
`facts_to_verify` ranks an arbitrary 5,000-10,000 subset "by impact". Fine as a bound; the "ordered by impact" claim in
`facts_to_verify`/docs holds only below the cap. One header line, or `ORDER BY f.suspect_since` per branch if the
oldest suspects should win (that reads the whole range anyway).

### tracked_paths.cypher (8 lines)
CLEAN (up to 2 × limit rows; header says "distinct", which UNION provides).

### upsert_anchor.cypher (23 lines)
CLEAN. MERGE after WITH; `ON MATCH SET` reads `a.hash` before overwriting it (quirk 7 order kept).

### verify_confirm.cypher (14 lines)
CLEAN.

## Clean files (23 of 31: no correctness, performance or boundedness finding; some carry clarity notes)
relay (12): agent_exists, claim_next_task, dependents_of, existing_artifacts, existing_tasks, heartbeat, missing_refs,
ready_tasks, register_agent, reopen_task, task_status (clarity), verify_artifact — staleness (11): anchor_mismatch,
backdate, backdate_point, fact_for_verify, facts_to_verify, mark_degraded, set_review_date, source_by_uri (clarity),
tracked_paths, upsert_anchor, verify_confirm.
Not clean: relay `complete_task`, `fail_task`, `create_tasks`, `handoff`, `record_decision` (confirmed empty-list scan);
staleness `mark_changed` (correct as tested; boundedness note), `suspect_ids`, `docs_to_update` (low boundedness).
