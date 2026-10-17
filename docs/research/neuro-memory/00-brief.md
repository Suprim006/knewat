# Shared brief for the neuro-memory research subagents

You are one of six parallel research subagents. Each of you covers ONE memory mechanism and writes ONE file:
`docs/research/neuro-memory/<topic-slug>.md` inside the worktree `C:/Change_folder_after_HDD/wt-neuro-memory`
(branch `feature/neuro-memory-research`). Write nothing else in the repo. Do not touch other worktrees
(`main`, `wt-p10`, `wt-p11`, `wt-p12`, `wt-p9f-b`). Do not start, connect to, or query any FalkorDB container, and do
not change any code or test. This is research and doc-writing only. Do not commit; the orchestrator commits.

Use `web_search` / `web_extract` (or arxiv/PubMed pages) to get REAL sources. Every external claim gets a citation to a
URL you actually opened. Mark anything from model memory `[unverified]`. Give parameters and numbers from the papers
where they exist. Prefer primary papers and review articles over blog posts.

## What Plexus is (read these files FIRST, in this order; they are short)

1. `docs/forgetting.md` (172 lines): the activation-based forgetting that already exists (ACT-R base-level
   activation, event weights, surprise, protection, floor 0.9, memory_sweep dormant/active, restore).
2. `docs/research/forgetting-A-science-and-papers.md` (295 lines, 43 cited sources): the previous research note.
   It already covers Ebbinghaus, ACT-R base-level equation, spacing/testing effect (briefly), interference/RIF
   (briefly), salience/flashbulb (briefly), and the 2023-2026 agent-memory papers (Generative Agents, MemoryBank,
   Titans, FadeMem, Oblivion, ScrubJay, MemTier, ZenBrain, ...). DO NOT repeat that note. Go DEEPER on your mechanism:
   the actual neuroscience (circuits, models, parameters), newer or more specific sources, and above all a
   concrete design for Plexus.
3. `docs/BASELINE.md` lines 399-537: the L5b forgetting benchmark (pre-registration, the failed first run at floor
   0.5, the post-hoc diagnosis, the confirmatory run at floor 0.9). Read the "post-hoc diagnostic" paragraph: the
   thing that displaced the right fact was NOT noise but PROTECTED/HOT NEAR-TWIN facts from other sprints
   (near-identical texts), because the activation multiplier moved them more than the tiny relevance gap.
4. `docs/PLEXUS_REPORT.md` sections 7, 8, 9 (lines 574-795): what was built and measured, the SQL tie (P9/L6), and
   the honest shortcomings.
5. Code, for the exact current scoring:
   - `plexus/src/plexus/activation/model.py` (121 lines): `A = ln(Σ w·max(now−t,60s)^−d + surprise_bonus)`,
     d=0.5, newest K=50 events, `multiplier = floor + (1−floor)·σ(A−A0)`, protected uses max(A, A0),
     exact-keyword bypass = 1.0, `final = relevance × multiplier`, relevance = 1 − cosine-distance-after-sibling-boost.
   - `plexus/src/plexus/activation/rank.py` (76 lines): the re-rank over recall candidates (fetches 2k, keeps k).
   - `plexus/queries/activation/activation.cypher`: how events are gathered (READ {via:'use'|'recall', at, suspect},
     ASSERTED_BY.at, BASED_ON, CARRIES, VERIFIED_BY.at, SUPERSEDES, CONTRADICTS, DERIVED_FROM*1..3 → Source.trust).
   - `plexus/queries/engram/recall.cypher`: hybrid recall (vector top-`over` + full-text keyword seeds, scope
     INHERITS*0..3, validity window `valid_from <= t < valid_to`, status filter, 1-hop ABOUT sibling expansion).
   - Optional: `plexus/queries/engram/assert_fact.cypher` (write-time supersede / duplicate / contradiction),
     `plexus/queries/activation/sweep_apply.cypher`, `docs/graph-model.md`, `docs/staleness.md`.

Graph facts you can rely on: `Fact {id, predicate, value, status: active|superseded|dormant|forgotten|quarantined,
confidence, valid_from, valid_to (OPEN = 9999999999999), created_at, recorded_at, surprise, pinned, verify_state,
suspect_since, verify_after, embedding (384-d bge-small)}`; `(Fact)-[:ABOUT]->(Entity)`, `(Fact)-[:IN_SCOPE]->(Scope)`,
`(Fact)-[:ASSERTED_BY {at}]->(Agent)`, `(Fact)-[:DERIVED_FROM]->(Source|Episode|Fact)`, `(Fact)-[:SUPERSEDES]->(Fact)`,
`(Fact)-[:CONTRADICTS]-(Fact)`, `(Fact)-[:DUPLICATES|DUPLICATES_MAYBE]->(Fact)`, `(Step)-[:READ {via, at, suspect}]->(Fact)`,
`(Decision)-[:BASED_ON]->(Fact)`, `(Handoff)-[:CARRIES]->(Fact)`, `(Fact)-[:VERIFIED_BY {at, commit, outcome}]->(Agent)`,
`(Recall)-[:RETURNED {rank, score}]->(Fact)`, `(Entity)-[:RELATES {kind}]->(Entity)`. FalkorDB 6.0.2: no null
properties, no datetime(), epoch ms, one Cypher statement per atomic write, every write bounded (no unbounded
UNWIND / variable-length paths), vector index has no pre-filter (over-fetch then filter), `LIMIT` does not stop eager
writes. No LLM inside Plexus (local embedder only), so any "importance" signal must be computable from graph
structure, timestamps and embeddings.

## The problem you are solving (ground truth; do not re-litigate)

- On every retrieval-quality benchmark run so far, Plexus's recall TIED a hand-written SQL / flat baseline.
  The graph wins on provenance and explainability, not yet on retrieval quality.
- The existing forgetting is a ranking heuristic at floor 0.9. In L5b it reduced noise share (24% → 15%) but
  COST recall@1 (75.7% → 63.6%) and recall@5 (98.6% → 96.4%). It has not improved accuracy anywhere.
  Its failure mode: popular / protected near-twins outrank the relevant fact; protection stops sweeping, not
  outranking. The sweep is lossy for cold-but-true facts.
- The owner wants (a) retrieval quality that measurably BEATS the SQL/flat baseline, and (b) forgetting that
  behaves like biological forgetting, which is theorised to improve signal-to-noise in recall, not just save space.

## What your file must contain (use these section headings)

1. **Mechanism** — the neuroscience / cognitive science: circuits, the best-supported computational model(s),
   their parameters, and the key empirical results, with citations. Say what is settled and what is contested.
2. **Why it matters for recall QUALITY in an agent memory** — not storage cost. Argue from the science which
   retrieval errors it should reduce (wrong-twin, stale fact, noise, missed cold fact, contradiction, ...).
   Be concrete about what it would do to the L5b failure mode (near-twin displacement).
3. **Design for Plexus** — a concrete, falsifiable design:
   - schema/property changes (exact node/edge/property names and types);
   - exact Cypher changes or new query files (pseudocode is fine, but name the pattern, the bounds, and the
     FalkorDB 6.0.2 constraints you respect);
   - the scoring function in pseudocode, with parameter defaults and where they come from;
   - how it integrates with the existing `memory_strength`, `memory_sweep`, `review_date`/`verify_after`,
     `pin_fact`, `verify_fact`, `assert_fact` supersede/contradict paths;
   - cost: extra reads/writes per recall or per assert, and whether writes happen on read (today nothing is
     written on read except the READ edge in audit modes).
4. **Benchmark plan** — how to test it against the SQL-tie baseline so that a WIN (not a tie) is possible:
   which existing harness (L5b, C7, L2-scale, L6) or a new one, what the SQL arm would do (be fair: give SQL the
   same signals if it can compute them trivially), the metric, the pre-registered hypothesis with a number, and
   what result would falsify the idea. State the biggest risk that it ties again.
5. **Confidence** — your honest estimate (low/medium/high) that this would show a measurable recall-quality
   improvement over the baseline, and why. The owner explicitly wants honest shortcoming analysis.
6. **Sources** — numbered list of URLs you actually opened.

Length: 250-500 lines of Markdown. Plain prose, tables where useful. No marketing language.

When done, return a summary (≤ 300 words) containing: the file path, the one-paragraph design, the proposed
metric and hypothesis, and your confidence rating with the main risk.
