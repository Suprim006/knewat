# Crucible L2: provenance and time questions (pilot)

Run 20261014T215458Z-pilot · model `sonnet` (claude-sonnet-5-5) · context cap 32,000 chars · 5 of 43 questions

## Accuracy (exact match)

| Family | n | B0 | B1 | B2 | P |
|---|---|---|---|---|---|
| Decision provenance | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Time travel | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Supersession impact | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Recovery | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Forgetting | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| **All** | 5 | **5/5 (100.0%)** | **5/5 (100.0%)** | **5/5 (100.0%)** | **5/5 (100.0%)** |

Whole-reply-JSON-only variant (stricter): B0 5/5, B1 5/5, B2 5/5, P 5/5

## Cost

| Arm | tokens / question | cost / question | total cost | median latency | context chars (median) | truncated |
|---|---|---|---|---|---|---|
| B0 | 15930 | $0.0622 | $0.311 | 7.11 s | 25202 | 0 |
| B1 | 13436 | $0.0524 | $0.262 | 6.72 s | 18086 | 0 |
| B2 | 4105 | $0.0147 | $0.074 | 6.56 s | 2325 | 0 |
| P | 0 | $0.0000 | $0.000 | 2.7 ms | - | - |

## Wrong answers

none

## Headline

- L2: B0 + claude -p (sonnet) answered 5/5 (100.0%) exactly, 15930 tokens and $0.062 per question.
- L2: B1 + claude -p (sonnet) answered 5/5 (100.0%) exactly, 13436 tokens and $0.052 per question.
- L2: B2 + claude -p (sonnet) answered 5/5 (100.0%) exactly, 4105 tokens and $0.015 per question.
- L2: Knewat (deterministic Cypher) answered 5/5 (100.0%) exactly.
- L2: Knewat ties B0 by 0.0 points.
- L2: Knewat ties B1 by 0.0 points.
- L2: Knewat ties B2 by 0.0 points.

## Notes

- LLM cost of the answers reported here: $0.6465 over 15 claude -p calls (0 run in this invocation for $0.0000; 15 re-used from the on-disk cache demo_data/crucible/l2_cache, where each entry is the original call: tokens, cost and latency in the rows are those original measurements, so 'cached: true' on a row means re-scored, not free of cost).
- Each baseline question is one `claude -p` process (max-turns 3, no tools, context on stdin, ANTHROPIC_API_KEY removed); permission_denials and tool use are checked per call and fail the question.
- Scoring rule for the baselines: the model may reason in prose first, but the reply must END with exactly one {"answer": ...} JSON object (no text after it); that object is compared by exact match. `accuracy_whole_reply_json` is the stricter variant where only replies that are nothing but the JSON object count. The first full run used the whole-reply rule and scored B0 36/43, B1 38/43, B2 39/43 (Knewat 43/43): 13 baseline replies had a sentence of reasoning before a correct JSON object and were counted as unparseable. The rule was changed to the one above after seeing that (a methodology fix made with the results in view, so treat it as such), and every number was recomputed from the cached replies without any new LLM call. Both variants are reported.
- PILOT: 5 questions (one from each of 5 families); not a result. The full set is run only if this costs under the budget gate.

## Honesty

- L2: exact-match accuracy over a script-derived question set (43 questions, 10 families), one scenario, one model, one run per question; no LLM judge anywhere. Ground truth is computed from the scenario script, not read back from any arm.
- Baselines are the same unmodified `claude -p` with no tools, shown their own artifacts at the same 32,000-character cap. At this scenario size the B0 and B1 artifacts fit in the cap without truncation, so the cap is not what limits them; B2 deliberately sees only its top-12 retrieved chunks.
- Result in plain words: at this scenario size (12 tasks, 9 facts, 6 decisions) the whole B0 run is about 25k characters and the whole B1 dump about 18k, so Sonnet reads everything and answers every question; Knewat TIES them on accuracy. What Knewat does measurably better here is cost and determinism (no tokens, a few milliseconds, same answer every time versus 13-16k tokens and ~5 s per question). Whether accuracy diverges when the artifacts outgrow the context cap is NOT measured by this run.
- Arm P answers each question with a hand-written Cypher statement per question family. That is the point of the comparison (a graph can answer these with one query) but it is also engineering effort the baselines do not get: the baselines were given no hand-written SQL or grep helpers either.
- The Procedures family of BASELINE §2 is not in this set: the backend protocol has no procedure tool, so the arms cannot be compared on it. Cross-session recall is reduced to episodes recorded by agents (the protocol has no sessions).
- The scenario is the P3 Acme script replayed on the backend protocol, plus three L2 additions (the forum-post poison fault, one extra builder decision, two project-scoped facts); see crucible/l2/scenario.py.
- B1 and B2 (and B0's task file) keep only a task's final claimer, not the claim history; only B0's per-agent logs and Knewat's CLAIMED edges record who held an expired lease. Recovery questions therefore test what each arm's artifacts actually contain, as configured in L1.
