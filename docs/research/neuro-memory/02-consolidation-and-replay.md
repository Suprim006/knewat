# 02. Consolidation and replay: a consolidation pass instead of a scheduled sweep

Research note for Plexus. Builds on forgetting-A (no repeat). `[unverified]` = not confirmed against an opened source.

## 1. Mechanism

### 1.1 Two systems, interleaved

Complementary Learning Systems (McClelland, McNaughton & O'Reilly 1995; updated by Kumaran, Hassabis & McClelland
2016): a fast hippocampal system stores specific experiences; a slow neocortical system "gradually acquires
structured knowledge representations" through **interleaved** replay of those experiences. The 2016 update adds
that replay "allows goal-dependent weighting of experience statistics" and "can be modulated by reward or novelty,
which acts to rebalance the general statistics of the environment towards the goals of the agent" [1]. Catastrophic
interference (McCloskey & Cohen 1989) is what happens to the slow system without interleaving [1, refs].

### 1.2 Replay is causal and biased

Girardeau et al. (2009) selectively eliminated hippocampal sharp-wave ripples during post-training rest and
impaired spatial memory in rats: "evidence for a prominent role of hippocampal SPW-Rs in memory consolidation" [2].
Post-learning hippocampal–striatal replay is biased by reward-prediction signals, and replay is found in VTA
reward cells, "confirming the involvement of the full hippocampal-striatal-VTA loop in post-task reactivation" [3].
In machine learning the same idea is prioritized experience replay: sample transitions in proportion to their
TD error rather than uniformly; DQN with it beat uniform replay on 41 of 49 Atari games [4].

### 1.3 Sleep renormalises: the synaptic homeostasis hypothesis

Tononi & Cirelli (2014): waking learning "requires strengthening connections throughout the brain. This increases
cellular needs for energy and supplies, **decreases signal-to-noise ratios**, and saturates learning. During sleep,
spontaneous activity renormalizes net synaptic strength", and "activity-dependent down-selection of synapses can
also explain the benefits of sleep on memory acquisition, consolidation, and integration" [5]. The claim that matters
here is explicit: forgetting (down-selection) exists to *restore signal-to-noise*, and it is selective: strongly and
consistently activated synapses survive the global scaling, weak and inconsistent ones do not.

### 1.4 Trace transformation

Winocur & Moscovitch's trace-transformation view (and the multiple-trace theory it comes from) holds that a
consolidated memory is not the episode moved elsewhere but a *schematic, gist-like* version in cortex that
coexists with the detailed hippocampal trace [unverified: from memory; not opened for this note]. The engineering
analogue: consolidation produces a *gist* node that stands for a cluster of near-identical episodes, and the
episodes remain.

## 2. Why it matters for recall QUALITY

Three retrieval errors map onto these mechanisms:

- **Near-twin competition (L5b).** Twenty sprint-specific facts with the same gist compete at recall. The brain's
  answer is not to rank twins by popularity; it is to consolidate them into one gist ("API version is v2 in every
  sprint since S07") plus the per-episode differences. Recall then returns the gist once, and the specific twin only
  when the query names the episode. Today Plexus returns five twins and the agent reads five.
- **Shown-often ≠ used.** Without renormalisation every `READ via:'recall'` adds strength (weight 0.3 today). SHY
  says: periodically scale everything down and let only *consistently used* traces stay above threshold. That is a
  precise prescription against the rich-get-richer loop.
- **A sweep on a clock vs replay on evidence.** `memory_sweep` demotes by a threshold on activation. Replay-driven
  consolidation demotes what was *never replayed with a payoff*: facts that were returned by recalls whose step
  went on to use a *different* fact (the recall was a miss for them). That is prioritized replay inverted: TD error
  = "was returned, was not used".

## 3. Design for Plexus

### 3.1 Schema

- `Fact.tier ∈ {'episodic', 'consolidated'}` (default `'episodic'`; absent = episodic).
- `Fact.consolidated_at: int` (ms) when promoted.
- New node `Gist {id, scope_id, predicate, value_norm, embedding, created_at, n_members}` and edge
  `(Fact)-[:INSTANCE_OF {at}]->(Gist)`. A gist is created only from facts that are already `DUPLICATES` /
  `DUPLICATES_MAYBE`-confirmed or whose normalised value is identical (the P9 dedup machinery decides equality; the
  consolidation pass never invents equality).
- `Fact.returned_unused: int` and `Fact.returned_used: int` counters (maintained by the step-close path, §3.3).

### 3.2 `consolidate(scope, dry_run=true, limit=200)` — one tool, three bounded statements

**Statement 1 (promote, `rw`).** Among the oldest ≤ 5,000 active facts of the scope, promote to `consolidated` the
facts with evidence of *interleaved* use: ≥ 2 distinct agents in `READ via:'use'` or `ASSERTED_BY`, OR an unflagged
`BASED_ON`, OR a `VERIFIED_BY {outcome:'confirmed'}`, AND the last two uses more than 24 h apart (spaced, not a burst).

```
MATCH (f:Fact {status:'active'})-[:IN_SCOPE]->(:Scope {id:$scope})
WHERE coalesce(f.tier,'episodic') = 'episodic'
WITH f ORDER BY f.created_at ASC LIMIT 5000
OPTIONAL MATCH (s:Step)-[r:READ {via:'use'}]->(f)
WITH f, collect(DISTINCT s.agent_id) AS agents, collect(r.at) AS uses
WITH f, agents, uses,
     size([(:Decision {flagged:false})-[:BASED_ON]->(f) | 1]) AS n_dec,
     size([(f)-[:VERIFIED_BY {outcome:'confirmed'}]->() | 1]) AS n_ver
WHERE (size(agents) >= 2 OR n_dec > 0 OR n_ver > 0)
  AND size(uses) >= 2 AND (max(uses) - min(uses)) > 86400000          // spaced
WITH f LIMIT $limit
SET f.tier = 'consolidated', f.consolidated_at = $now
RETURN f.id
```
(6.0.2 note: keep every relationship type in one comprehension and aggregate once; `coalesce(d.flagged,false)`
instead of `{flagged:false}` if the property can be absent.)

**Statement 2 (gist, `rw`).** For each confirmed-duplicate cluster in the scope (connected by `DUPLICATES` edges,
bounded to `*1..3`), create or reuse one `Gist` and link members. Bounded: ≤ 200 clusters per call, ≤ 20 members
each. The gist's `embedding` is the member centroid (computed in Python from the members' stored vectors; one
extra read).

**Statement 3 (downscale / demote, `rw`).** SHY: for the same ≤ 5,000 facts, compute `returned_unused /
(returned_used + returned_unused + 1)`; facts above 0.9 with ≥ 10 returns and no protection are listed (dry run) or
moved to `dormant` with `prior_status`, exactly as `sweep_apply` does today (same protection re-check in the same
statement). This *replaces* the activation threshold as the demotion criterion: a fact is parked because it was
repeatedly offered and never taken, not because it is old.

### 3.3 Where `returned_used` comes from

Today a `Recall` node has `RETURNED {rank, score}` edges and a `Step` has `READ {via}` edges. When a step closes
(the next `Step` is opened by the same agent, which the MCP layer already does), one bounded statement increments
`returned_used` on facts that were both `RETURNED` by a recall in that step and `READ via:'use'` in it, and
`returned_unused` on the ones only `RETURNED`. Bounded by the step's recalls (≤ 20) × k. This is the one new
write-on-read-adjacent path; it runs at step boundaries, not inside `recall`, so recall stays read-only in `off`
audit mode (in `off` mode there are no `Recall` nodes and the counters simply do not move).

### 3.4 Recall with gists

`recall` gains `collapse_gists: bool = true`: candidates that share a `Gist` are collapsed to one row (the member
nearest the query, with `gist_id`, `n_members`, and `members: [ids]`), ranked at the best member's score. A query
that names a member's distinguishing token (sprint tag, entity) still gets that member, because collapse happens
after ranking and keeps the nearest member. This directly removes the five-twins-in-top-five problem without any
activation change.

### 3.5 Integration

- `memory_sweep` stays (as the clock-based fallback) but its default becomes "list only what `consolidate` would
  demote". `restore_fact` works unchanged on `dormant` facts from either path.
- `memory_strength` shows `tier`, `gist_id`, `returned_used/unused`.
- `pin_fact` and all protection rules are checked inside statement 3 exactly as in `sweep_apply`.
- `as_of`, `why`, `knew_at`, `fact_history` ignore tiers and gists (history is not rewritten).
- Cost: three statements per `consolidate` call (background, operator-triggered or a cron); one bounded statement
  per step close; one extra read in `recall` only when gists exist (an `OPTIONAL MATCH (n)-[:INSTANCE_OF]->(g)` in
  the final projection of `recall.cypher`, no extra round trip).

## 4. Benchmark plan

L5b with two added modes: `on-consolidate` (one `consolidate` pass at V − 1 d, then recall with `collapse_gists`)
and `on-consolidate-nogist` (promotion + demotion without the gist collapse, to isolate the two effects). The
L5b generator must create the `DUPLICATES` links its sprints deserve (twins across sprints are *not* duplicates:
they differ in the sprint entity, so statement 2 should create **no** cross-sprint gist; this is a correctness
check of the pass, pre-registered as "0 cross-sprint gists"). Noise facts that are template-identical across
subjects *are* duplicates and should gist.

Hypotheses: noise share `on-consolidate` < `on-mult` (15.1%) by ≥ 3 points at recall@5 ≥ `off` − 0.01; the
demotion list contains 0 critical and 0 hot facts; cold-but-true facts demoted ≤ 2 (today's sweep hides 14 of 51,
because it uses age; the SHY rule needs ≥ 10 unused returns, which a cold fact never accumulates).

Fairness: a SQL arm can keep the same counters. The graph-specific part is the `RETURNED ∧ READ` join per step,
which is two edges away from the fact; in SQL it is one join on `(step_id, fact_id)`. Call it a tie on the
mechanism and a win on "the data is already there".

Biggest risk: the gist collapse is a presentation change, and a benchmark that counts "target in top 5" does not
reward returning fewer, better rows. Add a chars-per-correct-answer metric so the saving is visible.

## 5. Confidence

- That SHY-style demotion stops hiding cold-but-true facts: **high** (it keys on returns, which cold facts lack).
- That gist collapse improves what an agent reads: **medium**; measured by chars per correct answer, not recall@k.
- That any of this moves recall@1: **low**. Consolidation changes what is *offered*, not which twin is nearest.

## 6. Sources (opened)

[1] Kumaran, Hassabis & McClelland (2016) What learning systems do intelligent agents need? Complementary learning systems theory updated. TICS. http://stanford.edu/~jlmcc/papers/KumaranHassabisMcC16CLSUpdate.pdf
[2] Girardeau, Benchenane, Wiener, Buzsáki & Zugaro (2009) Selective suppression of hippocampal ripples impairs spatial memory. Nat. Neurosci. https://pubmed.ncbi.nlm.nih.gov/19749750/
[3] Post-learning replay of hippocampal–striatal activity is biased by reward-prediction signals (2025). Nat. Commun. https://pmc.ncbi.nlm.nih.gov/articles/PMC12644820
[4] Schaul, Quan, Antonoglou & Silver (2016) Prioritized experience replay. ICLR. https://arxiv.org/pdf/1511.05952
[5] Tononi & Cirelli (2014) Sleep and the price of plasticity. Neuron. https://pmc.ncbi.nlm.nih.gov/articles/PMC3921176/
