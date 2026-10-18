# Crucible Layer 2: provenance and time questions

43 exact-match questions about one recorded run of the Acme Notes scenario, answered by four arms:

| Arm | Answerer | What it is shown |
|---|---|---|
| **P** | deterministic Cypher (`knewat_answerer.py`, `queries/l2/*.cypher`), no LLM | the tenant graph |
| **B0** | unmodified `claude -p --model sonnet`, no tools | the arm's files (`tasks.json`, `MEMORY.md`, `decisions.jsonl`, `handoffs.jsonl`, `sources.json`, `logs/*.jsonl`), cap 32,000 chars |
| **B1** | same | schema + CSV dump of the SQLite tables, cap 32,000 chars |
| **B2** | same | top-12 retrieved memory chunks (local bge-small), cap 32,000 chars |

## Files

| File | Role |
|---|---|
| `scenario.py` | plays the P3 script on any `CoordinationBackend`, records the ground-truth `Ledger`. `deterministic()` makes the file/SQLite arms byte-reproducible (fixed ids, script clock) so the LLM answer cache can hit |
| `questions.py` | the question families, `build_questions(ledger)` (answers are *derived*), normalisation, `score`, `parse_reply` |
| `knewat_answerer.py` + `queries/l2/*.cypher` | arm P |
| `contexts.py` | what B0 / B1 / B2 show the model, and whether the cap cut anything |
| `llm.py` | `ClaudeRunner`: one `claude -p` process per question, stdin context, strict checks, on-disk cache |
| `run.py` | the CLI: `questions`, `run --mode pilot\|full`, `merge`; builds `results.json` + `report.md` |
| `../../demo_data/crucible/questions.yaml` | the committed question set (regenerate: `python -m knewat.crucible.l2.run questions`; a test fails if it drifts) |
| `../../demo_data/crucible/l2/<run>/` | `results.json`, `report.md`, `B0.context.txt`, `B1.context.txt` |
| `../../demo_data/crucible/l2_cache/<arm>/Qnn-<hash>.json` | every `claude -p` call (reply, usage, cost, latency), keyed by sha256(model, prompt version, context, question) |

## Run

```bash
cd knewat
docker run -d --name knewat-db-78 -p 127.0.0.1:6378:6379 falkordb/falkordb:6.0.2
uv run python -m knewat.crucible.l2.run run --mode pilot --port 6378 --budget-usd 1.5   # 5 questions x B0,B1,B2 (+P)
uv run python -m knewat.crucible.l2.run run --mode full  --port 6378 --budget-usd 8     # all 43; cached answers are free
uv run python -m knewat.crucible.l2.run merge --into path/to/H/results.json --l2 demo_data/crucible/l2/<run>/results.json
KNEWAT_TEST_DB_PORT=6378 uv run pytest tests/crucible/l2 tests/crucible/l3      # no LLM: the CLI is mocked
```

## `results.json` shape (for knewat-view)

Same envelope as `crucible/results.py` (`schema_version` 1, `kind` "crucible-results", `run`, `environment`, `config`,
`arms`, `layers`, `summary`, `honesty`). The L2 numbers are in **`layers["L2"]`** (capital L, like `L1`/`L4`);
`run.layers` lists `"L2"`; `summary.l2_accuracy_pct` is `{arm: pct}` and `summary.headline` gets L2 lines.
`merge` adds all of this to an existing H file.

```text
layers.L2 = {
  title, mode: "pilot"|"full", model: "sonnet", model_ids: ["claude-sonnet-5-5"],
  context_budget_chars: 32000, b2_top_k: 12, budget_usd,
  question_set: {path, sha256, total, asked, ids: [..]},
  scenario: {subject, agents, tasks, decisions, handoffs, facts, episodes, sources, supersedes, conflicting_pairs,
             reclaims, forgotten_facts, marks},
  families: {<family>: {title, n}},              # decision_provenance, handoffs, time_travel, supersession,
                                                 # dependencies, contradictions, recovery, memory_scope, episodes, forgetting
  arms: {                                        # keys: B0, B1, B2, P (any subset)
    <arm>: {
      answerer: str, completed: bool,            # false when the budget cap stopped the arm early
      accuracy: {correct, total, pct},           # exact match; THE headline number
      accuracy_whole_reply_json: {correct, total, pct},   # stricter: the reply must be nothing but the JSON object
      by_family: {<family>: {correct, total, pct}},
      errors: int, unparseable: int,
      reply_format: {json_only, prose_then_json, unparseable, call_failed} | null (arm P),
      usage: {llm_calls, calls_run_live, calls_from_cache, input_tokens, output_tokens,
              cache_read_input_tokens, cache_creation_input_tokens, total_tokens, tokens_per_question,
              cost_usd, cost_per_question_usd, latency_ms: {median, p95, total},
              server_ms: {median, total}, statements          # arm P only
             },
      context: {chars_median, chars_max, artifact_chars, questions_truncated}   # baselines only
      questions: [ {id, family, correct, expected, got, error, tokens, cost_usd, latency_ms, cached,
                    context_chars, artifact_chars, truncated, context_sha256, model, num_turns, reply, reply_format,
                    usage: {..}, retrieved: [..]|null,         # baselines
                    server_ms, statements                       # arm P
                   } ]
    } },
  summary: {accuracy_pct: {arm: pct}, tokens_per_question: {arm: n}, cost_usd: {arm: usd}, latency_ms_median: {arm: ms}},
  notes: [str]
}
```

`expected` / `got` are JSON lists (sets, compared order-insensitively after normalisation), strings, an integer or
`"yes"`/`"no"`. `tokens` is the sum of the four usage counters (so cache reads/creation count); `cost_usd` is the
CLI's own `total_cost_usd`. Rows served from the cache keep the cost and latency of the call that produced them.

## What the questions are

`scenario.py` replays the P3 turn order (`demo_data/recordings/acme-scripted/meta.json` is pinned by a test) and adds
three things the P3 script does not do, because BASELINE §2 asks for them: the poison fault is on (a forum post
asserts `database=MongoDB 4`, a decision is taken on it, its source is forgotten), the builder records one more
decision at t06 (six in total), and two project-scoped facts exist for the scope-isolation questions.
Ground truth comes from the ledger the script keeps while it runs. The Knewat answerer is checked against it on a live
graph (`tests/crucible/l2/test_knewat_answerer.py`, 43/43).

Not covered: the Procedures family (the backend protocol has no procedure tool); cross-session recall is episodes by
agent (no sessions in the protocol).

## L2 at scale (`scale_*.py`)

20 sprints of the Acme story in one tenant per arm (history 16.6x / 10.4x the 32k cap for B0 / B1), 40 questions (10 families x 4, one named sprint each), BM25 / vector context selection inside the same 32k cap. Pre-registered in `docs/BASELINE.md` ("L2-scale (pre-registered)" + amendments). The original L2 files above are unchanged except `llm.py`, whose runner takes optional `conventions` / `prompt_version` (defaults keep the L2 cache keys).

| File | Role |
|---|---|
| `scale_scenario.py` | `Sprint` (tag, ids, varied values), `play_scale(backend, k)`: k sprints on one clock, one `Ledger` per sprint |
| `scale_questions.py` | the 40 question slots per sprint, the sprint assignment rule (`assign_sprints`, seed 20261015), YAML dump/load |
| `scale_contexts.py` | `Bm25`, `b0_scale_context`, `b1_scale_context` (B2 reuses `contexts.B2Index`) |
| `scale_knewat.py` + `queries/l2scale/` | `ScaleKnewatAnswerer`: the L2 answerer with sprint scoping for 9 class-wide ops and one new statement (`visible_facts`) |
| `scale_run.py` | CLI: `questions`, `run --mode pilot\|full`; writes `demo_data/crucible/l2_scale/<run>/{results.json,report.md,contexts/<arm>/Qnn.txt}`; cache in `l2_scale_cache/` |

```bash
cd knewat
docker run -d --name knewat-db-66 -p 127.0.0.1:6366:6379 falkordb/falkordb:6.0.2
env -u ANTHROPIC_API_KEY uv run python -m knewat.crucible.l2.scale_run run --mode pilot --port 6366 --budget-usd 2
env -u ANTHROPIC_API_KEY uv run python -m knewat.crucible.l2.scale_run run --mode full  --port 6366 --budget-usd 6   # 36 questions (FULL_DROPPED_IDS removed by the budget rule)
KNEWAT_TEST_DB_PORT=6366 uv run pytest tests/crucible/l2      # no LLM: the CLI is mocked
```

### `layers["L2_scale"]` shape

Same envelope as `L2` (`schema_version`, `kind`, `run` with `layers: ["L2_scale"]`, `environment`, `config.l2_scale`, `arms`, `layers`, `summary.l2_scale_accuracy_pct`, `honesty`). `layers.L2_scale`:

```text
{ title, mode, model, model_ids, context_budget_chars, b2_top_k, budget_usd,
  history: {sprints, scenario: {tasks, decisions, handoffs, facts, ...}, artifact_chars: {B0,B1,B2},
            artifact_chars_over_budget: {arm: x_cap}, strata: {early|middle|late: [sprint numbers]}},
  retrieval: {B0, B1, B2: text, bm25: {k1, b, query}},
  question_set: {path, sha256, total, asked, ids, sprints: {id: "S07"}, seed},
  families: {<family>: {title, n}},
  arms: { <B0|B1|B2|P>: { same as L2 (answerer, completed, accuracy{correct,total,pct,wilson95_pct}, accuracy_whole_reply_json,
           by_family, errors, unparseable, reply_format, usage, context, questions[]),
           by_stratum: {early|middle|late: {correct,total,pct}},
           failure_analysis (baselines): {wrong, call_failed, unparseable, wrong_with_all_evidence_in_context,
                                          wrong_with_partial_or_no_evidence_in_context,
                                          median_share_of_shown_lines_from_the_asked_sprint},
           questions[i] adds: sprint, stratum, shown_units, shown_lines, shown_lines_with_sprint,
                              evidence_in_context: {found,total}|null } },
  summary, knewat_changes: [str], notes: [str] }
```
`evidence_in_context` is a diagnostic (do all words of each expected item occur anywhere in the shown context), never a score.
