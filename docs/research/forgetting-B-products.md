# Forgetting, decay, importance and surprise: what agent-memory products actually implement

Research note B for Plexus (FalkorDB Graph Hacks, Track 02). Scope: shipped products, their source code, and their issue trackers, plus open-source Ebbinghaus/ACT-R projects and graph-database patterns. Retrieved 2026-10-16. Citations `[n]` map to the Sources block at the end; claims from my own reasoning are marked `[unverified]` or labelled "design".

## TL;DR

- **Almost nobody deletes by decay.** The mainstream pattern is supersede, soft-hide, or rank-only: Graphiti sets `invalid_at`/`expired_at` and keeps the edge[9]; Mem0 expiration hides but does not delete[1]; Mem0 decay never filters and floors at 0.3×[3]; Supermemory's forget is a soft delete[36]; Hermes's curator "never auto-deletes"[53]. Hard deletion is reserved for explicit user action, compliance, or crude TTL sweeps (LangGraph's store)[33].
- **Marketing outruns code.** Cognee's blog says `memify` "prunes stale nodes, strengthens frequent connections, reweights edges"[25], but Cognee's own tracker says "Today there is no decay" and its frequency weights are "non-functional"[24][28]; the one decay PR was closed unmerged[27]. MemOS's paper lists "expiration" in its lifecycle[39], but its Dream-memory maintenance module is an explicit unimplemented stub[40].
- **Real decay is query-time ranking.** Mem0 (platform only) multiplies the score by 0.3×–1.5× at search time[3]; MemOS re-derives priority from timestamps at retrieval time instead of trusting stored values[42]; Graphiti's `episode_mentions` reranker counts `MENTIONS` edges at query time[78]. No mainstream product computes activation from a full per-access log; only small open-source projects claim ACT-R-style activation[55][56], and the exact ACT-R form needs every use timestamp[61], which Plexus's `READ`/`RETURNED` edges already provide.
- **The documented failures are mostly about staleness and silent truncation, not over-forgetting**: months-old `MEMORY.md` loaded with no freshness signal[45], silent truncation of load-bearing entries[46], superseded facts ranked equal to current ones in Graphiti search[14], contradictory memories under Mem0's ADD-only extraction[6][8].
- **Evidence that forgetting improves accuracy is thin.** Removing HeLa-Mem's forgetting module had "minimal impact" on LoCoMo[69]; pruning 9.8% of a 27k-node graph left token F1 unchanged (+0.001) with a possible loss of up to 3.8 points of judged correctness[72]; eviction errors are mostly irreversible[70]. Sell forgetting as hygiene, latency and safety, not as a recall win.

## 1. Method and caveats

Official docs were read first, then source code (GitHub raw files and `gh` code/issue search), then issue trackers. Vendor benchmark claims are not repeated unless a primary source backs them. Several GitHub issues are bot-authored or promotional; those are flagged. Where a negative ("no decay in the code") comes from my own search of a repository rather than from a document, I say so. I did not run any of these products.

## 2. Products

### 2.1 Mem0

- **Mechanism.** Three separate controls. (1) *Expiration*: an optional `expiration_date` (`YYYY-MM-DD`, UTC, inclusive); after it passes, `search()` and `get_all()` skip the memory, but `get(id)` still returns it and clearing the date brings it back[1]. (2) *Decay*: a Platform-only, per-project opt-in toggle that multiplies the retrieval score by a factor between 0.3× and 1.5× based on access history[3][1]. (3) *Delete*: permanent, via `delete`, `batch_delete` (up to 1000), or filter-based `delete_all`[4].
- **Deletes or down-ranks?** Expiration hides; decay down-ranks only ("a soft ranking bias, never a filter"); delete is the only destructive path[1][3].
- **Parameters.** Decay has a single on/off toggle and fixed bounds: just accessed ≈1.5×, idle for weeks 0.4–0.6×, idle for months/years ≈0.3× floor[3]. Candidate pool is widened to `top_k × 3` (floor 50) so reordering has room[3]. Each returned memory gets a fire-and-forget reinforcement, with access history capped at the 20 most recent touches[3]. Memories that predate decay fall back to `event_date`, then `updated_at`[3]. Malformed expiration dates fail open (the memory is *not* hidden)[1].
- **Updates.** The OSS v3 algorithm moved to "single-pass ADD-only (one LLM call, no UPDATE/DELETE)"[74]. Memories flagged `immutable` cannot be updated; the documented path is delete and re-add[4].
- **Complaints and failure cases.**
  - ADD-only extraction can store "favorite player is Ronaldo" and "favorite player is Messi" side by side[8]. A second report says the new fact "never supersedes the old one at read time"[6]; it is still open and recommends a provenance/supersession layer[6].
  - A proposal for a forgetting-curve plugin (`weighted_score = min(access_count,255) * 0.5^(days_since_last_access/7)`, 14-day grace, delete below 0.05) was closed because native access tracking "would cut across the vector-store abstraction and require changes across all 30+ backends", so maintainers pointed to a community plugin[7].
  - A 32-day production audit of 10,134 entries found 97.8% were junk; that is an extraction-quality problem, but it shows what accumulates when nothing prunes[5].
  - In the same thread a bot-drafted comment claims, from a simulation, that periodic batch pruning beats per-write pruning; treat it as unvetted[7].

### 2.2 Zep / Graphiti

- **Mechanism.** Bi-temporal edges: `valid_at`, `invalid_at`, `expired_at` and `reference_time` live on `EntityEdge`[10]. The Zep paper describes four timestamps: `t'created`/`t'expired` track when facts enter or leave the system, `tvalid`/`tinvalid` track when they held[17].
- **How edges expire.** An LLM compares new edges against semantically related existing edges to find contradictions; for temporally overlapping contradictions the old edge's `tinvalid` is set to the new edge's `tvalid`, and "Graphiti consistently prioritizes new information"[17]. In code, `resolve_edge_contradictions` skips edges whose intervals do not overlap, and for an older edge sets `invalid_at = resolved_edge.valid_at` and `expired_at = now` (if unset)[9]. Nothing is deleted.
- **Decay.** None that I could find. A GitHub code search for "decay" in `getzep/graphiti` returned no hits when I ran it for this report. The only ranking signal derived from usage is the `episode_mentions` reranker, which counts `(Episodic)-[:MENTIONS]->(Entity)` edges at query time and sorts descending[78][15].
- **Maintainer position.** On "how to forget knowledge" the answer was to run a process that deletes old edges or filter by `created_at`/`valid_at`/`invalid_at`; forgetting is "use case dependent" and left to developers[13]. A salience-filtering RFC was closed with "We're not looking to add this to Graphiti at this time"[12]. Issue #1300 ("temporal decay algorithms") is an auto-generated growth-tool post, not a user report[11].
- **Complaints.** The MCP search tools return superseded facts "ranked equally with current ones", and the reporter notes an empty result is ambiguous between "never recorded" and "recorded but all versions superseded"[14].

### 2.3 Letta / MemGPT

- **Mechanism.** MemGPT keeps a FIFO message queue. At a "warning token count" (e.g. 70% of the window) the system injects a memory-pressure warning so the model can store things to working context or archival storage; at the "flush token count" (e.g. 100%) it evicts a set of messages (e.g. 50%) and rewrites a recursive summary[21]. Evicted messages stay in recall storage indefinitely[21]. Letta's docs say all state is persisted and "never lost, even once evicted from the context window"[22].
- **Archival memory** is unlimited, semantically searchable, tagged, and "agent-immutable" (agents cannot easily modify or delete it; developers can via the SDK)[18]. Core memory blocks have a character `limit`[76].
- **Sleep-time agents.** Enabling them creates a primary agent plus a sleep-time agent that rewrites memory in the background[19]. A community-compiled forum guide says they consolidate, deduplicate and "archive and prune outdated information"[20]. Its example expiry policy (session context 30 days unless referenced 3+ times; decisions and preferences never expire; "reference count matters more than age") is advice from Discord discussions, not a built-in feature[20].
- **Deletes or down-ranks?** Context eviction moves data to a lower tier without deleting it[21]; there is no documented decay score or TTL on archival passages[18] `[unverified]` beyond the pages read.
- **Complaints.** A compaction bug: `sliding_window` with `sliding_window_percentage: 0.15` wiped the whole conversation, leaving only the summary (closed)[77].

### 2.4 Cognee

- **Claim vs reality.** The blog says `memify` "prunes stale nodes, strengthens frequent connections, reweights edges based on usage signals"[25]. A hackathon issue filed by the maintainers states "Today there is no decay — only full `prune_*` wipes, targeted `forget()`, and an unwired binary TTL cleanup", and that decay would only affect ranking if `feedback_influence>0`, which is off by default[24]. The companion issue says frequency weights are "non-functional today" and the getters/setters `raise NotImplementedError`[28].
- **What exists.** A feedback-weight EMA with a learning rate `IMPROVE_FEEDBACK_ALPHA=0.1`[26].
- **The decay PR.** PR #3443 added `decay_memory`: exponential half-life decay of `feedback_weight` by age, pruning only orphan/leaf nodes (degree ≤ 1), `dry_run` defaulting to true, and `protect_node_types`[27]. It was closed without merging[27]. My code search for `decay_memory` on `main` found nothing.
- **Deletes or down-ranks?** Designed as both: decay a weight, then delete stale orphans[27]. Not shipped.

### 2.5 LangGraph store and LangMem

- **LangGraph TTL.** `TTLConfig` has `refresh_on_read` (default `true`: `get`/`search` reset the expiry timer), `default_ttl` in minutes, `sweep_interval_minutes` (default 5), and `omit_expired`[29][30]. Checkpoint TTL has `delete` and `keep_latest` strategies[29]. This is hard deletion on a timer.
- **Cost of refresh-on-read.** In the Postgres store, every refreshing `get` runs `UPDATE store SET expires_at = NOW() + ttl_minutes` and the sweeper runs `DELETE FROM store WHERE expires_at < NOW()`[33]. This is a literal write-on-read.
- **LangMem.** Each operation prompts an LLM to "expand or consolidate the memory state"; for collections, the system must reconcile new information by "*deleting*/*invalidating* or *updating*/*consolidating*"[32]. The guide says recall "should combine similarity with 'importance' ... as well as the memory's 'strength', which is a function of how recently/frequently it was used"[32], but I found no decay or forget implementation (code search for `decay` and `forget` in `langchain-ai/langmem` returned nothing). `enable_deletes` defaults to `False`[75].
- **Complaints.** None found specific to decay; the failure surface is LLM-driven consolidation quality `[unverified]`.

### 2.6 Supermemory

- **Mechanism (docs).** Facts persist until updated, preferences "strengthen with repetition", and episodes "decay unless significant"[35]. "Automatic forgetting" is time-based (temporary facts drop after expiry), contradiction-driven ("updates win"), and noise filtering at ingest[35]. Relationships: Updates (sets `isLatest`; history kept), Extends, Derives[35].
- **Deletes or down-ranks?** Forget is a soft delete: `isForgotten=true`, excluded from default search, retrievable with `include.forgottenMemories`[36][34]. Updates are versioned with the original at `isLatest=false`[36]. "Forget Matching" has an LLM choose which semantically matched memories to soft-delete[36].
- **Parameters.** The docs I read give no half-life, threshold or score formula for "decays unless significant"; I could not find the implementation, so treat it as an unverified marketing claim.
- **Complaints.** Via MCP the only removal path was similarity-based forget (threshold 0.85), which "can delete the wrong memory" when several are similar[37].

### 2.7 MemOS

- **Paper.** Describes a lifecycle of "generation, activation, fusion, archiving, and expiration" and a hierarchy of working memory, long-term storage and cold archives "governed by recency, access frequency, and importance"[39].
- **Code.** `src/memos/dream/maintenance.py` says it "is intentionally left unimplemented as a contribution entry point" and lists the intended rules: stale if `last_hit_at` is older than a TTL, low `usefulness_score`, and `invalidated_by_feedback`; it advises "gradual decay: lower confidence over time rather than hard-deleting on first miss"[40]. Separately, `recency.ts` implements `0.5^(age_days/14)` blended as `score * (0.3 + 0.7*decay)` so old results are "not zeroed out"[41]. The local plugin defines `priority = max(V,0) * 0.5^(Δt/30d)` and re-derives it at retrieval time "rather than trusting the persisted value"[42].
- **Deletes or down-ranks?** Down-ranks at query time; archive/expire is paper-level.

### 2.8 ChatGPT memory

- **Mechanism.** Two layers: saved memories (explicit or auto-saved) and reference-chat-history; the "improved memory" "continually updates a broader summary of relevant context"[48][51]. Memory "does not retain every detail"; ChatGPT decides what is relevant[48]. Controls "can also include search, sorting, automatic prioritization, and version history" depending on plan[48].
- **Deletes or down-ranks?** User deletion stops future use but does not scrub past conversations; logs of deleted saved memories may be retained up to 30 days[48]. The summary "may omit details that are less relevant"[51]. There is "no separate storage limit" for chat-history reference[51].
- **Parameters / complaints.** No decay parameters are published. I did not retrieve a primary source on a saved-memory capacity cap, so I make no claim about one.

### 2.9 Claude Code and Claude (claude.ai) memory

- **Claude Code auto memory.** A `MEMORY.md` index plus topic files; the first 200 lines or 25KB of `MEMORY.md` load every session, topic files are read on demand[43]. When near the limit, Claude Code reminds the model to "merge or drop stale entries"; over the limit the write succeeds but returns an error telling Claude to rewrite the index, "because everything past the limit is dropped on the next load"[43]. Memory files are excluded from the transcript retention sweep: they "stay until you or Claude edits or deletes them"[43]. So the only forgetting is model-driven rewriting under a hard size cap.
- **Complaints.** (a) The 200-line cap was originally undocumented and silently truncated[44]. (b) A months-old `MEMORY.md` primed every session with a project description that no longer matched, with "no freshness indication, no expiry"[45]. (c) Truncation drops entries with a one-line notice and no indication which, and in the report the cut began at a "load-bearing" rule[46]. (d) The hardcoded "compact to under 17.1KB" reminder made compaction passes delete load-bearing content "just to hit a number"[47].
- **Claude.ai memory.** Summary plus RAG chat search. Anthropic's help page says that after the migration to an improved memory, a user who thinks "Claude has forgotten something" can export the legacy memory until September 9, 2026 and paste it back[49]. I did not retrieve a primary source on the synthesis cadence or staleness handling.

### 2.10 Hermes Agent memory and curator

- **Memory.** `MEMORY.md` is capped at 2,200 chars and `USER.md` at 1,375 chars; memory does not auto-compact: an over-limit write returns an error and the agent must consolidate or remove entries in the same turn[52]. Exact duplicates are rejected; entries are injected as a frozen snapshot at session start[52]. No decay or timestamps on entries.
- **Curator (skills only).** A background pass tracks view/use/patch counts, marks skills `stale` after 14 unused days and moves them to `.archive/` after 30 (configurable), deterministic and with no LLM; LLM consolidation is off by default[53]. It "never auto-deletes", exempts pinned skills and skills referenced by any cron job, and gives never-used skills a grace floor because "zero uses is absence of evidence, not proof the skill is disposable"[53]. A manual `purge --days 90` exists[53].
- **Complaints (docs).** The most common report is "I told it to remember and the next session it forgot", usually because the model claimed a save without calling the `memory` tool[52].

## 3. Open-source decay projects and the papers they follow

| Project / paper | Mechanism | Delete or down-rank | Notes |
|---|---|---|---|
| Generative Agents | Recency = exponential decay, factor 0.995 per game hour since last *retrieval*; importance = LLM 1–10 rating at creation; relevance = similarity[60] | Down-rank only | Importance needs an LLM |
| MemoryBank | `R = e^(-t/S)`; on recall, `S += 1` and `t` resets[59] | Probabilistic forgetting | Strength grows with each recall |
| ACT-R base-level | `B = ln(Σ t_j^-d)`, d=0.5 by default; exact form needs "a complete record of the exact time stamps of each use"[61] | Activation only | Approximations store count + a few recent uses[61] |
| FadeMem | Differential exponential decay modulated by relevance, access frequency, temporal pattern, plus LLM conflict resolution; 45% storage reduction reported[73] | Fade and fuse | Self-reported |
| HeLa-Mem | Hebbian edges: `w(t+1) = (1-λ)·w(t) + η·I(co-activated)`[69] | Weights decay | Forgetting ablation: "minimal impact"[69] |
| YourMemory | `strength = importance·e^(-λ_eff·active_days)·(1+0.2·recall_count)`; `λ_eff = λ·(1-0.8·importance)`; per-category half-lives (e.g. failure ~11 d, strategy ~38 d); prune below 0.05[54] | Deletes below threshold; consolidation archives originals[54] | 270 GitHub stars at retrieval |
| Mnemoria | ACT-R activation, typed facts with "metabolic" decay, Hebbian links from co-access, IPS correction for popularity bias[55] | Down-rank | 0 stars at retrieval |
| mtrace | ACT-R power-law activation plus importance (1–10) plus recency, normalised so scales cannot swamp cosine[56] | Down-rank and forget | MIT, 10 stars |
| memory-decay-engine | Ebbinghaus retention with usage-based stability reinforcement vs a recency window[57] | Eviction by retention score | 9 stars |

Most of these are single-author repositories; star counts come from the GitHub API at retrieval time and are a rough maturity signal only. Two points carry over to Plexus: reinforcement and per-type decay rates are the common design, and Mnemoria explicitly corrects for popularity bias[55], which is the known failure of "boost whatever was returned".

## 4. Does forgetting help? Evidence

- Pruning a persistent 27,021-node graph by a weighted score of recency, access frequency, degree centrality and age removed 9.8% of nodes and 9.5% of bytes; token F1 was unchanged and judged correctness fell 1.6 points (95% interval bounds the loss at 3.8)[72]. The same paper found the graph did not beat a flat vector baseline, so the pipeline is the limit, not forgetting[72].
- Under a token budget, most errors from eviction are irreversible: 0.67–0.73 of restorable errors for FIFO, random and redundancy-aware eviction at 80k tokens, 0.60 for LLM-importance eviction, and 1.00 at 8k[70].
- A benchmark of personalised agents found "frequent reuse of invalid memories and failures to reconcile evolving memories", and introduced a metric that penalises obsolete memory[71]. That favours explicit supersession over passive decay.
- HeLa-Mem's authors say forgetting is "critical for scalability" but could not show a benefit on a ~300-turn benchmark[69].

## 5. Graph-database patterns for decay

- **No native TTL or decay in FalkorDB.** A request for vertex/edge TTL is an open issue[64]. What FalkorDB does offer is the arithmetic: `exp`, `pow`, `log`, `sqrt`, `timestamp()`, `reduce`, and list comprehensions[62], so `exp(-λ·(now-last))` or an ACT-R sum over edge timestamps can be written in a query.
- **Neo4j.** I found no documented built-in decay or forgetting in Neo4j's agent-memory library docs; a code search for "decay" hit paths I did not examine `[unverified]`. Graphiti's `episode_mentions` reranker is the working example of a usage signal computed from edges at query time, using plain Cypher aggregation[78].
- **Query-time scoring vs batch update.** Query-time: derive the score from timestamps already stored, nothing mutates (MemOS re-derives priority at retrieval[42]; Mem0's factor is applied per search[3]). Batch: a periodic job rewrites weights or statuses (Cognee's proposed `decay_memory`[27]; Hermes's curator transitions run on a 7-day interval[53]). Mem0's design is a hybrid: score at query time from a stored access history that is appended to on return[3].
- **Hebbian strengthening.** HeLa-Mem decays all edges by `(1-λ)` and adds `η` for pairs co-activated in the same retrieval set[69]; Mnemoria forms links from co-accessed memories[55]. Both store an edge weight, which implies a write per retrieval.

## 6. Cost and consistency: write a weight on every read vs compute from timestamps

| Concern | Store weight, update on read | Compute at query time from READ/RETURNED edges |
|---|---|---|
| Write amplification | One write per returned item per recall. Mem0 does it asynchronously ("fire-and-forget") and caps history at 20[3]; LangGraph does it synchronously on `get`[33] | None on the read path |
| Contention | FalkorDB serialises writes per graph while reads run in parallel on a snapshot[63], so write-on-read turns every recall into queue pressure | Reads only |
| Staleness | A stored weight is only correct at its last write; time decay still needs lazy or batch recomputation | Always current as of `now` |
| Atomicity | Read-modify-write races unless done as one atomic statement (FalkorDB makes a single query atomic[63]) | No race |
| Reproducibility | Overwrites history; cannot answer "what was the weight at step N" | Replayable as-of any time, because the log is the source of truth `[unverified]` design claim |
| Read cost | O(1) | O(events per candidate). ACT-R's exact form needs every timestamp, hence the approximations with a count plus *k* recent uses[61]; Mem0 caps at 20[3] |
| Precedent for avoiding per-read bookkeeping | Redis approximates LRU by sampling and keeps a 0–255 logarithmic LFU counter with `lfu-log-factor` and `lfu-decay-time`[67] | n/a |

Mem0's maintainers declined native access tracking partly because it touches every storage backend[7]; Plexus has one backend, and the access log already exists, which removes that obstacle.

## 7. Comparison matrix

| Product | Decay / down-rank | Hard delete | Supersession | Importance | User-facing knobs |
|---|---|---|---|---|---|
| Mem0 | Platform-only, 0.3–1.5×[3] | Explicit only[4] | Removed from OSS extraction (ADD-only)[74] | No built-in score found | Decay toggle, expiration date[1][3] |
| Graphiti/Zep | None found; `episode_mentions` count rerank[78] | Manual[13] | Yes, bi-temporal[9][17] | None[12] | Search filters on dates[13] |
| Letta | None documented | Agent cannot easily delete archival[18] | LLM rewrites blocks[20] | None | Block `limit`[76], compaction mode[77] |
| Cognee | Not shipped[24][27] | `forget()`/prune wipes[24] | Out of scope in the PR[27] | `importance_weight` mentioned[28] | `feedback_alpha`[26] |
| LangGraph/LangMem | Only TTL[29] | TTL sweep[33] | LLM update/delete; deletes off by default[75] | Described, not implemented[32] | `TTLConfig`[30] |
| Supermemory | Claimed for episodes[35] | Soft only[36] | `isLatest`[35] | "Significance"[35] | `forget`, versioned update[36] |
| MemOS | Recency/priority decay in some modules[41][42] | Stub[40] | Not examined | Paper-level[39] | Half-life in code[41] |
| ChatGPT | Opaque | User deletion[48] | Rolling summary[51] | "Automatic prioritization"[48] | UI toggles |
| Claude Code | None; size cap + model rewrite[43] | Model/user edits[43] | None | None | Auto-memory toggle, `autoMemoryDirectory`[43] |
| Hermes | None on memory; curator on skills[53] | Never auto[53] | Model edits[52] | None | Char caps, curator days[52][53] |

## 8. Implications for Plexus

Plexus already stores what these systems lack or approximate: validity windows, `SUPERSEDES`/`CONTRADICTS`, `Fact.status` including `forgotten`, per-agent `Step`s with `READ`/`WROTE`, `Recall` nodes with `RETURNED {rank, score}`, and `Decision -[BASED_ON]-> Fact` (local `docs/graph-model.md`).

### 8.1 Table-stakes vs differentiated

- **Table-stakes (competitors have it):** supersession with preserved history (Graphiti[9], Supermemory `isLatest`[35]); soft forget that keeps data (Supermemory[36], Hermes archive[53]; Plexus's `forgotten` status); an expiry date on a fact (Mem0[1], LangGraph[29]); bounded memory (Claude Code[43], Hermes[52]).
- **Differentiated:**
  1. Activation computed from a first-class, per-agent, per-step access log (`READ` vs merely `RETURNED`) instead of a counter plus last-touch. The closest competitor keeps 20 timestamps[3]; ACT-R's exact form needs all of them[61], which Plexus has.
  2. Deterministic and LLM-free, unlike importance scored by an LLM[60] or LLM-picked forgets[36].
  3. Dependency-aware retention: facts that a `Decision` is `BASED_ON` are protected. The nearest precedent is the curator skipping skills referenced by cron jobs[53]; Cognee's protection is by node type only[27].
  4. Explainable ranking: the same graph that scores a fact can show why (Recall → Fact edges).
  5. Honest negatives: "returned but never read" can be penalised, while Mem0 reinforces everything returned[3].

### 8.2 Recommended design (all design, not validated)

1. **Compute activation at query time; do not write weights on read.** Treat `READ` and `RETURNED` edges as the event log. Use ACT-R base-level, `B = ln Σ (now - t_j)^-d` with `d = 0.5`[61], or an exponential with a half-life per fact class, via `reduce`/`exp`/`pow`/`log` in Cypher[62]. Bound cost by considering only the last *K* events per fact (Mem0 uses 20[3]) plus a count. If scans get slow, materialise `read_count`/`last_read_at` on the `Fact` from a batch job, never on the recall path (FalkorDB serialises writes[63]).
2. **Rank, don't filter.** Blend as `score × (floor + (1-floor)·activation)` with a floor like Mem0's 0.3[3] or MemOS's α=0.3[41], so a relevant but unused fact can still surface. Keep a "show dormant" switch, as Mem0 has `show_expired`[1].
3. **Status transitions by batch sweep, not deletion.** `active → dormant → forgotten` (the `forgotten` status, `forgotten_at` and `prior_status` already exist), with `dry_run` default as in Cognee's PR[27] and a restore path as in Hermes[53]. Grace for never-read facts: zero reads is "absence of evidence"[53].
4. **Never hard-delete safety-critical or decision-supporting facts.** Exempt any fact that is (a) `BASED_ON` by a non-flagged `Decision`, carried by an open `Handoff`, or relevant to an open `Task`; (b) an endpoint of a `SUPERSEDES`/`CONTRADICTS` chain, since history is evidence; (c) marked by a policy class (e.g. constraints, credentials, safety rules; Mnemoria's typed decay makes constraints decay slowly[55]); (d) low-trust but quarantined. Hard delete only on explicit purge (compliance) as in Mem0's delete[4]. Because eviction is largely irreversible[70], default to demotion.
5. **Spend decay on bulky derived material first**: `Episode`, `Recall`, `ToolCall` and per-step logs. Pruning ~10% of low-scoring nodes was nearly free in one study[72], and it limits growth without touching curated facts.
6. **Surprise, deterministically.** Compute once at write time and store as an immutable property (no write-on-read problem); let it lengthen the half-life, in the way importance reduces λ in YourMemory[54] and recall resets strength in MemoryBank[59]. Candidate signals, none needing an LLM:
   - *Contradiction/supersede event*: a new fact that `SUPERSEDES` or `CONTRADICTS` an existing active fact is a belief revision; give it a surprise bonus (the prior model was wrong). Cross-agent contradiction is stronger than self-update.
   - *Write-time novelty*: `1 - max cosine similarity` of the new `value_embedding` to existing facts in scope; exact and paraphrase duplicates (`DUPLICATES`) score 0.
   - *Retroactive error*: when a failed `Run` or a flagged `Decision` traces back to a fact via `BASED_ON`, raise that fact's surprise/importance (prediction error shows the fact mattered).
   - *Retrieval gap*: a `Recall` whose best score is poor signals missing knowledge; facts written to fill it inherit a bonus.
   - These are the deterministic analogues of Titans' gradient-based surprise (needs a neural memory)[65] and of LLM-rated importance[60]. They should be benchmarked before being sold as "human-like"; no source here validates them.
7. **Hebbian co-access without stored edges.** Count pairs of facts `RETURNED` by the same `Recall`, or `READ` in the same `Step`, at query time (a join over existing edges). Only count `READ` or rank-weighted `RETURNED` to avoid the feedback loop where whatever is returned gets boosted and returned again; Mnemoria added an IPS correction for exactly this popularity bias[55]. If it must be materialised, use a batch-built `CO_ACCESSED {n, last_at}` edge.
8. **Position it as hygiene and safety.** The evidence supports "same accuracy, less noise, bounded growth"[72][69], not "better recall". Pair it with supersession, which is what the invalid-memory benchmark rewards[71], and with the freshness signals Claude Code users are asking for[45]: return `last_read_at`, activation and "superseded by" with each recall so an agent can tell stale from current (Graphiti users asked for the same[14]).

### 8.3 Open questions

- Which half-life or exponent suits multi-agent coordination facts versus personal-assistant facts? No source gives values for this setting; the numbers above come from chat-assistant projects.
- Does `READ`-weighted activation beat `RETURNED`-weighted on the existing crucible questions? That would be a direct, cheap ablation.
- Supermemory's and ChatGPT's implementations are closed; their matrix rows reflect documentation only.

## Sources

[1] https://docs.mem0.ai/platform/features/memory-expiration — Mem0: Memory Expiration
[3] https://docs.mem0.ai/platform/features/memory-decay — Mem0: Memory Decay
[4] https://docs.mem0.ai/core-concepts/memory-operations/delete — Mem0: Delete Memory
[5] https://github.com/mem0ai/mem0/issues/4573 — mem0 issue 4573: 97.8% junk audit
[6] https://github.com/mem0ai/mem0/issues/4956 — mem0 issue 4956: ADD-only stale/contradictory
[7] https://github.com/mem0ai/mem0/issues/5330 — mem0 issue 5330: access frequency tracking proposal
[8] https://github.com/mem0ai/mem0/issues/5867 — mem0 issue 5867: ADD-only conflicting memories
[9] https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/utils/maintenance/edge_operations.py — graphiti source: edge_operations.py
[10] https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/edges.py — graphiti source: edges.py
[11] https://github.com/getzep/graphiti/issues/1300 — graphiti issue 1300: temporal decay algorithms
[12] https://github.com/getzep/graphiti/issues/1602 — graphiti issue 1602: salience-based fact filtering RFC
[13] https://github.com/getzep/graphiti/issues/864 — graphiti issue 864: how to forget knowledge
[14] https://github.com/getzep/graphiti/issues/1645 — graphiti issue 1645: MCP stale-fact filtering
[15] https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/search/search_config.py — graphiti source: search_config.py
[17] https://arxiv.org/pdf/2501.13956 — Zep paper PDF (arXiv 2501.13956)
[18] https://docs.letta.com/v1-sdk/memory/archival-memory — Letta Docs: Archival memory
[19] https://www.letta.com/blog/sleep-time-compute — Letta blog: Sleep-time Compute
[20] https://forum.letta.com/t/sleeptime-agents-for-memory-consolidation-best-practices-guide/154 — Letta forum: Sleeptime agents best practices
[21] https://arxiv.org/pdf/2310.08560 — MemGPT: Towards LLMs as Operating Systems (arXiv 2310.08560)
[22] https://docs.letta.com/guides/agents/compaction — Letta Docs: Compaction settings
[24] https://github.com/topoteretes/cognee/issues/3390 — Cognee issue 3390: FORGET / decay task
[25] https://cognee.ai/blog/fundamentals/how-cognee-builds-ai-memory — Cognee blog: How Cognee Builds AI Memory
[26] https://raw.githubusercontent.com/topoteretes/cognee/main/cognee/modules/improve/config.py — cognee source: modules/improve/config.py
[27] https://github.com/topoteretes/cognee/pull/3443 — Cognee PR 3443 (closed, not merged): decay_memory
[28] https://github.com/topoteretes/cognee/issues/3391 — Cognee issue 3391: RE-WEIGHT task
[29] https://docs.langchain.com/langsmith/configure-ttl — LangSmith docs: How to add TTLs
[30] https://reference.langchain.com/python/langgraph.store/base/TTLConfig — LangGraph reference: TTLConfig
[32] https://langchain-ai.github.io/langmem/concepts/conceptual_guide — LangMem: Conceptual guide
[33] https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/checkpoint-postgres/langgraph/store/postgres/base.py — langgraph source: store/postgres/base.py (TTL columns, refresh on get)
[34] https://supermemory.ai/blog/memory-lifecycle-retention-corrections-deletion — Supermemory blog: Agent Memory Lifecycle
[35] https://supermemory.ai/docs/concepts/graph-memory — Supermemory docs: Graph memory
[36] https://supermemory.ai/docs/recall/memory-operations — Supermemory docs: Memory operations
[37] https://github.com/supermemoryai/supermemory/issues/1442 — supermemory issue 1442: MCP: no way to delete a document by ID — forget-by-similarity is the o
[39] https://arxiv.org/pdf/2507.03724 — MemOS: A Memory OS for AI System (arXiv 2507.03724)
[40] https://raw.githubusercontent.com/MemTensor/MemOS/main/src/memos/dream/maintenance.py — MemOS source: src/memos/dream/maintenance.py
[41] https://raw.githubusercontent.com/MemTensor/MemOS/main/packages/memos-core/src/recall/recency.ts — MemOS source: packages/memos-core/src/recall/recency.ts
[42] https://raw.githubusercontent.com/MemTensor/MemOS/main/apps/memos-local-plugin/core/retrieval/ALGORITHMS.md — MemOS source: memos-local-plugin core/retrieval/ALGORITHMS.md
[43] https://code.claude.com/docs/en/memory — Claude Code docs: Memory
[44] https://github.com/anthropics/claude-code/issues/25006 — claude-code issue 25006: MEMORY.md undocumented 200-line limit
[45] https://github.com/anthropics/claude-code/issues/85075 — claude-code issue 85075: months-old MEMORY.md loads silently, no expiry
[46] https://github.com/anthropics/claude-code/issues/99403 — claude-code issue 99403: MEMORY.md silently truncated when over size limit — no indication which entries
[47] https://github.com/anthropics/claude-code/issues/91188 — claude-code issue 91188: Feature request: make the auto-memory MEMORY.md compaction reminder threshold co
[48] https://help.openai.com/en/articles/8590148-memory-in-chatgpt — OpenAI Help: Memory in ChatGPT
[49] https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context — Claude Help Center: chat search and memory
[51] https://help.openai.com/en/articles/8590148-memory-in-chatgpt-faq — OpenAI Help: Memory FAQ
[52] https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/features/memory.md — Hermes Agent docs: Persistent memory (memory.md)
[53] https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/user-guide/features/curator.md — Hermes Agent docs: Curator (curator.md)
[54] https://github.com/sachitrafa/YourMemory — GitHub: sachitrafa/YourMemory
[55] https://github.com/Tranquil-Flow/mnemoria — GitHub: Tranquil-Flow/mnemoria
[56] https://github.com/Roxx0x/mtrace — GitHub: Roxx0x/mtrace
[57] https://github.com/Emmimal/memory-decay-engine — GitHub: Emmimal/memory-decay-engine
[59] https://arxiv.org/pdf/2305.10250 — MemoryBank: Enhancing LLMs with Long-Term Memory (arXiv 2305.10250)
[60] https://arxiv.org/pdf/2304.03442v2 — Generative Agents (arXiv 2304.03442) PDF v2
[61] https://act-r.psy.cmu.edu/wordpress/wp-content/uploads/2012/12/652petrovAbstract.pdf — Petrov (2006) Computationally efficient approximation of ACT-R base-level learning
[62] http://docs.falkordb.com/cypher/functions — FalkorDB docs: Cypher functions
[63] https://docs.falkordb.com/design/concurrency — FalkorDB docs: Atomicity and Concurrency
[64] https://github.com/FalkorDB/FalkorDB/issues/167 — FalkorDB issue 167: no vertex/edge TTL or timestamp property
[65] https://arxiv.org/pdf/2501.00663 — Titans: Learning to Memorize at Test Time (arXiv 2501.00663)
[67] https://redis.io/docs/latest/develop/reference/eviction — Redis docs: Key eviction
[69] https://arxiv.org/pdf/2604.16839v1 — HeLa-Mem PDF (arXiv 2604.16839v1)
[70] https://arxiv.org/abs/2609.08279 — What Eviction Destroys: A Restore-Counterfactual Audit of Forgetting in Agent Memory (arXiv 2609.08279)
[71] https://arxiv.org/abs/2604.20006 — From Recall to Forgetting: Benchmarking Long-Term Memory for Personalized Agents (arXiv 2604.20006)
[72] https://arxiv.org/abs/2608.28978 — Selective Forgetting: A Graph-Based Memory Framework for Long-Term LLM Agents (arXiv 2608.28978)
[73] https://arxiv.org/abs/2601.18642 — FadeMem: Biologically-Inspired Forgetting for Efficient Agent Memory (arXiv 2601.18642)
[74] https://docs.mem0.ai/migration/oss-v2-to-v3 — Mem0 docs: Migrating to the New Memory Algorithm (OSS v2 to v3)
[75] https://raw.githubusercontent.com/langchain-ai/langmem/main/src/langmem/knowledge/extraction.py — langmem source: knowledge/extraction.py
[76] https://docs.letta.com/guides/agents/memory-blocks — Letta Docs: Memory blocks
[77] https://github.com/letta-ai/letta/issues/3270 — letta issue 3270: sliding_window compaction ignores percentage, performs full context wipe
[78] https://raw.githubusercontent.com/getzep/graphiti/main/graphiti_core/search/search_utils.py — graphiti source: search/search_utils.py (episode_mentions_reranker)
