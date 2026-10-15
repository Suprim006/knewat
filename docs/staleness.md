# Staleness: code changes make memories suspect (P7-J, D-011)

Plexus only knows what agents tell it. When Claude Code edits a file but not the fact or doc that describes it, nothing
in the graph changes and recall keeps returning the old fact. Staleness closes that gap **without an LLM**: a client
hashes the changed files, the server marks the facts that depend on them `suspect`, and an agent re-verifies them.
Changing code never makes a fact false, it makes it *suspect*; nothing is deleted and recall still returns suspect facts.

```
 developer machine                                   Plexus server (Docker)                      agent
 -----------------                                   ----------------------                      -----
 git post-commit / Claude PostToolUse hook
   plexus code scan | hook-run   --mark_changed-->   hash differs?  --> Facts ANCHORED_TO it or
   (hash files + Python symbols)                      (CodeAnchor / Source)   DERIVED_FROM its Source
                                                        |  verify_state='suspect', (Change)-[:SUSPECTED]->(Fact)
                                                        v
                                                      decisions at risk + docs to update   ---->  facts_to_verify
                                                                                                    verify_fact(still_true | new_value)
```

## Graph model v1.1 additions (J)

(The names are fixed by the shared P7 contract. They are folded into `docs/graph-model.md` too, which is the single
source the consistency test reads.)

| On | Property | Meaning |
|---|---|---|
| Fact | `verify_state` | `'verified'` (default when absent) or `'suspect'` |
| Fact | `suspect_since` | epoch ms of the first change that made it suspect (0 when absent) |
| Fact | `verified_at` | epoch ms of the last `verify_fact` (0 when absent) |
| Fact | `verify_after` | epoch ms review date (open = `9999999999999`); once passed the fact is suspect too |
| Source | `kind` | now also `code`, `doc`, `external` |
| Source | `content_hash`, `commit` | hash of the file the Source's `uri` names, and the commit that last reported it (written by `mark_changed`) |

| Node | Properties |
|---|---|
| `CodeAnchor` | `id` (`'anc:' + sha1(path#symbol)[:16]`), `repo`, `path` (canonical), `symbol` (`''` = whole file), `hash`, `kind` (`file`/`function`/`class`), `updated_at`, `created_at` |
| `Change` | `id` (`'chg:' + sha1(commit, at, new hashes)[:16]`), `commit`, `at` (event time), `paths` (JSON list of the changed paths), `agent_id`, `created_at` |

Indexes added (range): `CodeAnchor.id`, `CodeAnchor.path`, `Change.id`, `Change.at`, `Fact.verify_state`, `Fact.verify_after`
(the last one is not in the contract list: it makes the review-date branch of the suspect scan a range seek instead of a
scan of every fact).

| Edge | Meaning |
|---|---|
| `(Fact)-[:ANCHORED_TO {at}]->(CodeAnchor)` | the fact is about this file / function |
| `(Source)-[:DESCRIBES {at}]->(CodeAnchor)` | this doc describes this code |
| `(Change)-[:TOUCHED]->(CodeAnchor \| Source)` | the change edited it |
| `(Change)-[:SUSPECTED {at}]->(Fact)` | the change made the fact suspect |
| `(Fact)-[:VERIFIED_BY {at, commit, outcome, evidence}]->(Agent)` | an agent re-checked it (`confirmed` / `changed`); one edge per verification |

A fact is **suspect at time t** if `coalesce(verify_state,'verified') = 'suspect'` OR `coalesce(verify_after, OPEN) <= t`.

Canonical paths (`CodeAnchor.path`, doc `Source.uri`): absolute, `/` separators, upper-case drive letter, no `.`/`..`,
no trailing slash (`C:/repo/app/payments.py`). One helper, `plexus.codescan.paths.canonical_path`, is used by the
client and the server; it is pure string handling, so a Linux container normalises a Windows path the same way.

## How a change is detected (`mark_changed`)

One bounded statement per call (<= 200 entries, <= 2000 facts; `queries/staleness/mark_changed.cypher`).

1. **Changed?** An entry `{path, symbol, new_hash, old_hash}` is changed when the hash stored on its `CodeAnchor` (or,
   for implicit anchoring, on the `Source`'s `content_hash`) differs from `new_hash`. When nothing is stored yet, the
   caller's `old_hash` stands in. **A first sighting without `old_hash` is a baseline**: it is recorded and marks
   nothing. `new_hash = ''` means the file / symbol is gone.
2. **Which facts?** Active facts only: those `ANCHORED_TO` a changed anchor, plus those that reach a `Source` whose
   `uri` is a changed file through `DERIVED_FROM*1..5` (zero effort: the physio graph's `CLAUDE.md` / `README.md`
   facts are covered as soon as the file is baselined). A file-level change also covers the symbol anchors of that file,
   but **only when the call has no symbol entries for it**; the client sends every symbol of a parseable Python file, so
   editing `create()` does not make facts about `refund()` suspect.
3. **Mark.** `verify_state='suspect'`, `suspect_since` (first time only), one `Change` node (only if something changed)
   with `TOUCHED` edges and a `SUSPECTED` edge per fact. Re-running with the same hashes changes nothing and creates no
   `Change`.
4. **Report.** `suspect_fact_ids`, the decisions `BASED_ON` them (<= 50 listed, total exact), and the docs that
   `DESCRIBES` a changed anchor (a doc reported in the same call is not listed).
5. **Truncation.** If more than 2000 facts are affected the call marks 2000, returns `truncated: true` and does **not**
   advance the stored hashes. Calling again with the same arguments (including the returned `at`) continues with the same
   `Change` (its id is derived from commit, `at` and the new hashes) and skips facts it already marked.

## Re-verifying (`verify_fact`)

- `still_true=true`: `verify_state='verified'`, `verified_at=now`, `VERIFIED_BY {outcome:'confirmed'}`. Fine on a fact
  that is not suspect (it refreshes `verified_at`). A passed review date is consumed.
- `still_true=false` needs `new_value`. The existing supersede path (`Engram.assert_fact(supersede=True)`) creates the
  new fact, then one statement (`staleness/backdate`) sets `old.valid_to = new.valid_from =` **the time of the newest
  `Change` that suspected the old fact** (event time), keeps `recorded_at` as the time Plexus learned it (two timelines),
  marks the old fact verified (`VERIFIED_BY {outcome:'changed'}`), and flags the decisions that rested on it
  (`flagged=true`, `flag_reason='fact changed: <id>'`, the `forget_source` convention). The backdate applies only when it
  falls strictly inside the old fact's window, so `valid_to` never moves before `valid_from`. `as_of` before the change
  returns the old value, after it the new one. `evidence` that is an absolute path or a URL becomes (or reuses) a `Source`
  the new fact derives from, which makes it implicitly anchored to that file; any other text is stored on the edge.
- **Known non-atomic path.** `verify_fact(still_true=false)` is two statements: the supersede (`assert_fact`) and then
  `staleness/backdate`. FalkorDB has no multi-statement transaction, and the supersede path is shared with `assert_fact`,
  so it was not rewritten. If the second statement fails (or the process dies between them): the new value is recorded
  and is the current fact (nothing wrong is served), but the old fact keeps `valid_to = <time of the supersede>` instead of
  the time of the code change, stays `verify_state='suspect'` with no `VERIFIED_BY` edge, and the decisions that rested on
  it are **not flagged**. The old fact is no longer current, so it has left `facts_to_verify` and `verify_fact` refuses it
  (`superseded`); there is no automatic repair. The symptoms are findable (`superseded` + `suspect` facts, decisions
  `BASED_ON` them that are not flagged, visible in `why` and the View) and
  `tests/staleness/test_verify.py::test_a_failure_between_the_two_statements_*` pins exactly this state.

Other work lists: `facts_to_verify` (suspect or past review date, ordered by non-flagged decisions that depend on the
fact, then activation (D-012, the fact agents actually use first; each row carries `activation` and `protected`), then
oldest suspicion; with `PLEXUS_FORGETTING=off` the activation step and fields are dropped; `Staleness(rank=...)` replaces
the ordering),
`docs_to_update` (docs describing code that changed after the doc's own last `TOUCHED`), `set_review_date` (for facts no
code change can invalidate: a deployed URL, an account, a client request).

## Using it

All commands run on the developer machine and talk to the server over MCP (`{url}/mcp/t/{tenant}`); defaults:
`--url http://127.0.0.1:8765` (or `PLEXUS_URL`), `--tenant` from `PLEXUS_TENANT`, `--agent code-hook`.

```bash
# once: record the current hashes of the files the graph already knows (Sources / anchors inside the repo).
# Without --paths this reads the tracked paths straight from FalkorDB (FALKORDB_HOST / FALKORDB_PORT).
plexus code baseline --repo C:/work/pv-core-api --tenant physio
plexus code baseline --repo C:/work/pv-core-api --tenant physio --paths README.md app/services/payments.py

# a commit (default HEAD; hashes come from git show REF and REF~1, event time = the commit time)
plexus code scan --repo C:/work/pv-core-api --tenant physio --commit HEAD
# files as they are on disk now
plexus code scan --repo C:/work/pv-core-api --tenant physio --paths app/services/payments.py
```

`scan` prints what became suspect, the decisions at risk and the docs to update.

**Claude Code hook** (after every `Edit` / `Write` / `MultiEdit`):

```bash
plexus code hook-claude --tenant physio       # prints the settings.json fragment; merge it into .claude/settings.json
```

```json
{"hooks": {"PostToolUse": [{"matcher": "Edit|Write|MultiEdit",
  "hooks": [{"type": "command", "timeout": 10,
             "command": "\"C:/.../python.exe\" -m plexus.codescan hook-run --tenant physio --url http://127.0.0.1:8765"}]}]}}
```

`hook-run` reads the event from stdin (`tool_name`, `tool_input.file_path`, `cwd`), hashes that file (and its Python
symbols), calls `mark_changed`, and, only if something became suspect, prints
`{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "Plexus: N memories about payments.py may be stale: ...; call facts_to_verify / verify_fact"}}`.
Claude Code adds `additionalContext` next to the tool result. Schema checked against the hooks reference
(<https://code.claude.com/docs/en/hooks>: "PostToolUse input" for the event, "Add context for Claude" for
`hookSpecificOutput.additionalContext`). It **never fails the edit**: every error (server down, bad JSON, no tenant) is one
stderr line and exit code 0; the whole run has a 5 s deadline. It uses a small stdlib MCP client (`fastclient.py`)
because `import mcp` alone takes about 2 s on a cold Windows machine; `scan` / `baseline` use the `mcp` package client.
Measured on this machine against a local server: 0.4 s for an event it ignores, about 0.5 s end to end including the
`mark_changed` and `facts_to_verify` calls.

**Git hook** (also catches edits made outside Claude Code):

```bash
plexus code hook-git --repo C:/work/pv-core-api --tenant physio   # writes/updates .git/hooks/post-commit
```

It appends a marked block that runs `python -m plexus.codescan scan --commit HEAD || true`, keeps any hook that is
already there, and replaces its own block on a re-run. A failing scan never fails the commit.

## Limits

- **Code links are file level, plus Python functions, classes and methods through `ast`.** Other languages (and Python
  files that do not parse right now) are file level only. A class hash covers its methods, so editing a method also marks
  facts anchored to the class.
- **Hash granularity.** Any change to a function's text (comments included) changes its hash; reordering functions,
  CRLF vs LF, indentation of a nested definition and trailing whitespace do not. A rename shows as a removed symbol plus a
  new one.
- **Commit time has one-second resolution** (`git show --format=%ct`). A fact created in the same second as the commit
  that changed its code cannot be backdated before its own `valid_from`, and keeps `valid_to = now`.
- **One `CodeAnchor` per file the client has reported, and per symbol of each Python file** (<= 190 symbols per file, else
  file level only). Every edited file gets an anchor even if no fact is about it.
- **Case.** Paths are compared byte-for-byte after normalisation (only the drive letter is upper-cased), so a path typed
  with different case on a case-insensitive file system is a different anchor.
- **Implicit anchoring needs the `Source.uri` to be the canonical path** of the file (the physio graph's are) and a
  baseline so that the first edit is a change rather than a first sighting.
- **Detection is only as good as the hooks.** An edit made while no hook runs and no scan is done is noticed at the next
  scan of a later commit (the stored hash differs), not at the moment it happened; its `Change.at` is then the later time.
- `facts_to_verify` ranks at most 5000 suspect ids; `docs_to_update` keeps up to 10 changes per doc.
- The audit rows (`ToolCall`) and Steps record the tools. The View API shows `Change` / `CodeAnchor` nodes, the Fact fields and
  `/verify-queue`, `/docs-to-update` (see `docs/view-api.schema.json`).

## Real run (P7-int): Claude Code verifies a stale memory on a copy of the physio graph

Recording: `plexus/demo_data/recordings/physio-stale-sonnet/` (graph dump, `meta.json`, the prompt and both transcripts).
Setup script: `scripts/p7_real_run_setup.sh`. Model `claude-sonnet-5-5` through `claude -p` (subscription, `env -u
ANTHROPIC_API_KEY`, no `--bare`), `--max-turns 12`, tools `mcp__plexus__*` and `Read` only, 0 permission denials.

What was set up (nothing was written to the compose stack: the graph `plexus_t_byo` (42 facts) was read with `DUMP` from
the compose database, `RESTORE`d and `GRAPH.COPY`-ed to `plexus_t_physio_test` on the private test database):

1. A scratch copy of `pv-core-api` (the original is untouched). The fact "payment gateways: eSewa and Khalti ... Legacy imepay
   is aliased to Khalti ..." was anchored with `anchor_fact` to `normalize_method` in the copy's
   `app/services/payments/gateway.py`, and the README `Source` was linked with `describe_code`. (The task text names
   `create_gateway_payment`; this repo has no such function, the payment gateway routing lives in `gateway.py`.)
2. `plexus code baseline` (1 file, 11 entries, nothing stale), then one edit: `normalize_method` no longer applies the
   `imepay -> khalti` alias. `plexus code scan --paths app/services/payments/gateway.py`:
   `2 changed, 1 memory may be stale; decisions built on them: 3; docs to update: README.md`.
3. One `claude -p` with the prompt in `prompt.txt` (call `facts_to_verify`, read the code, `verify_fact`, `docs_to_update`).

What Claude did (run 2, 5 turns, 21 s, $0.043 notional): `facts_to_verify` (one row, reason `changed in working tree
(.../gateway.py)`) and `docs_to_update` in parallel, `Read` of `gateway.py`, then
`verify_fact(still_true=false, new_value=<the fact with the alias clause corrected>, evidence=<the path>)`. Its summary
named the stale clause, the three flagged decisions, the README and, unprompted, `AGENTS.md` (not registered in Plexus) and a
code comment that does not match the code.

Graph after the run (`plexus demo record`: 340 nodes, 1310 edges): the old fact `superseded`, `valid_to` = the `Change`
time (`1792096666958`), the new fact `active` with `valid_from` = the same instant and `recorded_at` later (two
timelines); `VERIFIED_BY {outcome: 'changed', agent: claude-verifier, evidence: <path>}` on the old fact; 1 `Change`, 1
`SUSPECTED`, 11 `CodeAnchor` (the file and its 10 symbols), 3 decisions flagged `fact changed: <id>`; 0 suspect facts left.

**The first run found a bug.** Run 1 (`transcripts/01-run1-before-fix.jsonl`, $0.17) behaved the same, but `verify_fact`
answered `outcome: changed` with `new_fact_id` equal to the old fact id and `valid_to` still open. `assert_fact` had treated the
corrected text (one clause of a 326-character fact) as a paraphrase duplicate of the old one, so the old text stayed
current while the three decisions were flagged and the fact was marked verified. Fix: `verify_fact` now asserts with the
paraphrase check off (`Engram.assert_fact(dup_threshold=-1)`; an equal normalised value still counts as a confirmation);
`tests/staleness/test_verify.py::test_a_small_correction_of_a_long_fact_is_recorded_not_swallowed_as_a_paraphrase` pins it.
Run 2 is after the fix; the graph was rebuilt from the dump before it.

What this shows and does not show: one real agent, on one planted change, followed the loop with the tools alone and
the result is in the graph as designed. It is a demonstration, not a measurement of how often agents verify well; the
precision/recall of the flagging is in `docs/BASELINE.md` (L5a). The graph is the owner's own project notes (no third-party
data); test accounts mentioned in it are the seeded ones.

