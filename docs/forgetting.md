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
* A fact at `A₀` gets multiplier `0.75`; far above it, `1.0`; far below it, the floor (`0.9` by default).
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
`recall` events after `suspect_since` are ignored. A `use` still counts.

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
