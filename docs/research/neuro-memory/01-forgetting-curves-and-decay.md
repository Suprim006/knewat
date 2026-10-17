# 01. Forgetting curves and decay: what shape, what timescales, and why the current multiplier failed

Research note for Plexus (branch `feature/neuro-memory-research`). Builds on `docs/research/forgetting-A-science-and-papers.md`
§1.1–1.3 (Ebbinghaus, ACT-R base-level equation) and does not repeat it. Citations `[n]` are in §6; `[unverified]` marks
claims from model memory that were not confirmed against an opened source. Numbers marked *computed here* come from
the formulas as stated, run in Python for this note.

## 1. Mechanism

### 1.1 The shape: power law, and why "power law" means "many timescales"

Wixted & Ebbesen (1991) fitted forgetting data from humans and pigeons and concluded that a power function fits
across procedures and species where the exponential does not [1]. Averell & Heathcote (2011) re-examined the question
with 28-day recognition data and hierarchical Bayesian model selection, and found the data consistent with **two
processes acting on different time scales**, which is "consistent with the multiple-scale nature of the power
function" [2]. The rational-analysis reading (Anderson & Schooler 1991, already in forgetting-A §1.1) is that the
curve mirrors the environment's need-probability, which itself decays as a power law.

The mechanistic account that produces a power law from biology is Benna & Fusi (2016): a chain of interacting
variables with increasingly slow dynamics inside each synapse yields memory traces that decay approximately as
`1/√t` while keeping capacity high; the paper's stated aim is to reconcile the plasticity–rigidity trade-off, and the
power-law tail is what makes old memories survive new ones [3]. The engineering lesson is the same as Averell &
Heathcote's: **a single exponential is wrong, and a single power term is an approximation of a sum of terms with
different timescales.**

### 1.2 ACT-R: base level, noise, threshold

ACT-R's base-level equation `B = ln Σ t_k^-d` (forgetting-A §1.3) is one component of `A = B + spreading activation
+ partial matching + noise`, and retrieval succeeds only when `A > τ` (retrieval threshold); the probability of
retrieval is logistic in `(A − τ)/s` where `s` is the noise scale [4, slides "Activation"; the logistic form is the
standard ACT-R statement and is also in forgetting-A §4.7, [unverified] for exact constants]. Two things in that
equation matter for Plexus and are absent from the current implementation:

- **Activation is additive across sources.** Base level (frequency × recency) *adds to* the context match. It does
  not multiply it.
- **There is a threshold and a noise scale**, so small activation differences between candidates are *not*
  decisive; they only shift probabilities by a logistic with slope `1/s`. Anderson's workshop notes derive the
  competitive-latency form `T = F·Σ_j e^{A_j} / e^{A_i}` and use `F ≈ 0.35` [4].

### 1.3 Activation-dependent decay (Pavlik & Anderson 2005)

Pavlik & Anderson fitted Japanese–English vocabulary data in which "the relative benefit of spacing increased with
increased practice and with longer retention intervals". Their model: each practice adds an increment that decays
as a power of time, and **"the rate of decay for each presentation depended on the activation at the time of the
presentation"**, which "limits long-term benefits from further practice at higher levels of activation and produces
the spacing effect" [5]. The decay of the i-th presentation is `d_i = c·e^{m_{i−1}} + a`, where `m_{i−1}` is the
activation just before that presentation; the fitted constants reported in the paper are `c ≈ 0.217`, `a ≈ 0.177`
[unverified: from memory of the paper; the opened abstract confirms the mechanism, not the constants. Check the full
text before coding].

Consequence: a read that happens while the fact is already highly active (a burst) gets a *fast-decaying* increment;
a read that happens when the fact has faded gets a *slow-decaying* one. Massed practice is self-limiting.

### 1.4 Mozer's multiscale context model (MCM)

MCM (Mozer, Pashler, Cepeda, Lindsey & Vul 2009) models an item as a set of leaky integrators at multiple time
scales; a study boosts integrator *i* by an amount that depends on how close the first *i* integrators already are
to full strength, and the model's four parameters "are fully determined by the forgetting function". It blindly
predicted seven different spacing functions [6]. It is another multi-timescale account, and it shares with
Pavlik–Anderson the self-limiting increment.

### 1.5 What is settled and what is not

Settled enough to build on: power-law-shaped retention; frequency and recency both matter; increments are
self-limiting when the trace is already strong; exponential decay with one constant is the wrong model.
Contested: whether "decay" is a cause or a description (Wixted's interference account, forgetting-A §1.4), and the
exact constants, which are fitted per material. For an index this is fine: decay is a ranking prior, not a claim
about truth (forgetting-A §4.1).

## 2. Why it matters for recall QUALITY

Plexus's recall decides the order of `k` rows. The current rule is `final = relevance × m(A)` with
`m(A) = floor + (1 − floor)·σ(A − A0)`, floor 0.9. *Computed here* with `A0 = −5.68`:

| Activation A | history (ACT-R d = 0.5) | m(A), floor 0.9 | m(A), floor 0.5 |
|---|---|---|---|
| −7.93 | created once, 90 d ago (a cold target) | 0.910 | 0.549 |
| −5.68 | one event 1 d ago (neutral) | 0.950 | 0.750 |
| −4.81 | five uses at 1, 3, 7, 14, 30 d | 0.971 | 0.853 |
| −2.82 | read daily for 90 d (a hot twin) | 0.996 | 0.995 |

So at floor 0.9 the multiplier ranges over about **9%** between a cold target and a hot twin. The L5b twins share
near-identical text, so their cosine-relevance gap is a few thousandths to about 0.02. A hot twin with relevance
0.70 scores `0.70 × 0.996 = 0.697`; the cold target with relevance 0.72 scores `0.72 × 0.910 = 0.655`. **The twin
wins whenever the relevance gap is under roughly 0.06**, which is nearly always for paraphrases. That is the whole
L5b failure in one line: a multiplicative range of ~0.09 is larger than the relevance differences the ranking is
supposed to respect. At floor 0.5 the range was 0.45, which is why recall@5 collapsed to 73%.

Two independent design errors are visible:

1. **Multiplicative blending with a range wider than the signal it modulates.** ACT-R adds; it does not multiply.
2. **A single power term with d = 0.5 rewards massed reading.** 90 daily reads produce A = −2.82; a burst of 90
   reads inside one hour 45 days ago still gives −3.09 (*computed here*). Being *shown* often is enough to
   dominate, which is exactly the rich-get-richer loop forgetting-A §4.2 warned about.

The science says what to do about each: make activation additive with a threshold and a noise scale (so it breaks
ties rather than overriding relevance), and make each increment's decay depend on the activation at the time of the
event (so bursts saturate).

## 3. Design for Plexus

### 3.1 Scoring: additive, banded, thresholded

```
rel     = 1 − cosine_distance_after_sibling_boost          # as today, in [0, 1]
B       = base_level_activation(events)                    # §3.2, in nats
A       = B + S_ctx                                        # S_ctx: fan/context term, see note 04 (0 if disabled)
z       = (A − A0) / s                                     # s = 1.0 nat by default (ACT-R noise scale, [unverified] default)
score   = ln(max(rel, 1e−6)) + beta · tanh(z / 2)          # beta = 0.05 by default
```

`ln(rel)` keeps the relevance ordering; `tanh(z/2)` is bounded in (−1, 1), so the activation term can move a score
by at most `±beta` in log-relevance, i.e. by a *relative* relevance change of about `e^{±0.05} = ±5%`. Set `beta`
from the benchmark: the goal is `beta` ≈ the median relevance gap between a true target and its best non-target
competitor (L5b can measure this directly: it is the gap between rank 1 and rank 2 in the `off` mode). Activation
then decides ties and near-ties and nothing else. Protection keeps `max(A, A0)`. The exact-keyword bypass stays.

Retrieval threshold: rows with `A < τ` (default `τ = A0 − 3`, about 60 days unused, matching the sweep threshold)
are kept but flagged `faint: true` in the result, which lets an agent (or the viewer) see "this came back on
relevance alone". Nothing is hidden.

### 3.2 Base level with activation-dependent decay (Pavlik–Anderson)

```
events sorted ascending by t (newest K = 50 kept, as today)
for i, (t_i, w_i) in enumerate(events):
    m_prev = ln( Σ_{j<i} w_j · (t_i − t_j + 60 s)^(−d_j) )     # activation just before event i; −inf for the first
    d_i    = min(d_max, c · exp(m_prev) + a)                  # c = 0.217, a = 0.177 [unverified constants], d_max = 1.0
B(now) = ln( Σ_i w_i · (now − t_i + 60 s)^(−d_i) + surprise_bonus )
```

*Computed here*, 90-day horizon (absolute values are not comparable across the two models; compare the ordering):

| history | ACT-R, d = 0.5 | activation-dependent d |
|---|---|---|
| created once 90 d ago | −7.93 | −2.81 |
| created + 1 use, 90 d ago (L5b critical probe) | −7.24 | −2.63 |
| read daily × 90, last 1 d ago (hot twin) | −2.82 | −0.17 |
| burst: 90 reads in one hour, 45 d ago | −3.09 | **−2.14** |
| 5 spaced uses at 1, 3, 7, 14, 30 d | −4.81 | −1.11 |
| 1 use 1 d ago | −5.68 | −2.01 |

The burst case is the point: under d = 0.5 a one-hour burst is worth nearly as much as 90 spaced days; under
activation-dependent decay it is worth about as much as a single use. Spaced use still wins clearly. This is the
"decay" half of the fix for twins that were read daily (the "testing effect" half, which events count and how much, is
in note 03).

Cost: `O(K²)` per fact with K = 50 → 1,250 operations per candidate, 2k candidates per recall; negligible in Python.
No schema change; the event list is what `activation/activation.cypher` already returns.

### 3.3 Two-timescale variant (optional, Benna–Fusi-inspired)

If the K = 50 cap is ever too small for very hot facts, keep two per-fact accumulators instead of the event list:
`fast` (half-life 1 day) and `slow` (half-life 30 days), updated on each event in the same statement that writes the
`READ`/`VERIFIED_BY` edge (`SET f.act_fast = f.act_fast · exp(−Δt/τ_f) + w, f.act_slow = …`), and
`B = ln(act_fast + act_slow)`. This is the "count-based approximation" of forgetting-A §1.3 with two scales. It
changes nothing on reads and adds one `SET` on writes. Not needed for the benchmark; listed as the scaling path.

### 3.4 Integration

- `memory_strength` explains `B`, `S_ctx`, `z`, `beta·tanh(z/2)` and `faint`. The per-event `d_i` is shown so a user
  can see "these 40 reads were a burst and count for little".
- `memory_sweep` keeps its threshold on `B` (now `A0 − 2` under the new `B`; recalibrate the constant by the same
  rule, "a fact nobody used for about 60 days").
- `verify_after`, `pin_fact`, `set_review_date`: unchanged.
- Settings: `PLEXUS_ACT_MODE = mult | add` (default `add` after the benchmark passes), `PLEXUS_ACT_BETA`,
  `PLEXUS_ACT_S`, `PLEXUS_ACT_C`, `PLEXUS_ACT_A`; `PLEXUS_FORGETTING=off` still reproduces the plain order exactly.

## 4. Benchmark plan

Harness: Crucible L5b unchanged (K = 20 sprints, N = 5 noise, 90 simulated days, seed 20261016), plus the N = 15
stress run. Modes: `off`, `on-mult` (today's rule, floor 0.9), `on-add` (§3.1 + §3.2). New measurement: the
relevance gap between rank 1 and rank 2 in `off` per probe (so `beta` is set from data and reported).

Pre-registered hypotheses:
1. `on-add` recall@1 ≥ `off` recall@1 − 0.01 (today `on-mult` is 12 points below). Falsified if more than 1 point below.
2. `on-add` recall@5 ≥ `off` − 0.005; critical loss 0.
3. Noise share of `on-add` ≤ `off` − 0.03 (we accept a smaller noise reduction than `on-mult`'s 9 points; the point
   of this note is to stop paying recall for it).
4. The burst variant: add a fourth read schedule, "hot-burst" (same 90 reads of a hot twin, but within one hour),
   and predict that `on-add` ranks burst twins below spaced twins while `on-mult` does not.

SQL fairness: there is no SQL arm in L5b. The honest comparator is `off` (= flat vector + keyword retrieval, which is
what B2 and a SQL arm with the same embeddings would do). A SQL arm given the same event timestamps can compute the
same `B`; this note makes no claim that SQL could not.

Biggest risk of a tie: hypothesis 1 is "no harm", not "a win". Decay alone cannot beat `off` on recall@1 for
near-twins, because the discriminating information (which sprint) is not in the activation at all. The win has to
come from note 04 (pattern separation); this note's job is to stop the loss.

## 5. Confidence

- That `on-add` removes the recall@1 loss: **high** (it follows from the arithmetic in §2; `beta` bounds the damage).
- That activation-dependent decay ranks burst twins below spaced twins: **high** (the model does this by
  construction; the table shows it).
- That any of this *beats* `off` on recall: **low**. Decay is a prior over need-probability; on a benchmark where
  every probe names its target, a prior cannot beat a correct likelihood. Expect "no loss, less noise".

## 6. Sources (opened)

[1] Wixted & Ebbesen (1991) On the form of forgetting. Psychological Science. https://journals.sagepub.com/doi/10.1111/j.1467-9280.1991.tb00175.x (abstract and reference list)
[2] Averell & Heathcote (2011) The form of the forgetting curve and the fate of memories. J. Math. Psychol. https://www.ampl-psych.com/wp-content/uploads/2021/05/Averell-and-Heathcote-2011-The-form-of-the-forgetting-curve-and-the-fate-of-m.pdf
[3] Benna & Fusi (2016) Computational principles of synaptic memory consolidation. Nature Neuroscience. https://pubmed.ncbi.nlm.nih.gov/27694992 ; preprint https://arxiv.org/abs/1507.07580v1
[4] Anderson (2001) Comments on activation, latency and the fan effect. ACT-R Summer School slides. http://act-r.psy.cmu.edu/wordpress/wp-content/themes/ACT-R/workshops/2001/talks/JRAactivation.pdf
[5] Pavlik & Anderson (2005) Practice and forgetting effects on vocabulary memory: an activation-based model of the spacing effect. Cognitive Science 29(4). https://pubmed.ncbi.nlm.nih.gov/21702785 ; https://digitalcommons.memphis.edu/facpubs/8387/
[6] Mozer, Pashler, Cepeda, Lindsey & Vul (2009) Predicting the optimal spacing of study: a multiscale context model of memory. NeurIPS 2009. https://proceedings.neurips.cc/paper/2009/file/6bc24fc1ab650b25b4114e93a98f1eba-Paper.pdf
