# Activation-based forgetting (P7-K, D-012)

Plexus does **not delete memories because they are old**. It *ranks* them by how much they are used, and it can
*park* faded ones (`dormant`) so they stop cluttering recall. Parking is optional, dry-run by default and fully
reversible. The decision and its evidence are in `docs/DECISIONS.md` D-012 and `docs/research/forgetting-*.md`.

## What it does

| Where | Behaviour |
|---|---|
| `recall` (default on) | Fetches `2k` candidates, scores `final = relevance × (floor + (1 − floor)·σ(A − A₀))`, cuts to `k`. A relevant but unused fact keeps at least half of its relevance, so it can still surface. |
| `assert_fact` | Stores `Fact.surprise` once, at write time (below). |
| `READ` edges | Carry `via: 'recall' \| 'use'` and `at`, so being *shown* is not counted as being *used*. |
| `memory_strength` | Explains one fact's activation, multiplier and protection. Read-only: asking is not using. |
| `memory_sweep` | Lists (dry run, default) or moves to `dormant` the faintest unprotected facts. Never deletes. |
| `restore_fact`, `pin_fact`, `unpin_fact` | Undo a sweep; protect a fact by hand. |

`as_of`, `why`, `why_recalled`, `who_knew`, `knew_at`, `fact_history` and lookups by id never apply forgetting:
history is not rewritten. `recall(as_of=…)` also includes `dormant` facts.

## The formula

```
A(f)  = ln( Σ_events  w · max(now − t, 60 s)^(−d)  +  surprise_bonus )          time in seconds, d = 0.5
final = relevance × ( floor + (1 − floor) · σ(A − A₀) )                          relevance = clamp(1 − rank, 0, 1)
```

* The sum runs over the fact's **newest K = 50** events. `rank` is the cosine distance after the sibling boost.
* `A₀` (neutral) is the activation of a fact created once, one day ago: `ln(86400^−0.5) = −5.68`.
* A fact at `A₀` gets multiplier `0.95` (`floor + (1 − floor) / 2`, i.e. `(1 + floor) / 2`); far above it, `1.0`; far below it, the floor (`0.9` by default).
* Protected facts use `max(A, A₀)`, so they are never ranked below neutral.
* **Exact keyword hit:** a fact that the full-text index returned *and* whose value contains every query keyword
  (words of ≥ 3 characters, at most 10) has multiplier 1.

The model is the ACT-R base-level equation (`docs/research/forgetting-A-science-and-papers.md` §1.3).
`tests/activation/test_model.py` checks it against that table (1 h ago → −4.09, 1 d → −5.68, 90 d → −7.93,
accesses at 1/3/7/14/30 d → −4.81, …).

### Events and weights

| Event | Source in the graph | Weight |
|---|---|---|
| creation | `Fact.created_at` | 1 |
| re-assert | `ASSERTED_BY.at` after creation (another agent endorsing it) | 1 |
| decision | `Decision.created_at` of a `BASED_ON` | 1 |
| handoff | `Handoff.created_at` of a `CARRIES` | 1 |
| use | `READ {via:'use'}` (a decision, a handoff, an `assert_fact` duplicate / supersede / contradiction) | 1 |
| recall | `READ {via:'recall'}`, or a `READ` without `via` (data from before P7) | 0.3 |
| verification | `VERIFIED_BY.at` (written by P7-J) | 2 |

A decision that rests on a fact is therefore counted twice (the `BASED_ON` edge and the `READ` the tool call made).
That is the contract's table applied literally; it favours decision-supporting facts, which are protected anyway.

### Surprise (write time, never recomputed)

`Fact.surprise ∈ [0, 1]` is set once by `engram/assert_fact`:

| Case | Surprise |
|---|---|
| contradicts another agent's current fact | 0.9 |
| supersedes a current fact (same agent, or `supersede=true`) | 0.6 |
| otherwise | novelty `= min(0.5, max(0, 1 − maxcos))` to the 5 nearest **active** facts of the same scope |
| first fact of an empty scope | 0.5 |
| duplicate | nothing stored (no new fact) |

It adds `1 + round(4·surprise)` pseudo-events at creation time (rounding half up). It is separate from `confidence`:
surprise raises priority, not truth. Novelty uses one extra vector read before the single assert statement (the
vector index has no scope pre-filter, so 20 are fetched and filtered to the scope).

### Suspect facts

A fact is *suspect* if `verify_state = 'suspect'` or `verify_after` has passed (P7 contract). Recall still
**returns** it, with `verify_state`, `suspect_since` and `suspect_reason` (`changed in <commit or 'working tree'>
(<first path>)`, `review date passed`, or `marked suspect`). A suspect fact is **not strengthened by recall**:
a `recall` READ written while the fact was suspect (`READ.suspect`, the contract rule at the READ's time, so also a passed
review date) is ignored, and stays ignored after the fact is verified again; a back-dated doubt (`suspect_since` before the
read) and READ edges that have no flag are judged by the fact's current state. A `use` still counts.

## Protected facts

Reported as `protected: true`; they use `max(A, A₀)` in recall and are never swept:

* `pinned`;
* `BASED_ON` by a Decision whose `flagged` is not true;
* `CARRIES`-ed by any Handoff (no handoff state exists, so any carrying handoff protects);
* the start of a `SUPERSEDES` edge, or either end of a `CONTRADICTS` edge;
* derived (`DERIVED_FROM`, up to 3 hops) from a Source with `trust = 'high'`.

`Source.trust` is the **string** `'normal'` or `'high'` (P7-int decision): only `'high'` protects. `add_source` /
`create_source` accept `'normal'`, `'high'`, or (for older clients) a number 0..1, which never had an effect and now means
*no opinion*: a new source is `'normal'`, an existing one keeps its trust (so a plain re-registration does not demote a
`'high'` source). Data written before P7 holds a float (1.0); it reads as `'normal'` and is rewritten as such the next
time the source is registered.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `PLEXUS_FORGETTING` | `on` | `off` = recall is exactly the earlier retrieval order. `recall(forgetting=…)` overrides it. |
| `PLEXUS_ACT_DECAY` | `0.5` | `d` |
| `PLEXUS_ACT_A0` | −5.68 (1 day) | neutral activation |
| `PLEXUS_ACT_FLOOR` | `0.9` | lowest multiplier. At `0.5` popular near-twin facts outranked the relevant one (Crucible L5b); `0.9` is the confirmed default |
| `PLEXUS_ACT_EVENTS` | `50` | `K`, newest events counted (1..200) |
| `PLEXUS_ACT_MODE` | `mult` | D-013: `mult` = the formula above; `add` = the additive banded score below (opt-in; its pre-registered L5b test failed, see D-013) |
| `PLEXUS_RECALL_SEPARATION` | `on` | D-013 P1: entity resolution + fan-damped lift + damped sibling expansion + lures (below). `recall(separation=…)` overrides it |
| `PLEXUS_KW_BYPASS` | `fact` | the exact-keyword bypass tests `entity predicate: value` (`fact`) or the value alone (`value`, the pre-D-013 rule) |
| `PLEXUS_ACT_CUES` | `entity+predicate` | the context term: the entity and predicate cues summed (CROSS_CHECK §3.2); `entity` = the single damped entity term P1 first shipped |
| `PLEXUS_ACT_CUE_S`, `PLEXUS_ACT_W_ENTITY`, `PLEXUS_ACT_W_PREDICATE` | `5`, `0.03`, `0.02` | ACT-R `S` (a cue with fan ≥ e^S ≈ 148 adds nothing) and the cue weights (CROSS_CHECK's 0.6 / 0.4 scaled by 1/20; see below) |
| `PLEXUS_ACT_GAMMA`, `PLEXUS_ACT_SMAX` | `0.15`, `ln 50` | the single-cue form (`cues=entity`); `S_max` is also the fan at which the sibling expansion is damped to nothing |
| `PLEXUS_ACT_BETA`, `PLEXUS_ACT_S`, `PLEXUS_ACT_C`, `PLEXUS_ACT_A`, `PLEXUS_ACT_DMAX`, `PLEXUS_ACT_KAPPA`, `PLEXUS_ACT_DELTA`, `PLEXUS_ACT_BAND` | `0.05`, `1.0`, `0.217`, `0.177`, `1.0`, `0.4`, `0.03`, `0.02` | `add` mode constants (below) |

Bad values fail loudly (`ValueError`), they are not silently defaulted.

## Sweep and restore (optional)

`memory_sweep(scope, threshold=None, dry_run=True, limit=200)`:

1. looks at the oldest ≤ 5000 active facts **of that scope** (not inherited ones);
2. keeps unprotected, non-suspect facts with `A < threshold` (default `A₀ − 2 = −7.68`, a fact nobody has used for
   about 60 days), faintest first, at most `limit`;
3. `dry_run=false` moves them in one bounded statement (`activation/sweep_apply`): `status = 'dormant'`,
   `prior_status`, `dormant_at`. **Protection is re-checked inside that statement**, so a fact that became
   protected after the listing is skipped.

`restore_fact` puts `prior_status` back and removes both helper properties: **sweep then restore leaves the graph
identical** (`tests/activation/test_sweep_restore.py` dumps every node and edge before and after). Dormant facts are
hidden from `recall` unless `include_dormant=true`.

## D-013: pattern separation (on) and the additive mode (opt-in)

Research: `docs/research/NEUROSCIENCE_MEMORY_SURVEY.md`, `MEMORY_FORGETTING_IMPLEMENTATION_PLAN.md`, `neuro-memory/`.

**Pattern separation at recall (P1, `PLEXUS_RECALL_SEPARATION=on`).** Before the vector read, `engram/recall_entities`
matches the query's words against `Entity.name` (full-text OR, ≤ 5 entities) and counts each entity's **fan**: its
current facts in the searched scopes. An entity is *named* only when every word of its name is in the query, so
"Acme Notes API S07 api_version" names `Acme Notes API S07` and not its `S08` twin. The named entities' own
current facts join the candidates (one bounded read in the `engram/recall_hop_facts` shape, the `2k` nearest per
entity; CROSS_CHECK §3.3), so a named entity's fact is never missed because the vector over-fetch did not reach it.
The **predicate** is the second cue (CROSS_CHECK §3.2): a candidate's predicate counts as named by the same rule
(every word of it in the query; `api_version` is the words `api` and `version`), and `engram/recall_predicates`
counts its fan = current facts with that predicate in the searched scopes. Each candidate gets the context term

```
sep = w_entity · max(0, S − ln fan_entity) + w_predicate · max(0, S − ln fan_predicate)
      # w_entity = 0.03, w_predicate = 0.02, S = 5; a cue the fact does not match contributes 0
```

in log-relevance (ACT-R's `C = Σ W_j (S − ln fan_j)`): on the L5b probe the named fact gets `0.03·(5 − ln 12) +
0.02·(5 − ln 20) ≈ 0.115` nats, its same-entity sibling `0.075` (= the P1 lift at fan 12), its other-entity twin
`0.04` — the entity cue separates the entities, the predicate cue separates the facts of one entity, and the
weights are sized to the measured twin gaps (p50 0.017, p90 0.07 nats) so the cues decide near-ties and nothing
else. CROSS_CHECK §3.2 recommended `0.6 / 0.4`; that scale was run as registered and raised the noise share by
4–11 points for no recall gain (every fact about the named entity, noise included, outranked every fact about any
other entity); the `1/20` scale was chosen post hoc and then confirmed in a pre-registered run (`docs/BASELINE.md`
"Predicate cue results" and the confirmatory section after it). A cue is floored at 0, so a hub cue (fan ≥ e^5 ≈
148) adds nothing and never subtracts; a fan of 50 still adds a little (the first form zeroed it).
`PLEXUS_ACT_CUES=entity` restores the first form, `sep = gamma · max(0, 1 − ln(fan) / S_max)` (`gamma = 0.15`,
`S_max = ln 50`), the predicate ignored. In
`mult` mode `final = relevance × multiplier × e^sep`. The sibling expansion of `engram/recall` is damped by the
entity fan (`rank = d − boost · damp`, `damp = max(0, 1 − ln fan / S_max)`). Each row reports `entity_match`,
`predicate_match`, `sep` and `lures` (other candidates with the same predicate about another entity within 0.02
relevance: "this row has a near-identical competitor, check the entity"); `Recall.entities`/`separation` and
`RETURNED.sep` make `why_recalled` explain the lift. Nothing is written by a recall. The exact-keyword bypass
tests the whole fact text. Cost: two more bounded reads per recall when the query names an entity (the entity's
facts, the predicate fans): 6 round trips with forgetting on.

**Additive mode (P2, `PLEXUS_ACT_MODE=add`).** `plexus.activation.score`:

```
score = ln(rel) + beta · tanh((A − A0) / 2s) + sep + sal      # beta = 0.05, s = 1 nat
A     = activation_spaced(events): d_i = min(d_max, c · e^{m_{i−1}} + a), c = 0.217, a = 0.177   (Pavlik & Anderson 2005)
sal   = +delta · salience inside the relevance band (rel ≥ rel_top − eps), −delta · s_max_band outside it when the
        band holds something critical (s_max_band ≥ 0.8), else 0                                 # delta = 0.03, eps = 0.02
```

Every term is bounded, so the relevance order is kept except among near-ties. Activation-dependent decay makes a
burst of massed reads worth about one read while spaced reads keep their value (`tests/activation/test_score.py`);
a recall after the fact's last use is a *restudy* worth `0.3 · (1 − σ(m_prev − A0))`. **Salience** `s = 1 − e^{−Σ w·n}`
is read from the graph in the same `activation/activation` round trip (unflagged decisions 1.0, verifications 1.5,
independently verified artifacts of the decisions' tasks 1.0, done tasks 0.5, distinct using agents − 1 at 0.5,
handoffs 0.5, trusted source 1.0, pin 3.0); it slows decay (`d · (1 − kappa · s)`, `kappa = 0.4`), protects from
sweeps at `s ≥ 0.5`, is cached on `Fact.salience` by `pin_fact` and shown by `memory_strength` (`salience`,
`salience_inputs`, per-event `decays`, `act_term`, `fan`, `entity_lift`, `suggested_verify_after`). Salience never
feeds `confidence`. Under the new scale `A0 = −2.01` and the sweep's default threshold is `A0 − 0.72` (still "about
55–60 days unused"; `A0 − 2` would never fire). `max(A, A0)` for protected facts is replaced by the band guard.

**What the pre-registered L5b run showed (`docs/BASELINE.md` "L5b-D013", D-013).** P1: recall@1 75.7% → 85.7%,
recall@5 100%, every cross-entity displacer gone; the 0.90 target was **not reached**. The D-013 reading of the
residual ("same-entity facts with another predicate") was wrong: the predicate-cue run (`docs/BASELINE.md`
"Predicate cue results") found that all 20 remaining displacers are the scenario's 20 `CONTRADICTS` pairs — two
active `auth_method` facts per sprint subject, same entity, same predicate, both probes — so **85.7% is the recall@1
ceiling of L5b for any scorer that does not read the value**, and P1 had already reached it. The predicate cue
therefore changes no L5b rank; it fixed the last 5 of 200 probes of the plan's §5.3 hub variant (97.5% → 100%,
where relevance alone already answered 195) and removes the zero-lift-at-fan-50 edge of the first form. The §3.3
candidate union adds ~5 points of noise share on L5b (the named entity's noise facts always become candidates;
"complete about the named entity" is what the noise metric penalises). Shipped default measured in the
confirmatory run (`sep+mult` at 0.03 / 0.02): recall@1 85.7%, recall@5 100%, noise share 20.6–20.9%, critical
loss 0, cross-entity displacers 0.
P2 at its declared constants: **falsified** (70.0%); the additive term and the in-band salience lift together
re-created the twin problem, and at the strength where they stop costing recall they also stop reducing noise. So
`add` stays opt-in and `mult` + separation is the default (85.0% / 100% / noise 22.1%, vs D-012's 65.0% / 95.7% /
14.9%). The noise share is higher than under D-012 alone because the entity lift also lifts noise *about the named
entity* over real facts about other entities.

## Honest limits (what this does *not* claim)

* **Ranking-only forgetting at floor 0.9 is the default. The sweep is lossy for cold real facts and stays optional, dry-run by default, and reversible.** Measured (Crucible L5b, `docs/BASELINE.md`): at the first default, floor 0.5, recall@5 fell from 98.6% to 73-75% on a 20-sprint history of near-identical facts and 7-8 of 80 critical probes were outranked by popular twins (so the default was changed). At floor 0.9 (confirmatory, pre-registered, one run): critical loss 0, recall@5 96.4% against 98.6% with forgetting off, recall@1 63.6% against 75.7% (the more used of two near-identical facts is first more often), noise share 24.0% -> 15.1%. After a real sweep recall@5 is 88.6% (cold facts that nobody used for 90 days are what a sweep hides: 14 cold real facts and 160 noise facts moved; 0 critical); read the dry run first, `restore_fact` undoes it, and `PLEXUS_FORGETTING=off` restores the earlier retrieval order exactly.
* **It is a ranking and a tidy-up, not an accuracy gain.** The research found decay changes accuracy by ~0–1 points
  and can hurt when an old fact is needed; the benefit is less noise and cost. The pre-registered Crucible L5 ran
  (`docs/BASELINE.md`): at floor 0.9 recall@5 is 2.2 points below forgetting off in the confirmatory run; no accuracy claim is made.
* The weights, the 0.3 and `A₀ − 2` are defaults chosen from the literature, not tuned on Plexus data. The floor (0.9) was chosen after the first L5b run failed at 0.5 and then confirmed in a separate pre-registered run (`docs/BASELINE.md`); it is tuned on one synthetic scenario.
* Activation is computed from the newest 50 events, so a very heavily used fact does not keep growing.
* A fact that a sweep parked is still **current** for `assert_fact` (P7-02): a new value supersedes it (or, from another
  agent without `supersede`, contradicts it) like an active fact, and asserting the same value again wakes it
  (`status = prior_status`) instead of creating a twin. `restore_fact` refuses (`reason: 'already_superseded'`,
  `superseded_by`) a dormant fact for which a newer active fact of the same entity, predicate and scope already exists
  (data from before this rule); a recorded `CONTRADICTS` does not block a restore.
* `forget_source` and `quarantine_source` also reach `dormant` facts (P7-int), so a dormant fact derived from a forgotten
  source becomes `forgotten` and `restore_fact` leaves it alone; a quarantined dormant fact is released back to
  `dormant`. `restore_fact` also refuses (leaves dormant) a dormant fact derived from a forgotten or quarantined fact,
  which guards data swept before that rule.
* The sweep scans at most 5000 facts of a scope per call; the report says `scan_truncated`.
* Two multiple-counting effects are deliberate (decision = `BASED_ON` + `READ use`; a new agent's duplicate
  assert = `ASSERTED_BY` + `READ use`).

## Benchmark (`activation/activation`, slice 3)

`uv run python -m tests.activation.bench_activation 10000 50` builds 10 000 facts with 50 `READ` edges each
(500 000 edges) and times the lookup for 50 random fact ids (30 runs), FalkorDB 6.0.2 in Docker on this machine:

| | server `run_time_ms` | client wall time (incl. Docker port forward) |
|---|---|---|
| 2 000 facts × 50 reads | median 11.1, p95 14.1, max 17.5 | median 61 ms |
| 10 000 facts × 50 reads | **median 10.8, p95 12.3, max 16.7** | median 57 ms |

The budget was < 30 ms server time; it is met with ~3× headroom and does not grow with the number of facts (each id
is an index seek). The `READ` list is the only unbounded one and is cut to the newest 50 per fact inside the
statement.

## FalkorDB 6.0.2 behaviours found while building this

Each of these returned a wrong answer *without an error*; the tests pin them.

1. Several pattern comprehensions in one projection, or two comprehensions over the same relationship pattern,
   returned `[]` for some of them (`activation/activation` reads each relationship type once, before the
   aggregation).
2. A `WHERE` inside a pattern comprehension that mixed `f.created_at` and `$now` misbehaved the same way.
3. A chain of `OPTIONAL MATCH … count()` stages gave wrong counts for the later ones, and a variable-length
   `OPTIONAL MATCH` after an aggregation matched nothing, which would have swept a *trusted* fact
   (`activation/sweep_apply` uses pattern predicates in one `WHERE`).
4. `[x IN collected WHERE …]` next to pattern comprehensions fails with a type error.
5. An `OPTIONAL MATCH` over a label or relationship type that does not exist yet returns no match instead of
   failing, so recall works on a graph with no `Change` / `SUSPECTED` / `VERIFIED_BY` (verified).
6. Ties in vector distance come back in no fixed order (the baseline itself differs between runs); the
   "forgetting off is identical" test compares score groups, not positions inside a tie.
