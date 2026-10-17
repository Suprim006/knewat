# 03. Spacing and testing effects: which graph events are "retrieval practice"

Research note for Plexus. Builds on forgetting-A §1.2 (no repeat). `[unverified]` = not confirmed against an opened source.

## 1. Mechanism

### 1.1 Retrieval is a learning event, restudy mostly is not

Karpicke & Roediger (2008, Science): after a word pair could be recalled once, conditions that kept *testing* it
produced about **80%** recall a week later, while conditions that dropped it from testing (but kept restudying it)
produced **36% and 33%**; "repeated study after one successful recall did not produce any measurable learning a
week later" [1]. Students' own predictions did not track this. So: being *re-exposed* adds almost nothing; being
*retrieved* adds a lot.

### 1.2 Spacing: the optimal gap scales sub-linearly with the retention interval

Cepeda et al. (2008), 1,350 participants, gaps up to 3.5 months, retention intervals (RI) up to a year: "the optimal
gap increased as test delay increased. However, when measured as a proportion of test delay, the optimal gap
declined from about 20 to 40% of a 1-week test delay to about 5 to 10% of a 1-year test delay." For RIs of 7, 35,
70 and 350 days the optimal gaps were 1, 11, 21 and 21 days (recall). The optimal gap "provided a 64% increase in
final recall, d = 1.1" over the zero-day gap [2].

### 1.3 The two-strength theory and desirable difficulty

Bjork & Bjork's new theory of disuse (forgetting-A §1.4) separates *storage strength* (how well learned) from
*retrieval strength* (current accessibility), and adds the rule that **the increment to storage strength from a
retrieval is larger when retrieval strength is low** at the time [3, as summarised in the Bjork lab's own later
papers; the 1992 chapter itself was not opened]. This is the same statement as Pavlik–Anderson's
activation-dependent decay (note 01 §1.3) in different words: an event that happens when the trace is already
strong buys little.

### 1.4 Spaced-repetition schedulers: FSRS as the engineering form

FSRS models each item by Difficulty, Stability (the interval at which retrievability is 90%) and Retrievability
`R(t, S) = (1 + factor·t/S)^(−w20)` with `factor = 0.9^(−1/w20) − 1` so that `R(S, S) = 0.9`; the stability update after
a successful review multiplies `S` by a factor that *decreases* with `S` (`S^(−w9)`) and *increases* with
`(1 − R)` (the harder the retrieval, the bigger the gain); FSRS-6 has 21 fitted parameters [4]. Three rules worth
copying: (a) a per-item stability that is updated incrementally, so scoring needs no event scan; (b) the gain
shrinks as stability grows; (c) the gain grows as retrievability at the time of the event shrinks (desirable
difficulty). The fitted parameter values are for human flashcard review and are *not* transferable; the functional
form is.

## 2. Why it matters for recall QUALITY

The L5b hot twins were read "3–8 of them on each of the 90 days", half via `use`, half via `recall`. That is
massed restudy of the same twin, and under the current model it is rewarded linearly in count (each read is an
independent `t^−0.5` term). Karpicke–Roediger say restudy should count almost nothing after the first success;
Pavlik–Anderson and FSRS say each further event should count less as the trace gets stronger. Both would cap the hot
twin's advantage, which is one of the two displacers in the post-hoc diagnostic (hot 7–12 of the displacements;
critical/protected twins were the larger share, note 05).

Recall quality also depends on *which* events count. Today:

| graph event | counts as | weight |
|---|---|---|
| `READ via:'recall'` (shown) | restudy | 0.3 |
| `READ via:'use'` (a decision, handoff or assert consumed it) | retrieval practice | 1.0 |
| `VERIFIED_BY` (agent re-checked it against the code) | retrieval test, passed | 2.0 |
| re-`ASSERTED_BY` | restudy by another agent | 1.0 |
| `memory_strength`, `who_knew`, `as_of`, `fact_history` | nothing | 0 |

The weights are in the right order. The missing piece is the *diminishing return*: ninety `use` reads of the same
fact at high activation should not be worth ninety.

## 3. Design for Plexus

### 3.1 Spacing-aware increments (the core change)

Use Pavlik–Anderson's rule in the Python model (note 01 §3.2): the decay of event *i* is
`d_i = min(1, c·exp(m_{i−1}) + a)` where `m_{i−1}` is the activation just before event *i*. No schema change.
Worked table (*computed here*, from note 01): daily × 90 → −0.17; the same 90 reads in one hour → −2.14; 5 spaced
uses → −1.11; one use → −2.01. Massed reads collapse toward a single use; spaced uses keep their advantage.

Add the testing-effect asymmetry on top: a `recall` READ **after** the fact's last `use` is a restudy and gets
`w = 0.3 · (1 − R_est)` where `R_est = σ(m_{i−1} − A0)` is the estimated retrievability at that moment (an easy
re-exposure is worth ~0; a re-exposure of a faded fact is worth up to 0.3). `use` and `VERIFIED_BY` keep full weight
(they are retrievals with a consequence).

### 3.2 Which calls count

- `verify_fact(confirmed)` = a passed retrieval test: weight 2 (as today) **and** it resets `verify_after` by the
  schedule in §3.3. `verify_fact(changed)` is a failed test on the *old* fact (it is superseded; nothing to update)
  and a creation event for the new one.
- `who_knew`, `as_of`, `fact_history`, `memory_strength`, `why_recalled`: still **not** events. They are audits of
  history and must not change it (forgetting-A §4.1). This is a deliberate asymmetry with the human case, where
  any retrieval strengthens; a database can afford the cleaner rule.
- `verify_artifact(independent=true)` on an artifact of a task whose decision is `BASED_ON` the fact: a passed test
  two hops away; weight 1, found by the same traversal note 05 uses for salience.

### 3.3 Incremental stability and automatic review dates

Option A (compute on the fly, as today): fine up to K = 50 events; `O(K²)` with the spacing rule.

Option B (FSRS-style, incremental): two properties on `Fact`, `stab` (seconds) and `stab_at` (ms), updated inside
the same statement that writes the `READ`/`VERIFIED_BY` edge:

```
// inside the write statement, after MATCH (f:Fact {id:$id})
WITH f, coalesce(f.stab, 86400.0) AS S, coalesce(f.stab_at, f.created_at) AS t0
WITH f, S, ($now - t0) / 1000.0 AS dt
WITH f, S, pow(1.0 + 0.2345 * dt / S, -0.5) AS R            // FSRS-4.5 curve: factor 19/81, decay −0.5
SET f.stab    = S * (1.0 + $gain * pow(S / 86400.0, -0.2) * (exp(1.0 - R) - 1.0)),
    f.stab_at = $now
```
`$gain` = 2.0 for `use`/`verify`, 0.3 for `recall` (constants to be fitted on the L5b read schedule, not taken from
FSRS, whose constants are for human flashcards). `R` at recall time is then `pow(1 + 0.2345·dt/S, −0.5)` from two
properties, no event scan. The ranking uses `A = ln(R)`-style terms or feeds `R` straight into note 01's additive
score as `z`. Option B is the scaling path; Option A is enough for the benchmark and keeps the audit trail
explainable event by event.

Automatic review: `set_review_date` today is manual. With `stab`, schedule `verify_after = stab_at + stab · I(r)`
where `I(r) = (r^(−2) − 1) / 0.2345` for target retrievability `r` (FSRS-4.5 inversion) — but **only** for facts
that are decision-critical (`BASED_ON` by an unflagged decision) or anchored to code: those are the facts whose
being wrong costs something. Default `r = 0.9`. Cepeda's ridgeline says the review gap should be 5–20% of the
horizon you care about; for a fact that must stay right for a year, that is a review every 2–10 weeks, which is
what `r = 0.9` on a stability of a few weeks produces. A passed `verify_fact(confirmed)` grows `stab` and pushes the
next review out; a `changed` outcome starts the new fact at the default stability.

### 3.4 Integration

- `memory_strength` reports `R_est` at each event, the effective `d_i`, and the next `verify_after` with its
  reason (`scheduled by stability` vs `set by agent`).
- `memory_sweep` / `consolidate` thresholds work on the same activation.
- `facts_to_verify` already lists facts whose `verify_after` has passed; no change.
- Cost: Option A, none on write; Option B, one `SET` inside existing write statements (no extra statement).

## 4. Benchmark plan

L5b with an added read schedule variable: for the hot set, `massed` (today: daily for 90 days) vs `burst` (the
same count inside one hour at day 45) vs `spaced` (10 reads at FSRS-like growing gaps). Modes `off`, `on-mult`,
`on-spaced` (note 01 additive score + this note's increments). Pre-registered: (1) under `on-spaced`, hot-burst
twins outrank cold targets in ≤ 1% of probes (under `on-mult` they do so whenever the relevance gap < 0.06);
(2) recall@1 of `on-spaced` ≥ `off` − 0.01; (3) the automatic `verify_after` schedule flags every critical fact at
least once in 90 simulated days and no cold non-critical fact.

Also a staleness-style test for the scheduler: L5a's repo with 21 commits; the question is whether stability-based
review catches the 19 stale (commit, fact) pairs *without* anchors (today the no-anchor arm catches 0 of 19). Prediction:
a few, not all — review on a schedule is a floor, anchors are the real mechanism.

Fairness: a SQL arm with the same event table can compute the same thing. No claim otherwise.

Biggest risk: L5b's "hot" set is 9 facts; the effect on recall@1 will be small and noisy. The burst variant is
needed to show the mechanism at all.

## 5. Confidence

- That spacing-aware increments remove the massed-read advantage: **high** (by construction, table in note 01).
- That the automatic review schedule is useful: **medium**; it replaces a manual date with a defensible default
  and nothing more.
- That this beats `off` on recall@1: **low**; same reason as note 01.

## 6. Sources (opened)

[1] Karpicke & Roediger (2008) The critical importance of retrieval for learning. Science 319. https://pubmed.ncbi.nlm.nih.gov/18276894/ ; PDF https://learninglab.psych.purdue.edu/downloads/2008/2008_Karpicke_Roediger_Science.pdf
[2] Cepeda, Vul, Rohrer, Wixted & Pashler (2008) Spacing effects in learning: a temporal ridgeline of optimal retention. Psychological Science. https://laplab.ucsd.edu/articles/Cepeda%20et%20al%202008_psychsci.pdf
[3] Bjork & Bjork (2011) Making things hard on yourself, but in a good way: creating desirable difficulties. https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/04/EBjork_RBjork_2011.pdf (listing; 1992 chapter in forgetting-A [30])
[4] FSRS: The Algorithm (open-spaced-repetition wiki, FSRS v4 → FSRS-6). https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm/5bf70e459e45152d40988c670fa7c4625b5e8577
[5] Pavlik & Anderson (2005), as in note 01 [5].
