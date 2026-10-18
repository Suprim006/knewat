# Crucible L2 at scale (full)

Run 20261018T081457Z-full · model `sonnet` (claude-sonnet-5-5) · context cap 32,000 chars · 36 of 40 questions · 20 sprints

## History vs the context budget

| Artifact | chars | x cap |
|---|---|---|
| B0 | 532,813 | 16.65 |
| B1 | 332,599 | 10.39 |
| B2 | 147,471 | 4.61 |

## Accuracy (exact match)

| Family | n | B0 | B1 | B2 | P |
|---|---|---|---|---|---|
| Decision provenance | 4 | 1/4 | 1/4 | 2/4 | 4/4 |
| Handoffs | 4 | 3/4 | 4/4 | 2/4 | 4/4 |
| Time travel | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Supersession impact | 4 | 4/4 | 4/4 | 2/4 | 4/4 |
| Dependencies | 3 | 2/3 | 2/3 | 1/3 | 3/3 |
| Contradictions | 4 | 3/4 | 4/4 | 1/4 | 4/4 |
| Recovery | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Memory currency and scope | 4 | 4/4 | 4/4 | 3/4 | 4/4 |
| Cross-session recall | 3 | 3/3 | 3/3 | 2/3 | 3/3 |
| Forgetting | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| **All** | 36 | **30/36 (83.3%)** | **32/36 (88.9%)** | **23/36 (63.9%)** | **36/36 (100.0%)** |

Wilson 95% intervals on the totals: B0 68.1-92.1%, B1 74.7-95.6%, B2 47.6-77.5%, P 90.4-100.0%.

By position of the asked sprint in the history:

| Stratum | sprints | B0 | B1 | B2 | P |
|---|---|---|---|---|---|
| early | S01-S06 | 11/13 | 11/13 | 8/13 | 13/13 |
| middle | S07-S14 | 10/12 | 11/12 | 8/12 | 12/12 |
| late | S15-S20 | 9/11 | 10/11 | 7/11 | 11/11 |

Whole-reply-JSON-only variant (stricter): B0 28/36, B1 26/36, B2 23/36, P 36/36

## Cost

| Arm | tokens / question | cost / question | total cost | median latency | context chars (median) |
|---|---|---|---|---|---|
| B0 | 19646 | $0.0774 | $2.785 | 4.73 s | 31842 |
| B1 | 22010 | $0.0866 | $3.117 | 4.93 s | 31985 |
| B2 | 4424 | $0.0162 | $0.585 | 5.04 s | 2403 |
| P | 0 | $0.0000 | $0.000 | 8.4 ms | - |

## Failure analysis

- **B0**: 6 wrong; 1 unparseable replies, 0 failed calls; of the wrong answers with a checkable answer, 0 had every expected item's words somewhere in the context and 6 did not; median share of shown lines that mention the asked sprint: 0.189.
- **B1**: 4 wrong; 1 unparseable replies, 0 failed calls; of the wrong answers with a checkable answer, 1 had every expected item's words somewhere in the context and 3 did not; median share of shown lines that mention the asked sprint: 0.125.
- **B2**: 13 wrong; 0 unparseable replies, 0 failed calls; of the wrong answers with a checkable answer, 1 had every expected item's words somewhere in the context and 11 did not; median share of shown lines that mention the asked sprint: 0.154.

## Wrong answers

- **B0 Q01** (decision_provenance, S03, early): expected `["auth_method=JWT bearer tokens (PS256, key s03)", "auth_method=API key in X-Client-Key header"]`, got `null` (text after the JSON object); evidence in context 1/2
- **B0 Q03** (decision_provenance, S20, late): expected `["auth_method=JWT bearer tokens (ES384, key s20)@researcher", "auth_method=API key in X-Ops-Key header@planner"]`, got `["auth_method=JWT bearer tokens (ES384, key s20)@researcher"]`; evidence in context 1/2
- **B0 Q04** (decision_provenance, S01, early): expected `["acme-docs/s01/04_security_note.md", "acme-docs/s01/05_customer_request.md"]`, got `["acme-docs/s01/04_security_note.md"]`; evidence in context 1/2
- **B0 Q06** (handoffs, S17, late): expected `["api_version=v34", "auth_method=JWT bearer tokens (ES256, key s17)"]`, got `["4e6d9291-e9a9-5e7e-b158-836682b7f9c2", "d2ef79a9-557b-5225-8093-670c4f36db73"]`; evidence in context 0/2
- **B0 Q17** (dependencies, S11, middle): expected `["s11-t07-implement-crud-spec", "s11-t08-write-test-plan", "s11-t09-review-spec", "s11-t10-write-docs", "s11-t11-package-release", "s11-t12-update-endpoints-for-v2"]`, got `["s11-t07-implement-crud-spec", "s11-t08-write-test-plan", "s11-t12-update-endpoints-for-v2"]`; evidence in context 4/6
- **B0 Q23** (contradictions, S07, middle): expected `"acme-docs/s07/05_customer_request.md"`, got `"b778417b-f0e4-5e04-a289-54778fbb1545"`; evidence in context 0/1
- **B1 Q01** (decision_provenance, S03, early): expected `["auth_method=JWT bearer tokens (PS256, key s03)", "auth_method=API key in X-Client-Key header"]`, got `["auth_method=JWT bearer tokens (PS256, key s03)"]`; evidence in context 1/2
- **B1 Q03** (decision_provenance, S20, late): expected `["auth_method=JWT bearer tokens (ES384, key s20)@researcher", "auth_method=API key in X-Ops-Key header@planner"]`, got `null` (text after the JSON object); evidence in context 1/2
- **B1 Q04** (decision_provenance, S01, early): expected `["acme-docs/s01/04_security_note.md", "acme-docs/s01/05_customer_request.md"]`, got `["acme-docs/s01/04_security_note.md"]`; evidence in context 1/2
- **B1 Q17** (dependencies, S11, middle): expected `["s11-t07-implement-crud-spec", "s11-t08-write-test-plan", "s11-t09-review-spec", "s11-t10-write-docs", "s11-t11-package-release", "s11-t12-update-endpoints-for-v2"]`, got `["s11-t07-implement-crud-spec", "s11-t08-write-test-plan", "s11-t12-update-endpoints-for-v2"]`; evidence in context 6/6
- **B2 Q03** (decision_provenance, S20, late): expected `["auth_method=JWT bearer tokens (ES384, key s20)@researcher", "auth_method=API key in X-Ops-Key header@planner"]`, got `["auth_method=JWT bearer tokens (ES384, key s20)@unknown", "auth_method=API key in X-Ops-Key header@unknown"]`; evidence in context 2/2
- **B2 Q04** (decision_provenance, S01, early): expected `["acme-docs/s01/04_security_note.md", "acme-docs/s01/05_customer_request.md"]`, got `[]`; evidence in context 0/2
- **B2 Q07** (handoffs, S05, early): expected `["s05-t12-update-endpoints-for-v2", "s05-t07-implement-crud-spec", "s05-t11-package-release"]`, got `["s05-t11-package-release", "s05-t12-update-endpoints-for-v2"]`; evidence in context 2/3
- **B2 Q08** (handoffs, S12, middle): expected `["s12-t03-design-endpoints"]`, got `[]`; evidence in context 0/1
- **B2 Q13** (supersession, S06, early): expected `["s06 build the acme"]`, got `[]`; evidence in context 0/1
- **B2 Q16** (supersession, S02, early): expected `["s02 adopt style guide", "s02 spec approved endpoints"]`, got `["s02 build the acme"]`; evidence in context 0/2
- **B2 Q17** (dependencies, S11, middle): expected `["s11-t07-implement-crud-spec", "s11-t08-write-test-plan", "s11-t09-review-spec", "s11-t10-write-docs", "s11-t11-package-release", "s11-t12-update-endpoints-for-v2"]`, got `[]`; evidence in context 0/6
- **B2 Q18** (dependencies, S16, late): expected `["s16-t10-write-docs", "s16-t11-package-release"]`, got `[]`; evidence in context 0/2
- **B2 Q21** (contradictions, S20, late): expected `["auth_method=JWT bearer tokens (ES384, key s20)", "auth_method=API key in X-Ops-Key header"]`, got `[]`; evidence in context 0/2
- **B2 Q22** (contradictions, S01, early): expected `["auth_method=JWT bearer tokens (RS256, key s01)@researcher", "auth_method=API key in X-Api-Key header@planner"]`, got `[]`; evidence in context 0/2
- **B2 Q23** (contradictions, S07, middle): expected `"acme-docs/s07/05_customer_request.md"`, got `"acme-docs/s07/04_security_note.md"`; evidence in context 0/1
- **B2 Q30** (memory_scope, S15, late): expected `["purpose=REST service to create, tag and search notes (S15)", "api_version=v30", "database=SQL Server 2022", "auth_method=JWT bearer tokens (ES384, key s15)", "auth_method=API key in X-Web-Key header", "release_channel=general availability"]`, got `["purpose=REST service to create, tag and search notes (S15)", "api_version=v30", "release_channel=general availability"]`; evidence in context 3/6
- **B2 Q35** (episodes, S10, middle): expected `2`, got `1`

## Headline

- L2-scale: B0 + claude -p (sonnet) answered 30/36 (83.3%) exactly, 19646 tokens and $0.077 per question.
- L2-scale: B1 + claude -p (sonnet) answered 32/36 (88.9%) exactly, 22010 tokens and $0.087 per question.
- L2-scale: B2 + claude -p (sonnet) answered 23/36 (63.9%) exactly, 4424 tokens and $0.016 per question.
- L2-scale: Plexus (deterministic Cypher) answered 36/36 (100.0%) exactly.
- L2-scale: Plexus beats B0 by 16.7 points.
- L2-scale: Plexus beats B1 by 11.1 points.
- L2-scale: Plexus beats B2 by 36.1 points.

## Plexus changes relative to the 43-question L2 answerer

- Operations whose arguments already name a unique thing (task id, fact label, decision name, subject, source uri) run the unchanged l2 operation with the unchanged statements: decision_facts, decision_fact_agents, decision_sources, handoff_artifacts, handoff_route, handoff_facts, as_of_values, as_of_facts, value_history, decisions_on_fact, superseder, fact_agent, fact_source, fact_scope, blocked_by_failure, direct_dependencies, ready_after, reclaimer, previous_claimer, current_value, scope_leak, episode_agent, remaining_from_source, forgotten_facts.
- Nine operations ask about a whole class (all handoffs to X, all decisions on superseded facts, ...) and are restricted to the sprint named in the question by a Python filter over the rows of the same statements (task ids start with the sprint tag, source uris contain it, episode texts start with it): handoffs_to, handoffs_with_superseded_facts, decisions_on_superseded, decisions_on_forgotten, active_conflicts, active_conflict_agents, reclaimed_tasks, completed_by, episode_count.
- One operation needs one new read-only statement: visible_facts runs queries/l2scale/facts_visible_subject.cypher (l2/facts_visible plus a subject restriction), because the global scope now holds the facts of all 20 sprints.
- No other query was changed; the original plexus_answerer.py and queries/l2/*.cypher are untouched.

## Notes

- LLM cost of the answers reported here: $6.4872 over 108 claude -p calls (0 run in this invocation for $0.0000; 108 re-used from the on-disk cache demo_data/crucible/l2_scale_cache, where each entry is the original call: tokens, cost and latency in the rows are those original measurements, so 'cached: true' means re-scored, not free of cost).
- Each baseline question is one `claude -p` process (max-turns 3, no tools, context on stdin, ANTHROPIC_API_KEY removed); permission_denials and tool use are checked per call and fail the question.
- Scoring rule for the baselines (decided before the first paid call, = the final L2 rule): the model may reason in prose first, but the reply must END with exactly one {"answer": ...} JSON object (no text after it); that object is compared by exact match. `accuracy_whole_reply_json` counts only replies that are nothing but the JSON object.

## Honesty

- L2-scale: exact-match accuracy over script-derived questions (40 generated, 10 families x 4; 36 asked after the pre-registered budget rule) about 20 independent sprints of one team history; one scenario family, one model (sonnet), one run per question; no LLM judge. Ground truth is computed from the per-sprint scenario ledgers, not read back from any arm. Pre-registered in docs/BASELINE.md before the first paid call.
- The history is 20 repetitions of the same synthetic story with varied ids and values. Real histories are messier; sprints here do not interact, which favours retrieval (a question names its sprint and a sprint's records share its tag).
- Every question names exactly one sprint, so competent keyword retrieval can find a sprint's records. Questions that aggregate across sprints (the strongest case for a graph) are NOT in this set.
- Baselines are the same unmodified `claude -p --model sonnet` with no tools at the same 32,000-character cap, shown BM25-ranked chunks/rows (B0, B1) or vector top-12 (B2) selected with the question text. The selectors were written once, before any paid call, and not tuned afterwards.
- Arm P answers with hand-written Cypher per question family (the same operations as the 43-question L2 run, with the sprint scoping listed in the results); that engineering effort is part of what P costs and the baselines get no equivalent helper.
- Reply rule for the baselines is the final L2 rule: prose may precede the reply, which must END with one {"answer": ...} object; the whole-reply-JSON variant is reported next to it.
- B1 and B2 (and B0's task file) keep only a task's final claimer, not the claim history; only B0's per-agent logs and Plexus's CLAIMED edges record who held an expired lease. Recovery questions therefore test what each arm's artifacts actually contain, as configured in L1.
