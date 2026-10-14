# Crucible Layer 2: provenance and time questions

43 exact-match questions about one recorded run of the Acme Notes scenario, answered by four arms:

| Arm | Answerer | What it is shown |
|---|---|---|
| **P** | deterministic Cypher (`plexus_answerer.py`, `queries/l2/*.cypher`), no LLM | the tenant graph |
| **B0** | unmodified `claude -p --model sonnet`, no tools | the arm's files (`tasks.json`, `MEMORY.md`, `decisions.jsonl`, `handoffs.jsonl`, `sources.json`, `logs/*.jsonl`), cap 32,000 chars |
| **B1** | same | schema + CSV dump of the SQLite tables, cap 32,000 chars |
| **B2** | same | top-12 retrieved memory chunks (local bge-small), cap 32,000 chars |

## Files

| File | Role |
|---|---|
| `scenario.py` | plays the P3 script on any `CoordinationBackend`, records the ground-truth `Ledger`. `deterministic()` makes the file/SQLite arms byte-reproducible (fixed ids, script clock) so the LLM answer cache can hit |
| `questions.py` | the question families, `build_questions(ledger)` (answers are *derived*), normalisation, `score`, `parse_reply` |
| `plexus_answerer.py` + `queries/l2/*.cypher` | arm P |
| `contexts.py` | what B0 / B1 / B2 show the model, and whether the cap cut anything |
| `llm.py` | `ClaudeRunner`: one `claude -p` process per question, stdin context, strict checks, on-disk cache |
| `run.py` | the CLI: `questions`, `run --mode pilot\|full`, `merge`; builds `results.json` + `report.md` |
| `../../demo_data/crucible/questions.yaml` | the committed question set (regenerate: `python -m plexus.crucible.l2.run questions`; a test fails if it drifts) |
| `../../demo_data/crucible/l2/<run>/` | `results.json`, `report.md`, `B0.context.txt`, `B1.context.txt` |
| `../../demo_data/crucible/l2_cache/<arm>/Qnn-<hash>.json` | every `claude -p` call (reply, usage, cost, latency), keyed by sha256(model, prompt version, context, question) |

## Run

```bash
cd plexus
docker run -d --name plexus-db-78 -p 127.0.0.1:6378:6379 falkordb/falkordb:6.0.2
uv run python -m plexus.crucible.l2.run run --mode pilot --port 6378 --budget-usd 1.5   # 5 questions x B0,B1,B2 (+P)
uv run python -m plexus.crucible.l2.run run --mode full  --port 6378 --budget-usd 8     # all 43; cached answers are free
uv run python -m plexus.crucible.l2.run merge --into path/to/H/results.json --l2 demo_data/crucible/l2/<run>/results.json
PLEXUS_TEST_DB_PORT=6378 uv run pytest tests/crucible/l2 tests/crucible/l3      # no LLM: the CLI is mocked
```

## `results.json` shape (for plexus-view)

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
Ground truth comes from the ledger the script keeps while it runs. The Plexus answerer is checked against it on a live
graph (`tests/crucible/l2/test_plexus_answerer.py`, 43/43).

Not covered: the Procedures family (the backend protocol has no procedure tool); cross-session recall is episodes by
agent (no sessions in the protocol).
