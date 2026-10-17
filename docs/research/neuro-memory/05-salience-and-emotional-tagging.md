# 05. Salience and emotional tagging: graded salience that slows decay, with a band guard

Research note for Plexus. Builds on forgetting-A §1.5 (no repeat). `[unverified]` = not confirmed against an opened source.

## 1. Mechanism

### 1.1 Modulation of consolidation, not of encoding

McGaugh's line of work (forgetting-A [27]) places the amygdala's effect on *consolidation*: stress hormones and
noradrenaline acting on the basolateral amygdala make a memory *last*, with an inverted-U dose response
[unverified for the inverted-U detail; the 2004 review is cited in forgetting-A]. The engineering reading: salience
should change how fast a trace *fades*, not how strong it starts.

### 1.2 Synaptic tagging and capture (STC)

Redondo & Morris (2011): "the fate of a memory is not determined at the time of encoding"; a weak induction creates
a synapse-specific *tag* but not a lasting change, and "weak encoding protocols achieve long-term memory if
plasticity-related products are made available by an unrelated event before or after encoding" [1]. The
behavioural form (Moncada & Viola 2007; "behavioural tagging") shows a weak memory becomes long-lasting if a
novel experience happens within about an hour [2, abstract listing]. So a *retroactive* window exists: an
unremarkable fact that is followed closely by a salient event is kept.

### 1.3 Novelty gating via locus coeruleus dopamine

Takeuchi et al. (2016, Nature): "the retention of episodic-like memory is enhanced … when something novel happens
shortly before or after encoding"; the effect is mediated by locus coeruleus neurons projecting to the hippocampus
and acting on D1/D5 receptors, and optogenetic activation of those neurons mimics the novelty effect [3]. This is
the circuit behind behavioural tagging, and it confirms the window is around encoding on both sides.

### 1.4 Arousal-biased competition: sharpen, do not boost

Mather & Sutherland (2011): "the battle is for a share of our limited attention and memory, with the brain
selecting the winners and discarding the losers … arousal during an event increases this bias both in perception
and in long-term memory": arousal *enhances* high-priority representations and *impairs* low-priority ones [4].
This is the key design constraint: a salience signal must not lift everything; it must widen the gap between the
top and the rest.

### 1.5 ML analogues

EWC (Kirkpatrick et al. 2017) protects parameters in proportion to their Fisher information, an *importance*
estimated from how much the loss depends on them [5]; prioritized replay samples by TD error [note 02, [4]]. Both
derive importance from *consequence*, not from content. Generative Agents' LLM-rated importance (forgetting-A §2.1)
is content-based and unavailable to Plexus by design (no LLM inside).

## 2. Why it matters for recall QUALITY

Plexus has a boolean `protected` (pinned, `BASED_ON`, `CARRIES`, supersede chain, high-trust source) that stops
sweeping and floors the multiplier at `A0`. L5b's post-hoc diagnostic: the main displacers were *protected*
(critical) twins: 367 displacements at floor 0.5, 82 at 0.9. Protection raised a popular twin's rank against the
right fact. That is salience used as a *boost on everyone protected*, the opposite of arousal-biased competition.

What the science prescribes instead:
- importance should slow *decay* (so a critical fact stays reachable for months) but not add rank *now* against a
  more relevant fact;
- importance should be graded and derived from consequence (decisions, verified artifacts, completed tasks, use by
  several agents), so that "the planner cited it once" and "three agents verified it and two tasks shipped on it"
  are different numbers;
- within one result list, salience should sharpen (widen the top-vs-rest gap) only when it coincides with
  relevance, never lift a less relevant row over a more relevant one.

## 3. Design for Plexus

### 3.1 Graded salience from graph structure (no LLM)

```
s(f) = 1 − exp(−( 1.0·n_decisions_unflagged
                 + 1.5·n_verified_confirmed
                 + 1.0·n_artifacts_verified_independent      // via Decision→Task→Artifact VERIFIED_BY {independent:true}
                 + 0.5·n_tasks_done_downstream                // Decision→(task) with status done
                 + 0.5·(n_distinct_use_agents − 1)
                 + 0.5·n_handoffs
                 + 1.0·[derived from Source.trust='high']
                 + 3.0·[pinned] ))                            // pin = strong salience, s ≈ 0.95 alone
```
All counts come from one bounded read extending `activation/activation.cypher` with two more comprehensions
(`(:Decision)-[:BASED_ON]->(f)` already exists; add `(d)-[:DECIDED]->(:Task)` hops bounded to 20 decisions and
`(a:Artifact)-[:FOR]->(t)-[...]` bounded to 20 artifacts). `s` is cached as `Fact.salience` and `Fact.salience_at`
by the same statements that create those edges (`record_decision`, `verify_fact`, `verify_artifact`,
`complete_task`, `handoff`, `pin_fact`), each doing one `SET` on ≤ 200 facts in the statement it already runs.
`pin_fact` becomes `SET f.pinned = true, f.salience = max(f.salience, 0.95)`; protection thresholds are
`s ≥ 0.5` for "never swept" and `s ≥ 0.8` for "use `max(A, A0)`". Boolean rules remain as the floor for data from
before the change.

### 3.2 Salience modulates decay (McGaugh), not strength

In the activation model: `d_eff(f) = d · (1 − κ·s(f))`, `κ = 0.4`. A fact with `s = 1` decays with exponent 0.3
instead of 0.5. *Computed here*: one use 90 days ago gives `B = −7.93` at d = 0.5 and `−4.76` at d = 0.3; at
30 days `−7.38` vs `−4.43`. The salient fact stays near neutral for months; the plain fact fades. Combined with the
additive band (note 01), this changes *which faded facts are still tie-breakable*, not the order among relevant
ones.

### 3.3 Tagging and capture (retroactive)

When a strong event is written (a decision, a `verify_artifact(independent=true)`, a `complete_task` on a task
with a decision), the same statement looks back along the agent's step chain for facts `READ via:'use'` within
`W = 1 h` that are not yet `BASED_ON` and raises their salience by `+0.2` (capped at 0.6 by capture alone):

```
MATCH (d:Decision {id:$id})<-[:WROTE]-(s0:Step)
MATCH p = (s0)<-[:NEXT*0..20]-(s:Step)            // bounded: 20 steps back
WHERE s.at >= s0.at - 3600000
WITH DISTINCT s
MATCH (s)-[:READ {via:'use'}]->(f:Fact)
WHERE NOT (:Decision)-[:BASED_ON]->(f)
WITH f LIMIT 50
SET f.salience = CASE WHEN coalesce(f.salience,0) + 0.2 > 0.6 THEN 0.6 ELSE coalesce(f.salience,0) + 0.2 END,
    f.salience_at = $now,
    f.captured_by = $id
```
(6.0.2: a node created earlier in the same statement cannot be `MATCH`ed, so this runs as the second statement of
`record_decision`, after the decision exists; it is bounded and idempotent.) `captured_by` gives `memory_strength`
its explanation: "salience 0.4: captured by decision D-17 within 12 min of use".

### 3.4 Arousal-biased competition as a ranking rule

Within one recall result, with `s_max` the highest salience among the top-`k` by relevance:
```
sharpen(f) = +δ·s(f)      if rel(f) ≥ rel_top − ε       (ε = 0.02, inside the band)
           = −δ·s_max     otherwise, only when s_max ≥ 0.8  (a critical fact is in the band: suppress the tail)
δ = 0.03 (log-relevance)
```
Salience never lifts a row across the band edge; it widens the gap between the band and the tail when the band
contains something important. That is Mather–Sutherland's rule literally, and it is the guard against repeating
L5b: a protected twin outside the band gets `−δ`, not `+`.

### 3.5 The honesty rule

`salience` is stored and shown separately from `confidence` and from `surprise`; it never feeds `confidence`
(flashbulb memories: salience raises perceived accuracy, not accuracy, forgetting-A [18][19]). `memory_strength`
prints all three with one line each.

### 3.6 Integration

- `memory_sweep` / `consolidate`: protection from `s`; the boolean rules stay as the floor.
- `pin_fact`/`unpin_fact`: set/clear `pinned` and adjust `salience` (unpin recomputes from counts).
- `verify_after`: a salient fact (`s ≥ 0.5`) gets the automatic review schedule from note 03; a plain fact does not.
- Cost: one `SET` inside existing write statements; the activation read gains two comprehensions; recall gains
  nothing (salience is a property).

## 4. Benchmark plan

L5b, modes `off`, `on-mult`, `sal` (notes 01 + 04 + this note's §3.2 and §3.4). Pre-registered: (1) critical loss 0
with the *boolean* protection floor removed (salience alone must protect); (2) critical@5 after a sweep ≥ 97.5%
(today) and critical@5 at a simulated **365 days** ≥ 95% (today, at d = 0.5 with one use a year ago, a critical fact
sits at the floor of the band and is lost to any neighbour; with `d_eff = 0.3` it is not: this is the test that
distinguishes "slower decay" from "a boost"); (3) rows ranked above the target that are `critical` from another
sprint: ≤ 5 (today 82); (4) capture: in the L5b read schedule, mark the facts used within 1 h before each recorded
decision; the capture rule must raise exactly those and no others (precision 1.0, a correctness test).

SQL fairness: the counts are joins; a SQL arm can compute `s`. Tie on the rule, expected. The capture rule needs the
step chain walk (`NEXT*0..20`), which is a recursive CTE in SQL: feasible, more code.

Biggest risk: L5b has no outcomes beyond decisions (no `verify_artifact`, no `complete_task` in the read schedule),
so `s` degenerates to the old boolean. The benchmark needs the L3 recording or a synthetic outcome schedule to
exercise the graded part.

## 5. Confidence

- That graded salience + decay modulation + the band guard removes the protected-twin displacement: **high**
  (the band guard alone does it; note 01's arithmetic).
- That slower decay for salient facts shows up as a measurable win: **medium**, and only on a long-horizon
  variant (365 days) that does not exist yet.
- That tagging-and-capture improves anything measurable: **low** on current benchmarks; it is a provenance-driven
  importance estimate that needs real multi-step runs to matter.

## 6. Sources (opened)

[1] Redondo & Morris (2011) Making memories last: the synaptic tagging and capture hypothesis. Nat. Rev. Neurosci. https://www.nature.com/articles/nrn2963
[2] Moncada & Viola (2007) Induction of long-term memory by exposure to novelty requires protein synthesis: evidence for a behavioral tagging. J. Neurosci. 27(28). https://bibliotecadigital.exactas.uba.ar/collection/paper/document/paper_02706474_v27_n28_p7476_Moncada (listing); review: https://pmc.ncbi.nlm.nih.gov/articles/PMC6673289
[3] Takeuchi et al. (2016) Locus coeruleus and dopaminergic consolidation of everyday memory. Nature 537. https://pmc.ncbi.nlm.nih.gov/articles/PMC5161591
[4] Mather & Sutherland (2011) Arousal-biased competition in perception and memory. Perspect. Psychol. Sci. https://pmc.ncbi.nlm.nih.gov/articles/PMC3110019
[5] Kirkpatrick et al. (2017) Overcoming catastrophic forgetting in neural networks. PNAS. https://www.pnas.org/doi/10.1073/pnas.1611835114
