# Independent cross-check of the neuro-memory survey and implementation plan

Written 2026-10-17 by a second orchestrator pass over the same brief. The brief's delegation budget was 0, so two
orchestrator instances ran the survey themselves in this worktree at the same time: one produced the numbered notes
`00…06-*.md`, `NEUROSCIENCE_MEMORY_SURVEY.md` and `MEMORY_FORGETTING_IMPLEMENTATION_PLAN.md` (commit 9c2f6f2); this
pass produced six slug-named notes on the same mechanisms independently, from the same repo evidence and its own
searches (those files were removed from the working tree by the concurrent pass before they could be committed; their
unique content — verified constants, computed tables, and the design deltas — is folded into §2, §3 and the appendix
here rather than re-issued as a duplicate set). Rather than overwrite the committed survey and plan with a
near-duplicate, this document records where the two passes agree, where they differ, and what the second pass
verified that the plan marks `[unverified]`. It is the "independent
review after a major change" the owner asks for, applied to the plan before any code is written.

## 1. Agreement (the conclusions are robust to who did the survey)

Both passes, without seeing each other's notes, reached:

1. **The decay curve is not the defect; the combination rule is.** ACT-R adds base-level activation to a cue-driven
   context term and thresholds; Plexus multiplies relevance by a squashed activation, which can only reorder
   near-ties, and L5b's near-ties are twins where popularity is the wrong tie-breaker.
2. **Top pick: pattern separation at recall** — resolve the query's entity with the existing `Entity.name`
   full-text index, lift facts about the named entity with an ACT-R fan penalty `S − ln(fan)`, report lures instead of
   writing suppression. Both predict recall@1 75.7% → ≥ 90% on L5b and both say a SQL arm handed an entity lookup
   and `GROUP BY` fan ties by construction; the honest claim is "beats flat retrieval, attributable to structure".
3. **Second: forgetting that cannot cost recall** — additive bounded activation, Pavlik-Anderson
   activation-dependent decay (massed reads self-limit), graded outcome-weighted salience that modulates decay and
   replaces the `max(A, A0)` lift; protection stays a sweep rule.
4. **Third: prediction-error-gated updating** (Beta posterior moved only by outcome/PE events, plain recall inert,
   a penalty for the weaker side of an unresolved contradiction); measurable only on an injected correction set.
5. **Deferred: consolidation / replay** (Need × Gain tiers, SHY-style renormalisation, co-recall or returned-unused
   signals): fixes the sweep's lossiness, does not move recall@k, costs the most.
6. **Guard rails:** salience ≠ confidence; asking ≠ using; recall writes nothing; `as_of`/`why`/`knew_at`/
   `fact_history` ignore every new term; nothing is deleted; publish the SQL tie.

## 2. Verified in this pass (resolves `[unverified]` markers in the plan)

| Plan item | Status after this pass | Source opened |
|---|---|---|
| Pavlik & Anderson constants `c = 0.217, a = 0.177` (plan §1 table, "[unverified constants]") | **Confirmed** from the full text: Eq. 4 `d_i = c·e^{m_{i−1}} + a`, Eq. 5 `m_n = ln Σ t_i^{−d_i}`; Table 1: decay intercept `a = 0.177`, decay scale `c = 0.217` (their Experiment 1); `a = 0.217, c = 0.143` for the Bahrick 30-day data; threshold `τ = −0.704`, noise `s = 0.255`, interference scalar `h = 0.025` (between-session "psychological time") | `act-r.psy.cmu.edu/…/409s15516709cog0000_14.pdf` |
| `s_noise = 1.0 nat` "ACT-R convention [unverified]" (plan §1) | ACT-R's fitted `s` is **0.255** in Pavlik & Anderson; with `s = 0.255` the logistic moves from 50% to 88% recall over 0.5 nat, so a `tanh((A − A0)/(2s))` band saturates inside ±1 nat. Under the new decay scale the hot–cold span is ≈ 2.4 nats (table below), so `s = 1.0` is the better *engineering* choice for a band that still discriminates; keep it, but cite it as a design choice, not an ACT-R constant | same |
| `S_ji = S − ln(fan_j)`, retrieval probability `1/(1 + e^{−(A−τ)/s})` | **Confirmed** (ACT-R declarative summary; Anderson & Reder 1999 for the fan effect's empirical base) | `mathematicalpsychology.com/ACT_R_Declarative`, PubMed 10406105 |
| Sevenster 2013: prediction error required for destabilisation | **Confirmed** from the Science abstract/editor's summary (CS alone → labile, blockable by propranolol; CS+US together → not labile) | `science.org/doi/10.1126/science.1231357` |
| Cepeda 2008 optimal-gap ratios | Consistent with the paper as read (gap ≈ 20–40% of a 7-day RI, ≈ 5–10% of a 350-day RI; 1,354 participants) | `laplab.ucsd.edu/articles/Cepeda et al 2008_psychsci.pdf` |
| FSRS stability update shape `(e^{w(1−R)} − 1)` | **Confirmed** (FSRS-4.5/5/6 formulas on the algorithm wiki) | `github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm` |
| STC window ~1–2 h; Dunsmoor 2015 retroactive, delay-dependent | **Confirmed** at abstract level | Nature nrn2963; PMC4432479 |

## 3. Disagreements and gaps found in the plan (recommended changes before hand-off)

### 3.1 The sweep threshold breaks under the new activation scale (bug, not a judgement call)

Plan §3.3 keeps `memory_sweep`'s threshold at `A0 − 2` and says "verify". Computed here under Pavlik-Anderson with
`a = 0.177` (`A0_PA = ln(86400^−0.177) = −2.01`):

| Age of a once-created, never-used fact | standard `d = 0.5` (`A − A0`) | `a = 0.177` (`A − A0_PA`) |
|---|---|---|
| 30 days | −1.70 | **−0.60** |
| 60 days | −2.05 | **−0.73** |
| 90 days | −2.25 | **−0.80** |

Today `A0 − 2` means "untouched for ~55 days". Under the new scale a single-creation fact reaches `A0_PA − 2` after
~80,000 days, so `memory_sweep` would never select anything. **Set the threshold to `A0_PA − 0.72`** (same ~55-day
meaning) and make the regression test assert the age, not the number. This also affects the plan's §5.1 noise-share
targets for any `+sweep` mode.

### 3.2 Hub entities get no lift at all; add the predicate as a second cue

Plan §1: `sep = γ·ent_match·max(0, 1 − ln(fan)/S_max)` with `S_max = ln 50`, so an entity with ≥ 50 facts gives
**zero** lift, and the plan's hub variant (§5.3, 200 facts of distinct predicates) is then answered by relevance alone.
ACT-R does not zero the cue; it sums over cues, and the query in every L5b probe carries a second cue, the
**predicate**, whose fan is "facts with this predicate in scope" (≈ 20 in L5b, 1 in the hub variant). Recommended
(appendix A.3): `C = Σ_cues w_cue·(S − ln fan_cue)` with `w_entity = 0.6`,
`w_predicate = 0.4`, `S = 5` (so a fan of 148 still gives a small positive lift), and the conjunction entity ∧
predicate naturally identifies one fact even on a hub. Keep the plan's hub variant as the test that decides between
the two forms.

### 3.3 Candidate starvation: add the named entity's facts to the candidate set

Plan §2.2 applies `sep` to rows the vector/keyword search already returned. On L5b the over-fetch (`4k`, up to 512)
contains the target, but at 5k entities / 50k facts (L6-C scale) the named entity's facts may be outside the vector
top-k and the post-filter (`PLEXUS_REPORT.md` §6.9 item 2). Add the resolved entities' current facts to the candidate
union with the existing `engram/recall_hop_facts.cypher` shape (entity-first, bounded `per_entity`), at hop 0. One
extra bounded read; it also makes the plan's L6-C arm meaningful.

### 3.4 Trace inheritance on supersede is missing from P3

A fact created by `verify_fact(changed)` or `assert_fact(supersede=true)` starts with no use history, no salience and
the prior reliability, while its twins in other scopes keep theirs: the corrected value is a cold newborn. Plan §4
updates the *old* fact (`rel_b += 2`) but gives the new one nothing. Recommended (appendix A.4): `Fact.inherited_from = old.id` set in `backdate.cypher` / the supersede branch, and in `activation.cypher` one
`OPTIONAL MATCH (f)-[:SUPERSEDES]->(p:Fact) WHERE p.id = f.inherited_from` whose events (up to `f.valid_from`) count at
weight 0.5, salience likewise. Cheap, and it is the one P3 effect that would show on a plain correction probe without
injected task failures. Add "currency@1 of corrected facts" to §5.2.

### 3.5 Latent-cause auto-supersede at cosine > 0.6 is too aggressive

Plan §4.3(b): supersede a current fact "unused for > 30 d and `cosine(new, current) > 0.6`". With bge-small, unrelated
sentences about the same entity routinely exceed 0.6 (the P9 duplicate work needed discriminator keys precisely
because cosine alone merged "enabled"/"not enabled"; `PLEXUS_REPORT.md` §8.4). Keep the flag default `off` as the
plan says, and when it is tried, require the P9 duplicate guards (numbers, units, negation, comparatives) to pass and
the predicate to be identical; otherwise this re-introduces false merges that C7 extended drove to 0/150.

### 3.6 Keyword bypass over `fact_text`: isolate it, it may be most of the L5b gain

The plan's `kw-fix` (test the bypass against `fact_text(entity, predicate, value)` instead of `value`) was missed by
this pass and is a good catch: every L5b probe's words appear in the target's `fact_text`, so the exact-match bypass
alone may lift recall@1 close to the target. The plan already isolates it as a mode (§5.1 hypothesis 2). Add the
caveat that the bypass is binary and lexical: it does nothing for paraphrased entity names or for L6-C, which is what
the fan term is for. Report the split.

### 3.7 Smaller points

* `activation.cypher` already hit 6.0.2 planner bugs with multiple pattern comprehensions in one projection
  (`docs/forgetting.md` "FalkorDB 6.0.2 behaviours"); the plan adds `agents_use` and `artifacts_ok` comprehensions —
  add them one at a time with the activation regression tests after each.
* Salience cache invalidation (`salience_at ≥ newest relevant edge`) needs the newest-edge time, which is a second
  read; simpler v1: recompute always (the activation read already gathers the inputs) and cache later if profiling
  says so.
* `score()` uses `ln(rel)`; `rel = 1 − cosine distance` can be ≤ 0 for seeds beyond the index's typical range
  (distance > 1 occurs for cosine distance on opposed vectors); the `−inf` guard handles it, but the keyword union can
  return such rows — confirm they are dropped rather than ranked.
* Both passes' weights (`γ`, `β`, `δ`, `ρ`, `κ`) are declared defaults; neither has a fit. The plan's §5.1 "measure
  the rank-1/rank-2 gap in `off`" is the right first step; record the distribution in `docs/BASELINE.md`.

## 4. What the second pass adds beyond the plan (optional, later)

* An automatic `verify_after` from activation (a spaced-repetition review queue via
  the existing `facts_to_verify`), which the plan keeps as a suggestion only; agreed for this phase.
* Read-time tag-and-capture (a recall READ whose Step then `WROTE` a Decision counts as a
  use) — the plan's deferred capture rule, in a write-free form that only touches `activation.cypher`'s inputs.
* A `CO_RECALLED {n, last}` edge built by a bounded consolidation pass from Recall/RETURNED pairs where one fact was later used, as the Need proxy, versus the plan's returned-but-unused counter;
  the plan's counter is cheaper and should be tried first.
* A `VEC-ONLY` arm (facts, vector + BM25, no entity table) beside the
  SQL arm, so the report can show the two claims separately with a real flat-retrieval control rather than only
  Plexus's own `off` mode.

## 5. Verdict

The plan is sound and ready for hand-off after the §3.1 threshold fix (required), with §3.2–3.4 recommended as small
additions to P1/P3 and §3.5 as a guard on an already-off flag. The two passes' agreement on the diagnosis and the
ranking, reached independently, is the strongest evidence this survey can offer that the picks are not an artefact
of one reading of the literature. The expected outcome is unchanged and should be written down before the first run:
P1 raises recall@1 on L5b by ≥ 10 points over `off`; P2 makes forgetting free rather than costly; P3 shows only on a
correction set; the SQL tie survives on every quality metric, and the honest differentiator is structure-attributable
retrieval over flat baselines plus explanation.

## Appendix: the second pass's unique computations and design deltas

### A.1 Activation under the two decay scales (L5b classes, 90 simulated days, weights as in `docs/forgetting.md`, newest 50 events)

| Access history | standard ACT-R `d = 0.5` (today) | Pavlik-Anderson `a = 0.177, c = 0.217` |
|---|---|---|
| neutral `A0` (created once, 1 day ago) | −5.68 | −2.01 |
| hot: 5 reads/day for 90 days (newest 50 count) | −2.72 (A0 + 2.96) | −0.43 (A0 + 1.58) |
| critical: created + one `use` 90 days ago | −7.24 (A0 − 1.56) | −2.64 (A0 − 0.63) |
| cold: created 90 days ago, never read | −7.93 (A0 − 2.25) | −2.81 (A0 − 0.80) |
| 7 spaced reads at 1, 3, 7, 14, 30, 60, 89 days | −5.12 | −1.75 |
| 50 massed reads within one hour, 45 days ago | −3.67 | −1.75 |

Reading: today 50 massed reads beat 7 spaced reads by 1.45 nats; under activation-dependent decay they tie, and the
hot–cold span halves (5.2 → 2.4 nats). The plan's `tanh` band and `beta` should be sized to the 2.4-nat span.

### A.2 Fan arithmetic for the L5b probe

Probe `"<Acme Notes API S07> <api_version>"`: entity cue fan ≈ 12 (7 real + 5 noise facts ABOUT that entity),
predicate cue fan ≈ 20 (one per sprint). With `S = 5`, `w_entity = 0.6`, `w_predicate = 0.4`: the named fact gets
`0.6·(5 − ln 12) + 0.4·(5 − ln 20) ≈ 1.26 + 0.80 = 2.06` nats of context; its S08 twin gets only the predicate share,
0.80. The gap (1.26 nats) is 2.5× the 0.5-nat step that moves ACT-R recall probability from 50% to 88% at `s = 0.255`.
The twins are not a near-tie under a cue-structured score; they are a near-tie only under cosine.

### A.3 Predicate cue and candidate union (delta to plan P1)

```cypher
// name: engram/cue_fan  (ro, bounded): fan and direct facts of each resolved entity cue, plus RELATES neighbours
UNWIND $entity_ids AS eid
MATCH (e:Entity {id: eid})
OPTIONAL MATCH (e)<-[:ABOUT]-(f0:Fact)
  WHERE f0.status IN $statuses AND f0.valid_from <= $t AND $t < f0.valid_to
WITH e, collect(DISTINCT f0.id) AS direct
OPTIONAL MATCH (e)-[r:RELATES]-(n:Entity)
WITH e, direct, collect(DISTINCT {id: n.id, kind: r.kind})[0..$hop_cap] AS neigh
RETURN e.id AS cue, size(direct) AS fan, direct, neigh
```

Predicate fan: `MATCH (f:Fact {predicate: $p}) WHERE … RETURN count(f)` (range index on `Fact.predicate`; cap at
1,000). Candidate union: `direct` ids join the vector/keyword seeds before scoring (shape of `recall_hop_facts.cypher`,
entity-first). Context term in Python: `C = Σ_cues w·(S − ln max(fan, 1))` for facts ABOUT the cue entity or with
the cue predicate; half weight over one `RELATES` hop. Scope filtering of `direct` happens in Python against the
`sids` list recall already computes.

### A.4 Trace inheritance on supersede (delta to plan P3)

In `staleness/backdate.cypher` (and the same-agent supersede branch of `assert_fact`), after `MATCH (old), (nw)`:

```cypher
SET old.beta = coalesce(old.beta, 1) + 2, old.last_pe_at = $now,
    nw.alpha = coalesce(old.alpha, 1), nw.beta = 1, nw.inherited_from = old.id
```

In `activation/activation.cypher`: `OPTIONAL MATCH (f)-[:SUPERSEDES]->(p:Fact) WHERE p.id = f.inherited_from`, gather
`p`'s decisions/handoffs/use READs/verifications once (one comprehension per relationship type, as the file
requires), and in Python add them at weight 0.5 for events with `t <= f.valid_from`; salience inherits the same way.
The `CONTRADICTS` path (different agent, no supersede) inherits nothing.

### A.5 Sweep threshold under the new scale

Single-creation fact: 30 d → `A0_PA − 0.60`, 60 d → `A0_PA − 0.73`, 90 d → `A0_PA − 0.80`. Today's `A0 − 2` means
~55 days unused; the equivalent is `A0_PA − 0.72`. `A0_PA − 2` is reached after ~80,000 days (never, in practice).

### A.6 Sources opened by the second pass that the plan's notes do not list

Wixted & Ebbesen 1991 (journals.sagepub.com/doi/10.1111/j.1467-9280.1991.tb00175.x); Anderson 1974
(doi.org/10.1016/0010-0285(74)90021-8); Rolls 2013 (frontiersin.org/articles/10.3389/fnsys.2013.00074); McCloskey &
Cohen 1989; O'Reilly et al. 2014 (pubmed 22141588); Joo & Frank 2018 (nature.com/articles/s41583-018-0077-1); Mattar &
Daw 2018 (princeton.edu/~ndaw/md18.pdf); Tse et al. 2007 (pubmed 17412951); Tononi & Cirelli 2019 (PMC6612535);
McGaugh 2004 (pubmed 15217324); Roozendaal & McGaugh 2011; Dunsmoor et al. 2015 (PMC4432479); Karpicke & Blunt 2011
(science.org/doi/10.1126/science.1199327); Lindsey et al. 2014; Lee 2009 (doi.org/10.1016/j.tins.2009.05.002);
Nader, Schafe & LeDoux 2000 (nature.com/articles/35021052); Elsey, Van Ast & Kindt 2018 (pubmed 29792441).
