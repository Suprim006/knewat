# Neuroscience-inspired retrieval and forgetting for Plexus: consolidated survey

Branch `feature/neuro-memory-research`, October 2026. Per-mechanism notes with full citations are in
`docs/research/neuro-memory/01…06-*.md`; the shared brief is `00-brief.md`. This document consolidates them and,
for each mechanism, answers one question honestly: **would this move Plexus off the SQL tie on retrieval quality?**
The implementation plan for the picks is `MEMORY_FORGETTING_IMPLEMENTATION_PLAN.md`. A second, independent
orchestrator pass over the same brief wrote the slug-named notes in `neuro-memory/` and the review
`neuro-memory/CROSS_CHECK.md`, which lists where the two passes agree and what the plan should change.

Process note: the brief planned six parallel Sonnet subagents; the one-shot run had no delegation budget, so the
orchestrator did the survey itself. Every source cited in the notes was opened (abstract, PDF or full text);
claims from memory are marked `[unverified]` in the notes and are not relied on for any design decision.

## 0. Starting point (ground truth, not re-litigated)

- Retrieval quality: Plexus's recall has tied a hand-written SQL arm on every structured benchmark (L2, L2-scale,
  L6) and the existing activation-based forgetting has *cost* recall on L5b (recall@1 75.7% → 63.6%, recall@5
  98.6% → 96.4% at floor 0.9) in exchange for a lower noise share (24% → 15%). It has never improved accuracy.
- The L5b post-hoc diagnostic: the rows that displaced the right fact were **protected and hot near-twins from
  other sprints**, not noise. Twins share near-identical text; the discriminating token (the sprint tag) is in the
  entity name.
- Plexus contains no LLM. Every signal must come from edges, timestamps and the local embedding.

## 1. The diagnosis the six notes converge on

Two independent defects, one in the *scoring algebra* and one in the *features*:

1. **Algebra.** `final = relevance × (0.9 + 0.1·σ(A − A0))`. The multiplier spans about 9% between a cold target
   (A = −7.9) and a hot twin (A = −2.8); paraphrase twins differ in relevance by 0.005–0.02. *Any* hot twin
   beats *any* cold target when the relevance gap is under ~0.06 (note 01 §2). ACT-R adds activation to the
   context match and applies a threshold and a noise scale; it never multiplies. At floor 0.5 the range was
   45%, which is why recall@5 fell to 73%.
2. **Features.** The query names the entity (`Acme Notes API S07`). `Entity.name` is full-text indexed and
   `resolve_entity` exists, but `recall` never resolves the query's entity, and the exact-keyword bypass tests the
   fact's *value*, not the entity name (note 04 §2). The one feature that separates lure from target is thrown
   away before ranking. That is a pattern-separation failure in the dentate-gyrus sense.

Everything below is secondary to fixing these two. Decay, spacing, salience and reliability become tie-breakers
and priors once the separation step exists; without it they cannot help, because they carry no information about
*which* twin the query means.

## 2. Mechanisms, what the science says, and the Plexus mapping

### 2.1 Forgetting curves and decay (note 01)

Science. Retention is power-law shaped (Wixted & Ebbesen 1991), and a power law is what a sum of processes at
different timescales looks like (Averell & Heathcote 2011: two timescales over 28 days; Benna & Fusi 2016: a
cascade of synaptic variables gives `~1/√t` with high capacity). Pavlik & Anderson 2005: each practice adds an
increment whose decay rate depends on the activation *at that moment*, so massed practice is self-limiting. ACT-R:
activation is additive, thresholded, noisy.

Plexus mapping. (a) Additive, banded score: `ln(rel) + β·tanh((A − A0)/2s)`, `β ≈ 0.05` set from the measured
rank-1/rank-2 relevance gap, so activation decides near-ties only. (b) Activation-dependent decay per event
(`d_i = c·e^{m_{i−1}} + a`): a burst of 90 reads in one hour counts about as much as one use; 90 daily reads keep
their advantage; 5 spaced uses beat the burst (computed table in note 01 §3.2). (c) Optional two-accumulator
form (`act_fast`, `act_slow`) for scale.

Off the SQL tie? **No, and it does not claim to.** Decay is a prior over need-probability; on a benchmark where
every probe names its target, a prior cannot beat a correct likelihood. Its job is to stop the 12-point recall@1
loss while keeping the noise reduction. Confidence that it does that: high (arithmetic). A SQL arm with the same
timestamps computes the same number.

### 2.2 Consolidation and replay (note 02)

Science. Complementary learning systems (Kumaran, Hassabis & McClelland 2016): interleaved replay, "modulated by
reward or novelty", builds structured knowledge; replay is causal (Girardeau 2009: ripple suppression impairs
memory) and biased by reward-prediction signals; prioritized experience replay (Schaul 2016) is the ML form.
Synaptic homeostasis (Tononi & Cirelli 2014): waking learning "decreases signal-to-noise ratios"; sleep's global
renormalisation and activity-dependent down-selection restore it. Trace transformation: consolidation yields a
gist that coexists with the episode.

Plexus mapping. A `consolidate(scope)` tool in three bounded statements: promote facts with *interleaved* evidence
(≥ 2 agents, a decision, or a confirmed verification, with spaced uses) to `tier = 'consolidated'`; build `Gist`
nodes only over clusters the P9 dedup machinery already confirmed (`DUPLICATES`), and collapse them in recall
(`collapse_gists`); demote by **returned-but-never-used** counts (`returned_unused / returned_used`, maintained at
step close from `RETURNED ∧ READ`) instead of by age. That last rule is the SHY prescription and it fixes the
sweep's known loss: cold-but-true facts are never "returned and ignored ten times", so they are never demoted.

Off the SQL tie? **No on recall@k; yes on what an agent reads.** Gist collapse returns one row per cluster, which
recall@k does not reward; a chars-per-correct-answer metric does. The demotion rule is a join SQL can do.
Confidence: high that SHY-demotion stops hiding cold facts; low that recall@1 moves.

### 2.3 Spacing and testing effects (note 03)

Science. Karpicke & Roediger 2008: after one successful recall, repeated *testing* gives ~80% a week later,
repeated *restudy* 36%; "repeated study after one successful recall did not produce any measurable learning".
Cepeda 2008: the optimal gap is 20–40% of a 1-week retention interval and 5–10% of a 1-year one (optimal gaps 1,
11, 21, 21 days for RIs of 7, 35, 70, 350 days). Bjork's two-strength theory: the storage gain from a retrieval is
larger when retrieval strength is low. FSRS: per-item stability, retrievability `R(t,S) = (1 + f·t/S)^−w`, gain
shrinks with `S` and grows with `(1 − R)`.

Plexus mapping. Pavlik–Anderson increments (shared with 2.1); `recall` reads after the last `use` are restudy and
weigh `0.3·(1 − R_est)`; `use`, `VERIFIED_BY` and independent `verify_artifact` are retrieval tests with full
weight; `who_knew`/`as_of`/`fact_history`/`memory_strength` remain non-events (history must not rewrite itself).
Optional incremental `stab`/`stab_at` properties updated inside the existing `READ`/`VERIFIED_BY` write statement
(FSRS-4.5 form, constants to be fitted on Plexus data, not copied from flashcards). Automatic `verify_after` from
stability, for decision-critical and code-anchored facts only.

Off the SQL tie? **No.** Same reason as 2.1. It removes the massed-read advantage of hot twins (one of the two
displacer classes). Confidence: high on the mechanism, low on a recall win.

### 2.4 Interference, pattern separation, pattern completion (note 04)

Science. Anderson 2003: forgetting is inhibitory control over competitors at the cue. Yassa & Stark 2011, Bakker
2008, Sahay 2011: the dentate gyrus/CA3 treat a slightly different lure as new; more neurogenesis → better
discrimination of similar contexts and nothing else. ACT-R fan effect: `S_ji = S − ln(fan_j)`; a cue attached to
many memories spreads less activation to each (Anderson 2001 slides; Anderson & Reder 1999).

Plexus mapping. (a) Resolve the query's entity(ies) before the vector search (one bounded full-text/exact read on
the indexes that already exist, with each entity's fan). (b) Score `ln(rel) + γ·ent_match·(S − ln fan)/S + β·tanh(z/2)`
with `γ = 0.15`: the named entity gives a lift no paraphrase gap can match, damped for hub entities. (c) Fix the
keyword bypass to test `fact_text(entity, predicate, value)`. (d) Fan-damped sibling expansion in
`recall.cypher` (pattern completion around small entities, not hubs). (e) Report `lures: [ids]` (near-identical
competitors about other entities) instead of writing suppression edges: retrieval-induced forgetting as a
read-time signal, never a graph write. (f) A read-only `resolve_contradiction` tool that scores both ends of a
`CONTRADICTS` pair by graph support (verified, decisions, trust, agents, uses) and recommends; the agent writes.

Off the SQL tie? **This is the one that changes the L5b number.** Pre-registered expectation: recall@1 from 75.7%
(`off`) / 63.6% (`on`) to ≥ 0.90 on the same seed. Against a SQL arm *given* an entity lookup and `GROUP BY
entity_id` for the fan: **a tie on recall@1 by construction**: same rule, same columns. What is graph-native is
that the signals (entity index, fan, provenance for `resolve_contradiction`) exist as a side effect of operation
and are computed in the same read as the vector seeds, and that `why_recalled` can state "ranked first because the
query named its entity (fan 7)". The honest claim is "beats flat retrieval (`off`, B2) by ~15 points of recall@1 on
near-twins", not "beats SQL". The one family where SQL must write traversal code is multi-hop separation through
typed relations (L6-C, never run). Confidence: high that it fixes L5b; low that it beats SQL-with-the-same-columns.

### 2.5 Salience and emotional tagging (note 05)

Science. McGaugh: the amygdala modulates *consolidation*, so emotion makes memories last, not start stronger.
Synaptic tagging and capture (Redondo & Morris 2011; Moncada & Viola 2007): a weak trace within ~1 h of a strong
event is kept; Takeuchi 2016 locates the novelty signal in locus-coeruleus dopamine. Mather & Sutherland 2011:
arousal *biases competition*: it enhances high-priority and suppresses low-priority representations; it sharpens,
it does not boost everything. Flashbulb memories: salience raises confidence, not accuracy.

Plexus mapping. Graded `salience ∈ [0,1]` from consequence counts (unflagged decisions, confirmed verifications,
independently verified artifacts, completed downstream tasks, distinct using agents, handoffs, high-trust source,
pin), cached by the statements that create those edges. Salience modulates the **decay exponent**
(`d_eff = d·(1 − 0.4·s)`): one use 90 days ago sits at −7.93 for a plain fact and −4.76 for a fully salient one.
Tagging-and-capture: `record_decision`'s second statement walks the agent's `NEXT*0..20` steps within 1 h and
raises salience of facts used but not yet `BASED_ON`, with `captured_by` for the explanation. Arousal-biased
competition as the ranking rule: salience adds `+δ·s` only inside the relevance band and *subtracts* `δ·s_max`
outside it when a critical fact is in the band. `pin_fact` = salience 0.95. Salience never feeds `confidence`.

Off the SQL tie? **No, but it fixes the other displacer class.** Protected twins outranked targets because
protection was a boost; with the band guard it cannot be. The long-horizon payoff (critical facts still reachable
after a year) needs a 365-day L5b variant that does not exist. The capture rule needs a step-chain walk (a
recursive CTE in SQL: feasible). Confidence: high on the guard, medium on the long-horizon win, low on capture
mattering in current data.

### 2.6 Reconsolidation and updating (note 06)

Science. Nader 2000: a retrieved memory becomes labile for hours and must be re-stored. Sevenster 2013/2014,
Exton-McGuinness 2015, Sinclair & Barense 2019: **prediction error is required**: no PE → retrieval only; moderate
PE → update the old trace; large PE → a new trace. Gershman 2017: latent-cause inference decides update-vs-new,
which is exactly `assert_fact`'s supersede-vs-contradict decision.

Plexus mapping. `Fact.rel_a / rel_b` (Beta posterior, prior 2/1); outcomes that close the loop on a step that
`use`d the fact move them inside the outcome's own write statement: `fail_task` and flagged decisions → `rel_b += 1`
(PE); `verify_fact(confirmed)` and independent `verify_artifact` → `rel_a += 0.5` (no PE, mild); unflagged
decisions → nothing (retrieval without PE does not reconsolidate); 24 h window. Recall adds `ρ·ln(reliability/0.67)`.
`assert_fact` gains two latent-cause branches (an already-discredited or long-unused near variant is *updated*,
not left as a second live contradiction). `why_confidence(fact)` explains the posterior from provenance edges.

Off the SQL tie? **Yes on an injected benchmark, idle on current data.** Where a wrong twin was used by a decision
whose task failed, the posterior drops it below the right fact (≥ 90% of injected pairs vs a coin flip). A SQL arm
with the same counters ties on single-hop; multi-hop (`BASED_ON` → `DECIDED` → task) needs a CTE. Today's recordings
contain 0 task failures caused by a wrong fact, so the mechanism is correct and unexercised. Confidence: high on
the injected test, low that it matters before real multi-step runs produce failures.

## 3. Cross-cutting rules the notes agree on

1. **Activation adds; it never multiplies relevance.** A bounded additive term with a band is what ACT-R does and
   is what stops near-twin displacement. (01, 04, 05)
2. **Separate four axes and show all four:** relevance (query), activation (use history), salience (consequence),
   reliability (outcomes). None may feed `confidence`; none may rewrite history (`as_of`, `why`, `knew_at`,
   `fact_history` ignore all four). (01–06)
3. **Writes on read stay out of `recall`.** Counters and captures run at step boundaries or inside the outcome's
   own write statement, so `audit=off` tenants keep a read-only recall. (02, 05, 06)
4. **No silent negative edges.** Retrieval-induced forgetting, suppression and demotion are read-time signals or
   reversible status moves with a stored reason; never an unexplained edge. (02, 04)
5. **Fairness in benchmarks:** give the SQL arm every column it can compute with a join; claim a graph edge only
   where traversal is required (multi-hop relations, step chains, provenance walks), and report the arm's code
   budget as L6 did.

## 4. What this survey does not support

- A claim that biological forgetting *improves accuracy* in Plexus. The two cleanest ablations in the literature
  (MemTier, ZenBrain; forgetting-A Part 3) are neutral, and nothing found here changes that. What the science
  supports is that forgetting done the brain's way (additive, spaced, consequence-modulated, prediction-error
  gated) **stops costing accuracy** while it removes noise, and that pattern separation, which is not forgetting,
  is what raises recall@1.
- A claim that any of these beats a SQL arm that is handed the same features. The honest position, consistent
  with PLEXUS_REPORT §8: Plexus beats flat retrieval and tool-less readers, ties hand-written SQL on correctness,
  and wins on having the signals already in the graph, on one-query computation, and on explanation.

## 5. Sources

Each note lists the sources it opened; forgetting-A lists the 43 earlier ones. Key additions in this survey:
Wixted & Ebbesen 1991; Averell & Heathcote 2011; Benna & Fusi 2016; Pavlik & Anderson 2005; Mozer et al. 2009;
Anderson 2001 (ACT-R slides); Anderson & Reder 1999; Anderson 2003; Yassa & Stark 2011; Bakker et al. 2008;
Sahay et al. 2011; Kumaran, Hassabis & McClelland 2016; Girardeau et al. 2009; Tononi & Cirelli 2014; Schaul et al.
2016; Karpicke & Roediger 2008; Cepeda et al. 2008; FSRS algorithm wiki; Redondo & Morris 2011; Moncada & Viola
2007; Takeuchi et al. 2016; Mather & Sutherland 2011; Kirkpatrick et al. 2017; Nader, Schafe & LeDoux 2000;
Sevenster, Beckers & Kindt 2014; Exton-McGuinness, Lee & Reichelt 2015; Sinclair & Barense 2019; Gershman,
Monfils, Norman & Niv 2017.
