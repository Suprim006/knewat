# Crucible L2 at scale (pilot)

Run 20261014T223746Z-pilot · model `sonnet` (claude-sonnet-5-5) · context cap 32,000 chars · 5 of 40 questions · 20 sprints

## History vs the context budget

| Artifact | chars | x cap |
|---|---|---|
| B0 | 532,813 | 16.65 |
| B1 | 332,599 | 10.39 |
| B2 | 147,471 | 4.61 |

## Accuracy (exact match)

| Family | n | B0 | B1 | B2 | P |
|---|---|---|---|---|---|
| Decision provenance | 1 | 0/1 | 0/1 | 0/1 | 1/1 |
| Supersession impact | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Contradictions | 1 | 1/1 | 1/1 | 0/1 | 1/1 |
| Recovery | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Forgetting | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| **All** | 5 | **4/5 (80.0%)** | **4/5 (80.0%)** | **3/5 (60.0%)** | **5/5 (100.0%)** |

Wilson 95% intervals on the totals: B0 37.6-96.4%, B1 37.6-96.4%, B2 23.1-88.2%, P 56.6-100.0%.

By position of the asked sprint in the history:

| Stratum | sprints | B0 | B1 | B2 | P |
|---|---|---|---|---|---|
| early | S01-S06 | 2/2 | 2/2 | 2/2 | 2/2 |
| middle | S07-S14 | 1/1 | 1/1 | 1/1 | 1/1 |
| late | S15-S20 | 1/2 | 1/2 | 0/2 | 2/2 |

Whole-reply-JSON-only variant (stricter): B0 4/5, B1 4/5, B2 3/5, P 5/5

## Cost

| Arm | tokens / question | cost / question | total cost | median latency | context chars (median) |
|---|---|---|---|---|---|
| B0 | 19635 | $0.0775 | $0.388 | 4.86 s | 31779 |
| B1 | 22217 | $0.0877 | $0.438 | 5.05 s | 31986 |
| B2 | 4545 | $0.0175 | $0.087 | 6.34 s | 2403 |
| P | 0 | $0.0000 | $0.000 | 9.6 ms | - |

## Failure analysis

- **B0**: 1 wrong; 0 unparseable replies, 0 failed calls; of the wrong answers with a checkable answer, 0 had every expected item's words somewhere in the context and 1 did not; median share of shown lines that mention the asked sprint: 0.256.
- **B1**: 1 wrong; 1 unparseable replies, 0 failed calls; of the wrong answers with a checkable answer, 0 had every expected item's words somewhere in the context and 1 did not; median share of shown lines that mention the asked sprint: 0.106.
- **B2**: 2 wrong; 0 unparseable replies, 0 failed calls; of the wrong answers with a checkable answer, 1 had every expected item's words somewhere in the context and 1 did not; median share of shown lines that mention the asked sprint: 0.231.

## Wrong answers

- **B0 Q03** (decision_provenance, S20, late): expected `["auth_method=JWT bearer tokens (ES384, key s20)@researcher", "auth_method=API key in X-Ops-Key header@planner"]`, got `["auth_method=JWT bearer tokens (ES384, key s20)@researcher"]`; evidence in context 0/2
- **B1 Q03** (decision_provenance, S20, late): expected `["auth_method=JWT bearer tokens (ES384, key s20)@researcher", "auth_method=API key in X-Ops-Key header@planner"]`, got `null` (text after the JSON object); evidence in context 0/2
- **B2 Q03** (decision_provenance, S20, late): expected `["auth_method=JWT bearer tokens (ES384, key s20)@researcher", "auth_method=API key in X-Ops-Key header@planner"]`, got `["auth_method=JWT bearer tokens (ES384, key s20)@unknown", "auth_method=API key in X-Ops-Key header@unknown"]`; evidence in context 2/2
- **B2 Q21** (contradictions, S20, late): expected `["auth_method=JWT bearer tokens (ES384, key s20)", "auth_method=API key in X-Ops-Key header"]`, got `[]`; evidence in context 0/2

## Headline

- L2-scale: B0 + claude -p (sonnet) answered 4/5 (80.0%) exactly, 19635 tokens and $0.077 per question.
- L2-scale: B1 + claude -p (sonnet) answered 4/5 (80.0%) exactly, 22217 tokens and $0.088 per question.
- L2-scale: B2 + claude -p (sonnet) answered 3/5 (60.0%) exactly, 4545 tokens and $0.018 per question.
- L2-scale: Knewat (deterministic Cypher) answered 5/5 (100.0%) exactly.
- L2-scale: Knewat beats B0 by 20.0 points.
- L2-scale: Knewat beats B1 by 20.0 points.
- L2-scale: Knewat beats B2 by 40.0 points.

## Knewat changes relative to the 43-question L2 answerer

- Operations whose arguments already name a unique thing (task id, fact label, decision name, subject, source uri) run the unchanged l2 operation with the unchanged statements: decision_facts, decision_fact_agents, decision_sources, handoff_artifacts, handoff_route, handoff_facts, as_of_values, as_of_facts, value_history, decisions_on_fact, superseder, fact_agent, fact_source, fact_scope, blocked_by_failure, direct_dependencies, ready_after, reclaimer, previous_claimer, current_value, scope_leak, episode_agent, remaining_from_source, forgotten_facts.
- Nine operations ask about a whole class (all handoffs to X, all decisions on superseded facts, ...) and are restricted to the sprint named in the question by a Python filter over the rows of the same statements (task ids start with the sprint tag, source uris contain it, episode texts start with it): handoffs_to, handoffs_with_superseded_facts, decisions_on_superseded, decisions_on_forgotten, active_conflicts, active_conflict_agents, reclaimed_tasks, completed_by, episode_count.
- One operation needs one new read-only statement: visible_facts runs queries/l2scale/facts_visible_subject.cypher (l2/facts_visible plus a subject restriction), because the global scope now holds the facts of all 20 sprints.
- No other query was changed; the original knewat_answerer.py and queries/l2/*.cypher are untouched.

## Notes

- LLM cost of the answers reported here: $0.9133 over 15 claude -p calls (15 run in this invocation for $0.9134; 0 re-used from the on-disk cache demo_data/crucible/l2_scale_cache, where each entry is the original call: tokens, cost and latency in the rows are those original measurements, so 'cached: true' means re-scored, not free of cost).
- Each baseline question is one `claude -p` process (max-turns 3, no tools, context on stdin, ANTHROPIC_API_KEY removed); permission_denials and tool use are checked per call and fail the question.
- Scoring rule for the baselines (decided before the first paid call, = the final L2 rule): the model may reason in prose first, but the reply must END with exactly one {"answer": ...} JSON object (no text after it); that object is compared by exact match. `accuracy_whole_reply_json` counts only replies that are nothing but the JSON object.
- PILOT: 5 questions (five families, all three strata); not a result. It only gates the cost of the full run.

## Honesty

- L2-scale: exact-match accuracy over 40 script-derived questions (10 families x 4) about 20 independent sprints of one team history; one scenario family, one model (sonnet), one run per question; no LLM judge. Ground truth is computed from the per-sprint scenario ledgers, not read back from any arm. Pre-registered in docs/BASELINE.md before the first paid call.
- The history is 20 repetitions of the same synthetic story with varied ids and values. Real histories are messier; sprints here do not interact, which favours retrieval (a question names its sprint and a sprint's records share its tag).
- Every question names exactly one sprint, so competent keyword retrieval can find a sprint's records. Questions that aggregate across sprints (the strongest case for a graph) are NOT in this set.
- Baselines are the same unmodified `claude -p --model sonnet` with no tools at the same 32,000-character cap, shown BM25-ranked chunks/rows (B0, B1) or vector top-12 (B2) selected with the question text. The selectors were written once, before any paid call, and not tuned afterwards.
- Arm P answers with hand-written Cypher per question family (the same operations as the 43-question L2 run, with the sprint scoping listed in the results); that engineering effort is part of what P costs and the baselines get no equivalent helper.
- Reply rule for the baselines is the final L2 rule: prose may precede the reply, which must END with one {"answer": ...} object; the whole-reply-JSON variant is reported next to it.
- B1 and B2 (and B0's task file) keep only a task's final claimer, not the claim history; only B0's per-agent logs and Knewat's CLAIMED edges record who held an expired lease. Recovery questions therefore test what each arm's artifacts actually contain, as configured in L1.
