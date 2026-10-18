# Memory forgetting and retrieval upgrade: implementation plan (hand-off spec)

> **STALE (2026-10-18):** the numbers in this document were measured on builds before the current main (7618d18) and are not valid for it until re-run. Build per number: [docs/NUMBERS_STATUS.md](../NUMBERS_STATUS.md).

Branch `feature/neuro-memory-research`. Companion: `NEUROSCIENCE_MEMORY_SURVEY.md` (why) and
`docs/research/neuro-memory/0N-*.md` (per-mechanism detail and sources). This document is the spec a coding
subagent implements. **Read `neuro-memory/CROSS_CHECK.md` first**: an independent pass found one required fix
(the sweep threshold under the new decay scale, §3.1 there) and four recommended additions (predicate cue, candidate
union, trace inheritance, a guard on the latent-cause flag). It picks three techniques, in priority order, and states for each what changes, how it is
measured, and how confident the author is that it moves a number.

## 0. The picks, and the honest expectation

| # | Technique | Targets | Expected effect | Confidence it shows a measurable gain |
|---|---|---|---|---|
| P1 | **Pattern separation at recall**: query entity resolution + fan-damped entity lift + keyword bypass over the full fact text + lure reporting | L5b near-twin displacement; the 24% of probes `off` already gets wrong at rank 1 | recall@1 75.7% → ≥ 90% (`off` → `sep`); the forgetting loss disappears | **High vs flat retrieval (`off`, B2). Low vs a SQL arm given an entity lookup + GROUP BY fan: tie by construction.** |
| P2 | **Forgetting that cannot cost recall**: additive banded activation, activation-dependent (spacing-aware) decay, salience-modulated decay with the band guard | the 12-point recall@1 loss and the 2.2-point recall@5 loss of `on`; massed-read twins; protected-twin displacement | `sep+add` within 0.01 of `sep` on recall@1/5, noise share ≤ 15% kept; burst-read twins ranked below spaced ones | **High that it removes the loss. Low that it wins anything on its own: it is a prior, not a likelihood.** |
| P3 | **Prediction-error-gated reliability** (reconsolidation): Beta posterior on each fact moved by outcomes in the outcome's own write statement; reliability term in the score; `why_confidence` | wrong facts that were used and then contradicted by outcomes keep their rank today | wrong twin drops below the right fact in ≥ 90% of injected pairs (vs ~50%) | **High on the injected benchmark. Low that it matters on current recordings (0 outcome-caused failures exist).** |

Deferred (designed in notes 02 and 05, not in this hand-off): `consolidate(scope)` with gists and SHY-style
"returned-but-unused" demotion; tagging-and-capture over step chains. Both are sound and bounded, but neither
moves recall@k, and both need data (step-level recall/use pairs, multi-step outcomes) that the benchmarks do not
generate yet. They are the next phase after P1–P3 land.

**What "beats SQL" can honestly mean here.** Every scoring rule below is computable by a SQL arm that is handed
the same columns, and the benchmark must hand them over (§5). The claims this plan can support are: (1) Plexus's
recall beats flat retrieval (its own `off` mode, which is what B2 and a SQL+embeddings arm do) by a pre-registered
margin on near-twins; (2) forgetting is now free; (3) the signals are already in the graph, are computed in the
same read as the vector seeds, and every rank is explained by `why_recalled`/`memory_strength`; (4) one family
(multi-hop separation through typed relations, L6-C) needs recursive SQL that the arm must be written to have.
Do not write "beats SQL on retrieval quality" in the report unless the L6-C family shows it with the SQL arm's
code budget stated.

## 1. Scoring: one function, four axes

New module `plexus/src/plexus/activation/score.py` (pure, no DB), used by `rank.rerank`:

```python
def score(rel, *, A, A0, s_noise, beta, ent_match, fan, S_max, gamma, salience, in_band, s_max_band, delta,
          reliability, rho, bypass) -> float:
    """ln-relevance plus bounded additive terms. Returns -inf for rel <= 0."""
    if rel <= 0: return float("-inf")
    base = math.log(min(rel, 1.0))
    if bypass:                                   # exact match of every query word in fact_text: relevance only
        return base
    act = beta * math.tanh((A - A0) / (2 * s_noise))                       # P2: in (-beta, beta)
    sep = gamma * ent_match * max(0.0, 1.0 - math.log(max(fan, 1)) / S_max)  # P1: 0 for hub entities
    sal = delta * salience if in_band else (-delta * s_max_band if s_max_band >= 0.8 else 0.0)  # P2 guard
    rel_term = rho * math.log(max(reliability, 1e-3) / 0.67)                # P3: 0 at the prior
    return base + act + sep + sal + rel_term
```

Defaults (all overridable by `PLEXUS_*` env, validated in `Settings` like today's):

| name | default | source |
|---|---|---|
| `beta` | 0.05 | note 01 §3.1; set from the measured rank-1/rank-2 gap (§5.1 reports it) |
| `s_noise` | 1.0 nat | ACT-R convention [unverified default; benchmark it at 0.5/1/2] |
| `gamma` | 0.15 | note 04 §3.2 (≈ 16% relative lift; twin gaps ≤ 3%) |
| `S_max` | ln 50 ≈ 3.91 | note 04: an entity with ≥ 50 facts gets no entity lift |
| `delta` | 0.03 | note 05 §3.4 |
| band `ε` | 0.02 (relevance units) | note 05 §3.4 |
| `rho` | 1.0 | note 06 §3.5 |
| `kappa` (salience → decay) | 0.4 | note 05 §3.2 |
| `c`, `a` (activation-dependent decay) | 0.217, 0.177 | Pavlik & Anderson 2005 [unverified constants; confirm in full text before freezing] |

Ordering: `score` desc, then vector rank, then id (unchanged tie rule). `PLEXUS_FORGETTING=off` and
`PLEXUS_RECALL_SEPARATION=off` together must reproduce today's order exactly (existing test
`tests/activation/test_rank_off_identical.py` or equivalent stays green). `PLEXUS_ACT_MODE=mult` keeps the old
multiplier for A/B runs; default becomes `add` after §5.1 passes.

## 2. P1: pattern separation at recall

### 2.1 Query entity resolution (new query `engram/recall_entities.cypher`, mode ro)

```
// name: engram/recall_entities
// purpose: the entities a recall query names (full-text on Entity.name), with each one's fan of current facts; bounded to $limit entities
// params: q:str, scope_sids:list[str], limit:int, statuses:list[str], t:int
// returns: entity_id, name, score, fan
CALL db.idx.fulltext.queryNodes('Entity', $q) YIELD node AS e, score
WITH e, score ORDER BY score DESC LIMIT $limit
OPTIONAL MATCH (e)<-[:ABOUT]-(f:Fact)-[:IN_SCOPE]->(s:Scope)
WHERE f.status IN $statuses AND f.valid_from <= $t AND $t < f.valid_to AND s.id IN $scope_sids
RETURN e.id AS entity_id, e.name AS name, score, count(f) AS fan
```
`$q` is the recall query's words of ≥ 3 characters, at most 10, joined by `|` (the same tokeniser as
`recall_keywords`). `limit = 5`. Add an exact pass on `Entity.norm_name` (`engram/find_entity_exact`, exists) for
the query's full normalised text, merged first with `score = +inf`. One extra read per recall; measure it in
`tests/integration/test_p5_plans.py` style (must stay an index seek, not a label scan).

6.0.2 notes: `queryNodes` with a `|` query is the P9 entity-resolution path and is already covered by tests;
`count(f)` after `OPTIONAL MATCH` with a `WHERE` on both ends is fine when there is one aggregation in the
statement (the `activation.cypher` gotchas concern comprehensions next to aggregations).

### 2.2 `rank.rerank` changes

- New inputs: `entities: Mapping[entity_id, fan]`, `words`, `settings`.
- `ent_match = row["entity_id"] in entities`; `fan = entities[row["entity_id"]]`.
- Bypass test becomes `_contains_every(fact_text(entity_name, predicate, value), words)` (today: `value` only).
  This alone is expected to fix a share of L5b; §5.1 isolates it as its own mode (`kw-fix`).
- `lures`: for each kept row, ids of other candidates with the same `predicate`, a different `entity_id`, and
  `cosine(f, g) ≥ 0.9` (computed from the stored embeddings in Python; the rows already carry the vectors? If not,
  add `n.embedding` to the `engram/recall` projection behind a flag, or compute `lures` from `score` proximity
  `|score_f − score_g| < 0.02` as the cheap v1). Returned as `lures: [ids]` on the row; never written.

### 2.3 Fan-damped sibling expansion (`engram/recall.cypher`)

In the expansion block (lines 40–50): bind `fan_e = size([(e)<-[:ABOUT]-(:Fact {status:'active'}) | 1])` in a
separate `WITH` before the `collect(...)[0..$sibs]`, and use
`rank = CASE WHEN s.d − $boost · damp < 0 THEN 0.0 ELSE s.d − $boost · damp END` with
`damp = CASE WHEN fan_e >= 50 THEN 0.0 ELSE 1.0 − log(fan_e) / 3.91 END` (6.0.2 has `log()` natural; verify, else
pass `S_max` and precompute `ln(fan)` in a `WITH`). Keep the entity-first plan shape (P5 review Q1); add a plan
assertion to `test_p5_plans.py` that the expansion still starts at the Entity.

### 2.4 `why_recalled` / `Recall` node

`Recall` gains `entities: [ids]` and `separation: true|false`; `RETURNED` gains `sep` (the `sep` term) alongside
`rank, score`. `why_recalled` prints "entity match (fan 7): +0.11". `memory_strength` prints `entity_match`,
`fan`, `lures`.

### 2.5 `resolve_contradiction(fact_id)` (read-only tool; optional for P1, cheap)

Query and Python scoring as in note 04 §3.5. Returns both sides with the support breakdown and a recommendation;
never writes. MCP contract test required (the guard that every tool has one).

## 3. P2: forgetting that cannot cost recall

### 3.1 `activation/model.py`

```python
def activation_spaced(events, *, now, created_at, surprise, c, a, d_max=1.0, kappa_s=0.0, max_events=50):
    ev = sorted((e for e in events if e.t <= now), key=lambda e: e.t)[-max_events:]
    ds = []
    for i, e in enumerate(ev):
        if i == 0: m_prev = float("-inf")
        else:      m_prev = math.log(sum(ev[j].w * _age(e.t, ev[j].t) ** -ds[j] for j in range(i)))
        d_i = a if m_prev == float("-inf") else min(d_max, c * math.exp(m_prev) + a)
        ds.append(d_i * (1.0 - kappa_s))              # salience slows every term's decay (note 05 §3.2)
    total = sum(e.w * _age(now, e.t) ** -ds[i] for i, e in enumerate(ev))
    total += surprise_events(surprise) * _age(now, created_at) ** -(a * (1.0 - kappa_s))
    return math.log(total) if total > 0 else float("-inf")
```
`_age(t1, t0) = max(t1 − t0, 60_000) / 1000`. `A0` is recomputed for the new model as "one event one day ago"
(`ln(86400^−a)` with `a = 0.177` → −2.01; it is a settings property, not a literal). Keep `activation()` (today's)
for `PLEXUS_ACT_MODE=mult`.

Testing-effect weights (note 03 §3.1): in `service._one`, a `recall` READ later than the fact's last `use` gets
`w = 0.3 · (1 − σ(m_prev − A0))`; this needs `m_prev`, so move the weight assignment into the model loop
(`Event` gains `kind`; the loop applies the rule for `kind == "recall"`).

### 3.2 Salience (`Fact.salience`, `Fact.salience_at`)

Computed in `activation/service._one` from the row (the comprehensions in `activation.cypher` already return
decisions, handoffs, verified_at, sources; add `agents_use: [distinct agent ids of READ via:'use']` and
`artifacts_ok: count` through `(d:Decision)-[:DECIDED]->(:Task)<-[:FOR]-(:Artifact)-[:VERIFIED_BY {independent:true}]->()`
bounded by the existing `[0..20]` slices). Formula in note 05 §3.1. Cache: the statements that create those edges
(`record_decision`, `verify_fact`, `verify_artifact`, `complete_task`, `handoff`, `pin_fact`) `SET f.salience`
on the facts they touch (≤ 200 per statement, inside the existing write). Read path uses the cached value when
`salience_at ≥ newest relevant edge`, else recomputes (one-line check in Python).

Protection: `protected = pinned or s ≥ 0.5 or <today's boolean rules>` (boolean rules remain as the floor).
`pin_fact` sets `salience = max(salience, 0.95)`; `unpin_fact` recomputes.

Band guard (note 05 §3.4): `in_band = rel ≥ rel_top − ε`; `s_max_band = max salience among in-band rows`. Protected
facts outside the band get `−delta·s_max_band` only when something in the band is critical. This replaces
`max(A, A0)` for protected facts in `add` mode (keep it in `mult` mode).

### 3.3 Sweep / review

- `memory_sweep` threshold: `A0 − 2` under the new `A0` ("about 60 days unused" must still hold; verify with the
  table in note 01 and adjust the constant in `Settings` with a comment).
- Automatic `verify_after` (note 03 §3.3) is **optional** in this phase: implement only `set_review_date`'s
  default suggestion (`memory_strength` reports `suggested_verify_after`) and do not write it automatically.

## 4. P3: prediction-error-gated reliability

### 4.1 Schema

`Fact.rel_a: float` (absent = 2.0), `Fact.rel_b: float` (absent = 1.0), `Fact.rel_at: int`. Read with
`coalesce`. `reliability = rel_a / (rel_a + rel_b)`.

### 4.2 Writes (inside the outcome's own statement; bounded; second statement only where 6.0.2 forces it)

| tool / query | change |
|---|---|
| `relay/fail_task.cypher` | append the `DECIDED → BASED_ON` walk from note 06 §3.3; `rel_b += 1` on ≤ 50 facts used within 24 h |
| `lineage/forget_source.cypher`, `quarantine.cypher`, `staleness/backdate.cypher` (they `SET d.flagged`) | same walk from the flagged decisions; `rel_b += 1`; bounded by the existing per-level caps |
| `staleness/verify_confirm.cypher` (creates `VERIFIED_BY`) | `SET f.rel_a = coalesce(f.rel_a, 2.0) + 0.5, f.rel_at = $now` |
| `relay/verify_artifact.cypher` with `independent = true` and a passing outcome | walk `Artifact -[:FOR]-> Task <-[:DECIDED]- Decision -[:BASED_ON]-> Fact` (≤ 20 decisions, ≤ 50 facts); `rel_a += 0.5` |
| `verify_fact(changed)` | on the superseded fact `rel_b += 2` (history views show it as unreliable at its end) |
| `record_decision` unflagged | nothing (retrieval without prediction error does not reconsolidate) |

`FOREACH (f IN fs | SET …)` after an aggregation is the form to try first; if the 6.0.2 planner rejects it in a
given statement, carry the ids in Python and run a second bounded `UNWIND $ids … SET` as `verify_fact` already
does for the backdate, and record that the two are not atomic (as PLEXUS_REPORT §9.3 does for `link_step`).

### 4.3 `assert_fact` latent-cause branches (note 06 §3.4)

Two new branches in `engram/service.assert_fact` (Python decides, the single assert statement is unchanged apart
from receiving `supersede=true`): (a) current fact `reliability < 0.5` → supersede, keep `CONTRADICTS` as history
edge; (b) current fact unused for > 30 d and `cosine(new, current) > 0.6` → supersede. Both behind
`PLEXUS_ASSERT_LATENT_CAUSE=on|off` (default `off` until C3/C7 are re-run; they count open contradictions as a
feature and need a new criterion: "contradictions later resolved by an outcome close; others stay open").

### 4.4 `why_confidence(fact_id)` (read-only tool)

Returns `confidence`, `reliability`, `rel_a`, `rel_b`, and the outcome events with their paths (note 06 §3.6).
Uses `rel_at` plus the existing edges; no new edge type.

## 5. Benchmark plan (pre-register in `docs/BASELINE.md` before any run)

### 5.1 L5b re-run, same seed (20261016), N = 5 and N = 15, 0 LLM calls

Modes, run in this order so each isolates one change:

| mode | what is on |
|---|---|
| `off` | today's flat order (control; must equal the committed 20261015T205321Z-floor09 `off` numbers within id noise) |
| `on-mult` | today's default (control) |
| `kw-fix` | only the keyword bypass over `fact_text` |
| `sep` | P1 (entity resolution + fan + lures), forgetting off |
| `sep+add` | P1 + P2 (additive banded activation, spacing-aware decay, salience band guard) |
| `sep+add+rel` | + P3 (needs the correction variant, §5.2; on plain L5b it must equal `sep+add` within 0.005) |

New measurements: the rank-1/rank-2 relevance gap distribution in `off` (sets `beta`); the class of rows above the
target per mode (the post-hoc diagnostic becomes a standard column); server `run_time_ms` of the new entity read.

Pre-registered hypotheses and decision rules:
1. `sep` recall@1 ≥ 0.90 and recall@5 ≥ `off` − 0.005; critical loss 0. **Falsified** if recall@1 < 0.85.
2. `kw-fix` alone: report its recall@1; if it already reaches ≥ 0.88, say so and treat the fan/entity term as
   the hub-entity mechanism only (§5.3), not as the L5b fix.
3. `sep+add` recall@1 ≥ `sep` − 0.01; recall@5 ≥ `sep` − 0.005; noise share ≤ 15.5% (today's `on-mult` 15.1%,
   rounded up for id noise). **Falsified** if recall@1 drops more than 1 point: then P2 still costs recall and
   `beta` is too large.
4. Rows above the target of class `critical` or `hot` under `sep+add`: ≤ 5 (today 82 + 7).
5. Burst variant (hot twins read 90 times inside one hour at day 45 instead of daily): under `sep+add`, a burst
   twin outranks a cold target in ≤ 1% of probes; under `on-mult` it does whenever the relevance gap < 0.06.

### 5.2 L5b-correction variant (for P3)

Inject a wrong twin for 20% of real facts (second agent, plausible wrong value → `CONTRADICTS`); record a decision on
the wrong twin and `fail_task` its task at day 30; `verify_fact(confirmed)` the right fact once. Hypotheses:
wrong twin below the right fact in ≥ 90% of injected pairs under `sep+add+rel` (≈ 50% under `sep+add`);
uninjected probes unchanged within 0.005; uninjected facts keep the prior reliability.

### 5.3 Hub variant (for the fan term)

One entity with 200 active facts of distinct predicates; probes name entity + predicate. Hypothesis: `sep`
recall@1 ≥ 0.9; a flat entity boost without the fan term (`S_max = ∞`) returns an arbitrary fact of the hub in
the top 5 for ≥ 30% of probes.

### 5.4 The SQL arm (B1h) and what to claim

Extend `crucible/backends/sqlite_h.py` with: an `entities` FTS table for the query lookup, `GROUP BY entity_id`
fan, the same event table for activation, and `rel_a/rel_b` columns updated by the same rules. Run `sep+add+rel`
on both arms. **Pre-registered expectation: a tie on recall@1/5 between Plexus and B1h on L5b and its variants.**
Report Plexus's server time for the combined read vs SQLite's, the number of statements each needs (Plexus: 3
reads: entities, keywords, recall + 1 activation read; SQLite: the equivalent queries), and the lines of SQL
written for the arm (the L6 rule). The claim that survives: Plexus beats flat retrieval by the §5.1 margins; SQL
given the same features ties; Plexus explains every rank.

Then, as the only family where a quality gap vs SQL is plausible: **L6-C multi-hop recall** (`hops=1..2` through
`RELATES`) with the separation lift propagated per hop (`−ln(fan)` per hop), SQL arm with a recursive CTE written
under the same code budget as L6-A/B. Pre-register "tie expected on correctness; report the arm's code size and
latency"; a loss for Plexus on latency at depth is likely (L6-A: SQL 192 vs 595 ms on 5,000-fact blasts).

### 5.5 Guards that must stay green

C7 extended (0 false merges / 150), L1 C1–C8 (0 violations), L5a, the MCP snapshot test (new tools need contract
tests and `docs/mcp.md` rows), `docs/queries.md` (new `.cypher` files listed), `test_docs_consistency.py`.

## 6. Order of work, gates

1. **P1 + `kw-fix`** (half a day): `recall_entities.cypher`, `rank.rerank` changes, bypass fix, lures,
   `why_recalled`/`memory_strength` fields, plan test for the entity read. Gate: §5.1 modes `off`, `kw-fix`,
   `sep` run and committed with the pre-registration.
2. **P2** (one day): `score.py`, `activation_spaced`, salience cache in the six write statements, band guard,
   settings + validation, `mult` kept. Gate: §5.1 `sep+add`, burst variant, hub variant.
3. **P3** (one day): schema, the five outcome statements, `why_confidence`, latent-cause flag (default off).
   Gate: §5.2.
4. **B1h extension + L6-C** (one day): §5.4. Gate: the tie is published either way.
5. Docs: `docs/forgetting.md` rewritten for the four axes; D-013 in `DECISIONS.md` (additive scoring; pattern
   separation; reliability); PLEXUS_REPORT §7/§8/§9 updated with the numbers and the tie.

Each step is one worktree and one dedicated FalkorDB container (D-005); never the hackathon's `plexus-db-NN`
ports without allocation by the orchestrator.

## 7. Confidence and shortcomings, stated plainly

- **Most confident:** P1 raises L5b recall@1 by ≥ 10 points over `off`. The mechanism is almost embarrassingly
  simple (the query names the entity; use it), and part of the gain may come from the one-line keyword fix. Report
  that split; it is a finding, not a disappointment.
- **Confident but not a win:** P2 turns forgetting from "costs 12 points of recall@1 for 9 points of noise" into
  "costs ~0 for ~9 points". That is the user's stated goal of biological forgetting that improves signal-to-noise
  rather than storage, and it is what the science supports; it is not an accuracy gain and the docs must not call
  it one.
- **Least confident:** P3 on real data. The rule is right and cheap, and it is the only one of the three that
  encodes *consequence* rather than *use*; but current recordings contain no outcome-caused failures, so until
  real multi-step runs (L3 at ≥ 5 runs per arm, PLEXUS_REPORT §10.2) produce them it is idle machinery proven on an
  injected benchmark.
- **The SQL tie will survive on the quality metric.** Every rule here is a function of columns a relational arm
  can hold. The defensible differentiators remain the ones PLEXUS_REPORT §8 already states (signals in the graph
  by construction, one-query computation, deterministic explanation) plus whichever multi-hop family (L6-C) shows
  a code-budget or latency gap. Write the report that way, and publish the tie.
