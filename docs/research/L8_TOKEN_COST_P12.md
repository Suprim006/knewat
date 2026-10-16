# L8 token cost: where the P arm's tokens went, and two fixes (P12)

Branch `p12`, after `docs/research/L8_ROUND_A2_POSTFIX.md`. Question from the A2 results: Plexus used 89,521 tokens per
correct action against 22,190 for plain Claude Code with its own files (B0′), 4×. What drives it, and can it be cut
without losing the recall fix (15/15 history facts) or the write-atomicity fixes?

Everything in §1-§2 is measured without an LLM except the tool-list probe (four one-line `claude -p` calls, $0.44
including a first attempt). §3 is three paid P runs ($4.14). Total spend of this round: **$4.58**.

## 1. Where the tokens went (A2, P arm, 5 seeds, measured)

Tool: `python -m plexus.crucible.l8.token_breakdown --runs plexus/demo_data/crucible/l8_postfix/runs` (commit
`52f18bf`) → `plexus/demo_data/crucible/l8_postfix/token_breakdown-a2.json`. It reads every `claude -p` transcript:
each assistant `message.id` is one API call with its own usage (prompt = input + cache_creation + cache_read). The
first call's prompt is the **prefix** (Claude Code's system prompt + every tool definition + the harness prompt) and is
re-read by every call of the process; the growth between two calls is split across the blocks that arrived in between
(tool requests, tool responses, text) by characters, and a block is charged once per later call that carries it. The
charges add up to the transcripts' total exactly. (The scorer's total is 10% lower: the 15 killed processes have no
`result` event; shares are unaffected.)

| Component (A2, 702 API calls, 30.4 M tokens) | Tokens | Share | Calls | Response size / call |
|---|---|---|---|---|
| **Prefix re-read on every API call** (36,618 tokens per call) | 25.7 M | **84.5%** | | |
| … of which the 45 Plexus tool definitions (28,873 per call, probe §1.3) | 20.3 M | **66.7%** | | |
| … of which Claude Code + file tools + harness prompt (≈ 7,745 per call) | 5.4 M | 17.9% | | |
| `recall` (request 0.02 M, **response 3.6 M**) | 3.63 M | **11.9%** | 118 | 7,713 tokens (14.1 k chars, 19.5 facts) |
| Read / Grep / Glob / Write (file tools) | 0.50 M | 1.6% | 354 | 100-700 |
| assert_fact, start_session, claim_next_task, complete_task, add_source, remember_episode, record_decision, handoff, create_tasks, verify_artifact | 0.56 M | 1.8% | 664 | 70-260 |
| `why`, `impact`, `why_recalled`, staleness tools | 0 | 0% | **0** (never called in L8) | |
| Assistant text + thinking | 0.02 M | 0.1% | | |

For comparison, the prefix per API call is 13,455 tokens for B1 (12 baseline tools) and 7,273 for B0′ (no MCP).

**Round-trip view** (same file, `round_trip`): charging each API call's whole prompt to the tool results that
triggered it shows what one more call of a tool costs, prefix included. Coordination calls dominate because each is one
more re-read of the 36 k prefix: `start_session` 13.3% (110 calls, 36.7 k each), process start 13.2%, `complete_task`
12.7% (48 k each), `Read` 10.5%, `claim_next_task` 10.0%, `recall` 9.0%, `Write` 7.7%, `Grep` 6.9%.

### 1.1 The recall response

By JSON field (share of recall's charged tokens): **`path` 41.9%**, `text` 7.5%, `fact_id` 6.5%, `entity` 4.0%,
`valid_from` 3.6%, `predicate` 3.5%, `verify_state` 3.4%, `value` 3.3%, `valid_to` 3.3%, `maybe_duplicate_of` 3.2%,
`suspect_reason` 2.9%, `activation` 2.6%, `surprise` 2.4%, `status` 2.4%, `suspect_since` 2.4%, `protected` 2.3%, `score`
1.8%, envelope 1.7%, `via` 1.5%. The request side is 0.6%.

What the agents used, checked over all A2 P transcripts: recalled `fact_id`s were passed on 115 times
(`record_decision` 65, `Write` 29, `handoff` 17, `remember_episode` 4); **no id from a `path` (entity, scope, source)
was ever passed to any tool**, and no agent text mentions activation, surprise or validity windows. `text` repeats
entity + predicate + value; `valid_to`, `status`, `via`, `verify_state`, `suspect_*`, `maybe_duplicate_of` held their
default value in nearly every hit.

### 1.2 Did the recall fix's k = 20 / budget 6,000 cause the regression?

Measured, not assumed: Round A P (k = 8) spent 1.93 M tokens on recall (7.0%, 3,789 tokens per response, 9.0 facts);
A2 P (k = 20) 3.63 M (11.9%, 7,713 per response, 19.5 facts). **+1.70 M over 5 runs, ≈ +5.6% of A2's tokens**, which
is about the whole Round A → A2 move in tokens per correct action (85,840 → 89,521, +4.3%). So yes, the recall fix
cost tokens, but it is ~6% of the bill, not the 4× gap: the gap is the prefix.

### 1.3 The tool list, measured exactly

`python -m plexus.crucible.l8.manifest_probe` (one `claude -p` call per variant, prompt "Reply OK", `--max-turns 1`,
same flags as the L8 harness; tool-list tokens = prompt tokens minus the no-MCP variant) →
`plexus/demo_data/crucible/l8_postfix/manifest_probe.json`:

| Variant | Prompt tokens | Plexus tool list |
|---|---|---|
| no MCP server | 5,963 | 0 |
| Plexus at `702501f` (A2 code) | 34,836 | **28,873** |
| this round, `PLEXUS_MCP_SCHEMA=full` | 33,403 | 27,440 |
| this round, default (compact) | 25,840 | **19,877** |

28,873 tokens for 45 tools is ~640 tokens a tool. It is a fixed cost of every API call, independent of what the tools
return. 75 kB of JSON: tool descriptions are 10.9 k characters of it; the rest is per-parameter schema, much of it
pydantic boilerplate (`title` on every field, `maxLength: 20000`, `maximum: 2147483647`, `anyOf [X, null]`, a generic
`outputSchema` per tool) and three parameter descriptions repeated on every tool (`step` 7.5 k characters in total,
`agent_id` 3.5 k, `audit` 2.7 k).

## 2. The fixes (each validated without an LLM first)

### Fix 1: compact recall hits (`460a459`)

`recall` returns, per hit, `fact_id`, `entity`, `predicate`, `value`, `valid_from`, `score` and `by` (the asserting
agent), plus **only the flags that differ from their default** (`verify_state: suspect` with `suspect_since` /
`suspect_reason`, `status`, `valid_to`, `via`, `protected: true`, non-empty `maybe_duplicate_of`, `hop` /
`relation_path`). `detail: "full"` gives the old hit. The set and order of facts is unchanged (same `recall_page`
call; `k = 20`, `budget_chars = 6,000` and the `all` scope stay), so completeness cannot move by construction; the
suspect warning is never trimmed (tested: `test_p7_wiring`, `test_p12_token_fix`).

No-LLM check, `python -m plexus.crucible.l8.recall_bench --detail full|compact` (the bench of A2 §1.4, 5 seeds, the
real tool layer; files `recall_bench-p12tok-{full,compact}.json`):

| | full | compact |
|---|---|---|
| Replay: recalls that returned the fact they asked for | 27 / 36 | 28 / 36 (one ranking tie, run-to-run) |
| Needed history fact found by a recall of its task: S07 / S13 / S20 | 5/5, 5/5, 1/1 | 5/5, 5/5, 1/1 |
| Canonical (1,000 queries) target returned | 1,000 | 1,000 |
| Mean response, replay | 21,422 chars | **5,341 chars (−75%)** |
| Mean response, canonical | 22,867 chars | 5,772 chars |

Why not lower `k` or make it adaptive instead: at compact size, 20 facts cost ~2.5 k tokens in the live runs (§3),
less than the old 8-fact full response (3.8 k). Trimming fields gets the saving without touching the result set the
recall fix's completeness depends on; a smaller or adaptive `k` would need its own completeness measurement and was not
tried (recall is now 5.3% of the bill, the k raise about half of that, it is not where the tokens are).

### Fix 2: compact published tool schemas (`b075927`)

`PlexusServer.list_tools` publishes `compact_schema(input_schema)`: no `title`, no `maxLength` / `minLength` /
`maxItems`, no numeric bound of 10,000 or more and no `minimum: 0`, `anyOf [X, null]` → `X`, no `default: null`, no
`outputSchema`. Kept: every description, type, enum, `required`, `$defs`/`$ref`, small bounds (`k` 1..50, `hops` 0..2)
and non-null defaults. The shared `agent_id`, `step` and `audit` descriptions were shortened (same meaning). Server-side
validation is unchanged: arguments are still validated against the full pydantic model (tested: a 200-character
`agent_id` and `k = 51` are still refused with the one-line error). `PLEXUS_MCP_SCHEMA=full` restores the verbose list.
Measured by the probe: **28,873 → 19,877 tokens per API call (−8,996, −31%)**.

What this does not do: no tool was removed, no tool description was rewritten, and no tool is hidden from a session.

### Not changed, and why

* `why` / `impact` / `why_recalled` payloads: never called in L8, 0 tokens; changing them would not move this
  benchmark.
* Audit overhead (Step / ToolCall / READ edges): graph writes only. The only audit field in responses is
  `tool_call_id` (~50 characters), inside the 70-260-token responses of the write tools: 1.8% of the bill for all of
  them together.
* Duplicate fields across responses: only recall had them (`text` = entity + predicate + value); removed by fix 1.

## 3. Paid sanity check: three P seeds on the fixed code

Same harness, prompts, model alias, seeds and schedules as A2 (`crucible/l8/run.py`, out dir
`plexus/demo_data/crucible/l8_p12tok/`), FalkorDB `plexus-db-66`. Projection before the first run: A2 seed 20261017 cost
$2.09; expected −25-35% → ≈ $1.5, under the $4 stop. Real: $1.42 for seed 20261017, then 20261018 and 20261021 in
parallel ($1.34, $1.38). Scored with the A2 scorer (`score_run`, after the same `redump_p_steps` the report runs).
Compared with the A2 runs of the **same three seeds**:

| Seed | tokens / correct action: A2 → fixed | cost: A2 → fixed | stale actions: A2 → fixed | tasks | history facts | X1 / X2 at write | provenance |
|---|---|---|---|---|---|---|---|
| 20261017 | 95,092 → **64,855** | $2.09 → $1.42 | 3/62 → 6/65 | 16 | 3/3 | yes / yes | 42/42 |
| 20261018 | 86,237 → **63,953** | $1.85 → $1.34 | 3/66 → 3/64 | 16 | 3/3 | yes / yes | 42/42 |
| 20261021 | 92,943 → **65,261** | $1.85 → $1.38 | 5/63 → 4/65 | 16 | 3/3 | yes / yes | 42/42 |
| **Pooled** | **91,300 → 64,688 (−29%)** | $5.79 → $4.14 | 11/191 (5.8%) → 13/194 (6.7%) | 48/48 | **9/9** | 6/6 | 126/126 |

Token breakdown of the three fixed runs (`l8_p12tok/token_breakdown-3seeds.json`): prefix 27,620 tokens per call (was
36,619 for the same seeds), recall response 2,479 tokens (was 7,713) with 20.2 facts per response, recall share 5.3%
(was 11.9%). Total tokens per run 3.8-4.0 M (was 5.4-5.6 M). One agent passed `detail: "full"` once.

**The stale-action count is not better and could be read as slightly worse (13 vs 11 of ~190).** Checked: two of the
three extra stale actions in seed 20261017 are one agent (builder, t07) copying `auth.session_cookie` from a recall into
its spec after the function was deleted; the fact was not suspect in either version (agents are not told to anchor
facts), so the full hit would have carried the same value with the same `verify_state: verified`. The scorer's
post-hoc variant that excludes the x2 brief write and deleted-function tokens gives 4 (fixed) vs 6 (A2). At n = 3 this
is run-to-run noise either way; no mechanism ties it to the fixes, but this round does not show the stale rate is
unchanged, only that it is in A2's per-seed range (1.5-7.9%: fixed 3.1-9.2%, one seed above).

## 4. How much of the 4× is closed

Same three seeds: B0′ 22,910 tokens per correct action, B1 35,064, P A2 91,300 (3.99× B0′), **P fixed 64,688 (2.82×
B0′)**. The fixes close **39% of the P-vs-B0′ gap** (26.6 k of 68.4 k tokens per correct action).

What is left is structural, and it is the tool list: in the fixed runs the 19,877-token Plexus tool list re-read on all
421 API calls is 8.4 M of 13.0 M tokens (65%), ≈ 41.8 k tokens per correct action, which is the whole remaining gap
(41.8 k). Without the tool list P's per-action cost would be about B0′'s: its extra coordination round trips
(`start_session`, `claim_next_task`, `complete_task`) roughly offset B0′'s extra file reading. Reducing it needs a
different kind of fix, out of scope here:

* **Fewer tools per session.** L8's agents called 12 of the 45 tools (`start_session`, `claim_next_task`,
  `complete_task`, `recall`, `assert_fact`, `add_source`, `remember_episode`, `record_decision`, `handoff`,
  `create_tasks`, `verify_artifact`, `fact_history`). Those 12 are 32% of the compact list's characters: an estimated
  ~6.4 k tokens instead of 19.9 k (estimate scaled by characters, not probed), which would put P near 36 k tokens per
  correct action, ≈ 1.6× B0′ and level with B1. It changes what an agent can do (no staleness, lineage or memory tools
  unless asked for), so it is a product decision, not a trim.
* **Shorter tool descriptions** (rewriting 45 docstrings; they steer agent behaviour, so it needs its own A/B).
* **Fewer round trips** (e.g. `claim_next_task` starting the session implicitly): 13% of A2's tokens were the
  `start_session` round trip alone, but it changes the protocol the harness prompts describe.

Billing view, for scale: ~90% of P's raw tokens are prompt-cache reads, billed at a tenth. Cost-weighted tokens per
correct action on the three seeds: B1 6,551, B0′ 7,453, P A2 14,667, **P fixed 10,070 (1.35× B0′)**; dollars per
correct action: B1 $0.018, P fixed $0.023, B0′ $0.026, P A2 $0.032 (P now does more correct actions per seed than B0′:
181 vs 143).

## 5. Not regressed

* History recall: 9/9 history facts in the three paid runs (A2: 15/15 over five); no-LLM bench unchanged (S07 5/5, S13
  5/5, S20 1/1, canonical 1,000/1,000) under both `detail` values; the recall fix's defaults (`all` scope, `k` 20,
  budget 6,000, candidate pool, keyword channel) untouched.
* Write atomicity: the folded task-tool statements and the `verify_fact` marker are untouched; their kill tests
  (`tests/crucible/l6/test_crash_fold_tasks.py`, `test_verify_crash.py`) pass in the full suite; provenance 126/126 in
  the paid runs (with one write in a killed turn, recorded).
* Contradictions surfaced at write: X1 3/3, X2 3/3.
* Tasks: 16/16 on every seed.
