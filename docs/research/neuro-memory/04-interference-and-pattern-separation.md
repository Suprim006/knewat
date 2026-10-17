# 04. Interference, pattern separation and pattern completion: the L5b failure is an interference failure

Research note for Plexus. Builds on forgetting-A §1.4 (no repeat). `[unverified]` = not confirmed against an opened source.

## 1. Mechanism

### 1.1 Interference, and forgetting as inhibition of competitors

Anderson (2003) reframes interference: "forgetting is not a passive side effect of storing new memories, but results
from inhibitory control mechanisms recruited to override prepotent responses"; when a cue activates several
competing memories, selecting one requires suppressing the others, and that suppression persists as
retrieval-induced forgetting [1]. Retrieval-induced forgetting is strongest for *strong* competitors (forgetting-A
§1.4). In other words the brain does not rank similar competitors by popularity; it actively separates the target
from its competitors at the cue.

### 1.2 Pattern separation (dentate gyrus) and pattern completion (CA3)

Yassa & Stark (2011): "the ability to discriminate among similar experiences is a crucial feature of episodic
memory … computational models suggest that it is dependent on pattern separation", with convergent evidence from
recordings, lesions, immediate-early genes, transgenic mice and human fMRI for the dentate gyrus and CA3 [2].
Bakker, Kirwan, Miller & Stark (2008) showed with high-resolution fMRI that the human CA3/dentate gyrus treats a
slightly different version of a seen object (a *lure*) as new, while CA1 and other regions treat it as a repetition
[3]. Sahay et al. (2011) showed that increasing adult neurogenesis in the dentate gyrus is *sufficient* to improve
performance "in a specific cognitive task in which two similar contexts need to be distinguished" while leaving
other memory tasks unchanged [4]. The computational story (Marr; Treves & Rolls) is that the DG orthogonalises
overlapping inputs by sparse coding before CA3 stores them, and CA3's recurrent collaterals later complete a
partial cue to the nearest stored pattern [unverified: the models themselves were not opened for this note; the
reviews above cite them].

Lesson: *similar* memories are stored with their differences amplified, so that a cue containing the difference
retrieves the right one, and a cue without it retrieves a blend (completion). The system is built so that the
*discriminating* feature carries more weight than its share of the input.

### 1.3 The fan effect (ACT-R)

Anderson's spreading activation: `A_i = B_i + Σ_j W_j·S_ji`, and the association strength that works in practice is
`S_ji = S − ln(n_j)`, "where `n_j` is the fan of the j-th element" [5]. A cue element that is attached to many
memories spreads less activation to each (the fan effect: more facts about a person → slower, less reliable
retrieval of any one of them). Anderson & Reder (1999) show the effect is modulated by how the facts are
organised, not just counted [6]. This is a *graph-degree* quantity, computed from edges Plexus already has.

## 2. Why it matters for recall QUALITY

Look at what L5b actually did. Every sprint asserts `Acme Notes API S07 api_version: v14`, `… S08 api_version:
v16`, and so on; most facts sit in the shared `global` scope (only `release_channel` uses the sprint scope). The
probe is `"Acme Notes API S07 api_version"`. The embedding of `"Acme Notes API S07 api_version: v14"` and of
`"… S08 …: v16"` differ by one token each; the cosine gap is tiny. The discriminating feature, **S07**, is exactly
the lure difference that the dentate gyrus would amplify and that a flat embedding dilutes.

Three concrete observations about the current query:

1. The exact-keyword bypass checks whether the *value* contains every query word (`rank.py::_contains_every(value,
   words)`). The sprint tag is in the **entity name**, not the value, so the bypass never fires for these probes.
2. The query's entity ("Acme Notes API S07") is resolvable: `Entity.name` has a full-text index and
   `Entity.norm_name` a range index, and the P9 atomic `resolve_entity` already does exact → full-text → vector
   lookup. Recall never uses it. The graph *knows* which entity the query names and ignores it.
3. The ABOUT sibling expansion (`recall.cypher` lines 40–50) spreads activation from a seed to *its* entity's other
   facts, which is pattern *completion*, with a fixed `boost` and no fan term. A seed on the wrong twin pulls in the
   wrong twin's siblings.

So the failure is not that activation was too strong; it is that the ranking had no pattern-separation step, so a
0.09 activation range could override a 0.01 relevance gap (note 01 §2). Fix the separation and the activation
question becomes a tie-breaker, as it should be.

## 3. Design for Plexus

### 3.1 Query-side entity resolution (pattern separation at the cue)

Before the vector query, resolve the query's entity candidates once:

```
// engram/recall_entities (ro): the query's words against Entity.name (full-text) and Entity.norm_name (exact),
// bounded to 5 entities, with their fan (number of current facts ABOUT them in the searched scopes)
CALL db.idx.fulltext.queryNodes('Entity', $query) YIELD node AS e, score
WITH e, score ORDER BY score DESC LIMIT 5
MATCH (e)<-[:ABOUT]-(f:Fact {status:'active'})
RETURN e.id AS entity_id, e.name AS name, score, count(f) AS fan
```
(6.0.2: full-text `queryNodes` returns a BM25-like score; the P9 entity code already handles its quirks; exact
`norm_name` lookup is a second one-row read.) Cost: one extra read per recall (about 1 ms); none on write.

### 3.2 Discriminative re-rank (the pattern-separation score)

For each candidate `f` with relevance `rel(f)`:

```
ent_match(f) = 1 if f.entity_id ∈ resolved_entities else 0
S_ctx(f)     = Σ_{e matched by f} W · (S − ln(fan_e))           # ACT-R spreading activation; W = 1, S = ln(50)
                                                                # S − ln(fan) ≥ 0 for fan ≤ 50; clamp at 0 below
contrast(f)  = rel(f) − λ · mean_{g ∈ competitors(f)} rel(g)    # λ = 0.5; competitors(f) = candidates with the
                                                                # same predicate, a different entity, cosine(f,g) > 0.9
score(f)     = ln(rel(f)) + γ · ent_match(f) · S_ctx(f)/S + beta · tanh(z/2)    # z from note 01; γ = 0.15
```

- `ent_match·S_ctx` is the DG step: the one feature that separates lures from targets (the named entity) is given a
  weight that no cosine gap between paraphrases can match (`γ = 0.15` in log-relevance ≈ a 16% relative lift;
  the twin gap is ≤ 3%). The fan term keeps it from lighting up all 200 facts about a busy entity equally: a fact
  about an entity with 50 facts gets no lift from the entity alone (`S − ln 50 = 0`) and must win on relevance and
  predicate, which is the fan effect's actual prediction.
- `contrast` is reported, not added, in v1: it is the diagnostic "this row has near-identical competitors about
  other entities", surfaced as `lures: [ids]` so an agent sees the ambiguity. Adding it to the score is a v2
  experiment (it is retrieval-induced forgetting in soft form and interacts with gists, note 02).
- The keyword bypass is fixed to test `fact_text(entity, predicate, value)`, not `value` alone.

### 3.3 Pattern completion with a fan term (sibling expansion)

In `recall.cypher`'s sibling expansion, replace the flat `rank = d − boost` by `rank = d − boost · max(0, 1 −
ln(fan_e)/S)`: expansion from an entity with few facts stays strong (completing the pattern around a small,
specific entity), expansion from a hub entity is damped. The fan is `count((e)<-[:ABOUT]-(:Fact {status:'active'}))`,
already bound in the same `OPTIONAL MATCH`, so it is one aggregation added to a statement that exists; no new
round trip. (6.0.2: compute the count in a separate `WITH` before the `collect(...)[0..$sibs]`, since an aggregate
next to a pattern comprehension misbehaves, see `activation.cypher` header.)

### 3.4 Retrieval-induced forgetting: deliberately not written to the graph

When a step `use`s fact *f* after a recall that also returned competitors *g*, the biological rule would suppress
*g*. Not recommended as a write: (a) `SUPERSEDES`/`CONTRADICTS` already model explicit conflict with provenance,
and a silent suppression edge would be unexplainable; (b) in a shared memory one agent's choice would demote facts
other agents rely on; (c) the `returned_unused` counter (note 02 §3.3) captures the same evidence without a
negative edge and feeds demotion only after many repeats. The *read-time* version (contrast above) gives the
ranking effect without touching the graph.

### 3.5 Contradiction resolution by graph consistency (pattern completion over provenance)

Today a `CONTRADICTS` pair stays open until an agent quarantines or supersedes. CA3-style completion suggests
picking the member more consistent with the rest of the graph. A read-only `resolve_contradiction(fact_id)` tool
scores both ends:

```
MATCH (a:Fact {id:$id})-[:CONTRADICTS]-(b:Fact)
WITH a, b
WITH a, b,
  [x IN [a, b] | {
     id: x.id,
     agents:    size([(x)-[:ASSERTED_BY]->(:Agent) | 1]),
     decisions: size([(:Decision)-[:BASED_ON]->(x) | 1]),
     verified:  size([(x)-[:VERIFIED_BY {outcome:'confirmed'}]->() | 1]),
     trust:     size([(x)-[:DERIVED_FROM*1..3]->(:Source {trust:'high'}) | 1]),
     uses:      size([(:Step)-[:READ {via:'use'}]->(x) | 1]),
     recorded_at: x.recorded_at }] AS sides
RETURN sides
```
Python computes `support = 1.0·verified + 0.7·decisions + 0.5·trust + 0.3·agents + 0.1·ln(1+uses)` and returns
both sides with the breakdown and a recommendation (`supersede_with`, `keep_both`, `quarantine_suspect`) when the
margin exceeds a threshold (default 1.0). It **never writes**: the agent calls `verify_fact` or `confirm_duplicate`
with the recommendation, so the change is attributed and reversible. (6.0.2: one comprehension per relationship
type; the `*1..3` inside a comprehension is bounded by the depth, acceptable for two nodes.)

### 3.6 Integration

- `memory_strength` gains `entity_match`, `fan`, `S_ctx`, `lures`.
- `why_recalled` records the resolved entities and `S_ctx` on the `Recall` node (`entities: [ids]`) so the
  explanation says "ranked first because the query named its entity (fan 7)".
- `memory_sweep`, `pin_fact`, `verify_after`: unchanged.
- `recall(forgetting=off)` keeps today's exact order; the separation step is a separate flag
  `PLEXUS_RECALL_SEPARATION = on|off` so the two effects can be benchmarked apart.

## 4. Benchmark plan

**L5b, re-run as is** (same seed, N = 5 and N = 15), modes: `off`, `on-mult` (today), `sep` (separation only,
forgetting off), `sep+add` (separation + note 01 additive activation). Pre-registered hypotheses:

1. `sep` recall@1 ≥ 0.90 (today `off` 75.7%, `on` 63.6%). Reasoning: in `off`, 24% of probes already have a twin at
   rank 1 by cosine noise; the entity term should flip nearly all of them. Falsified if recall@1 < 0.85.
2. `sep+add` recall@1 within 0.01 of `sep` and noise share ≤ `on-mult`'s 15.1%: forgetting becomes free once
   separation exists.
3. Critical loss 0; recall@5 ≥ `off`.
4. Diagnostic: the class of rows ranked above the target (`critical/hot/noise/cold`) collapses to near zero for
   `critical` and `hot` under `sep`.

**C7 extended** (226 labelled duplicate / non-duplicate pairs): unchanged as a guard that the discriminator does not
raise false merges (it does not write, so this should be exactly 0/150 still).

**The SQL arm, fairly.** Give B1h the same signals: a `facts` table with `entity_id`, an entity full-text lookup on
the query, and `GROUP BY entity_id` for the fan. Hypothesis: **a tie on recall@1 with `sep`**. Both are the same
scoring rule over the same columns. What differs: Plexus computes it in one read (entity resolve + vector + fan)
against the indexes it already maintains, and `why_recalled` explains it. The claim this note supports is "a
graph-native pattern-separation step beats flat retrieval (`off`, B2) on near-twins by ~15 points of recall@1",
not "beats SQL".

**A test where SQL cannot trivially follow:** multi-hop separation. When the query names an entity that `RELATES`
to the target's entity (hops = 1, P9-b), the lift should propagate with a second `−ln(fan)` through the relation.
A B1h arm needs a recursive CTE and a hand-written fan per hop; feasible, so still a tie on correctness, but this
is the family (L6-C, never run) where the per-query engineering cost diverges.

Biggest risk of a tie: hypothesis 1 might be achieved by a one-line fix (make the keyword bypass look at the entity
name). If so, report that honestly; the fan term and `S_ctx` then matter only for hub entities, and L5b has none.
Add a "hub" variant: one entity with 200 facts of different predicates, probes name the predicate; prediction: the
fan term keeps recall@1 ≥ 0.9 where a flat entity boost would return any of the 200.

## 5. Confidence

- That pattern separation fixes the L5b near-twin loss: **high**. The discriminating token is present in the query,
  indexed on the entity, and ignored today.
- That it beats *flat* retrieval (`off`) on recall@1 by ≥ 10 points on L5b: **medium-high**; it depends on how many
  of the 24% rank-1 misses in `off` are twin errors (the post-hoc diagnostic says most).
- That it beats a SQL arm given the same columns: **low**; expect a tie by construction.
- That contradiction resolution helps recall quality: **medium**; it helps the *agent* decide, which L2/L6 do not
  measure; it is a tooling win, not a ranking win.

## 6. Sources (opened)

[1] Anderson (2003) Rethinking interference theory: executive control and the mechanisms of forgetting. J. Mem. Lang. https://www.memorycontrol.net/a2003.pdf
[2] Yassa & Stark (2011) Pattern separation in the hippocampus. Trends Neurosci. 34(10). https://ncbi.nlm.nih.gov/pubmed/21788086
[3] Bakker, Kirwan, Miller & Stark (2008) Pattern separation in the human hippocampal CA3 and dentate gyrus. Science 319. https://pmc.ncbi.nlm.nih.gov/articles/PMC2829853
[4] Sahay et al. (2011) Increasing adult hippocampal neurogenesis is sufficient to improve pattern separation. Nature 472. https://ncbi.nlm.nih.gov/pubmed/21460835
[5] Anderson (2001) Comments on activation, latency and the fan effect. ACT-R Summer School. http://act-r.psy.cmu.edu/wordpress/wp-content/themes/ACT-R/workshops/2001/talks/JRAactivation.pdf
[6] Anderson & Reder (1999) The fan effect: new results and new theories. JEP: General 128(2). https://pubmed.ncbi.nlm.nih.gov/10406105/
