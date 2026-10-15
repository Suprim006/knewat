# Staleness: code changes make memories suspect (P7-J, D-011)

Plexus only knows what agents tell it. When Claude Code edits a file but not the fact or doc that describes it, nothing
in the graph changes and recall keeps returning the old fact. Staleness closes that gap **without an LLM**: a client
hashes the changed files, the server marks the facts that depend on them `suspect`, and an agent re-verifies them.
Changing code never makes a fact false, it makes it *suspect*; nothing is deleted and recall still returns suspect facts.

## Graph model v1.1 additions (J)

(The names are fixed by `.plexus-agents/specs/P7-contract.md`; this section is the documentation of them until they are
merged into `docs/graph-model.md`.)

| On | Property | Meaning |
|---|---|---|
| Fact | `verify_state` | `'verified'` (default when absent) or `'suspect'` |
| Fact | `suspect_since` | epoch ms of the first change that made it suspect (0 when absent) |
| Fact | `verified_at` | epoch ms of the last `verify_fact` (0 when absent) |
| Fact | `verify_after` | epoch ms review date (open = `9999999999999`); once passed the fact is suspect too |
| Source | `kind` | now also `code`, `doc`, `external` |
| Source | `content_hash` | hash of the file the Source's `uri` names (written by `mark_changed`) |

| Node | Properties |
|---|---|
| `CodeAnchor` | `id` (`'anc:' + sha1(path#symbol)[:16]`), `repo`, `path` (canonical), `symbol` (`''` = whole file), `hash`, `kind` (`file`/`function`/`class`), `updated_at`, `created_at` |
| `Change` | `id`, `commit`, `at`, `paths` (JSON list), `agent_id`, `created_at` |

Indexes added (range): `CodeAnchor.id`, `CodeAnchor.path`, `Change.id`, `Change.at`, `Fact.verify_state`.

| Edge | Meaning |
|---|---|
| `(Fact)-[:ANCHORED_TO {at}]->(CodeAnchor)` | the fact is about this file / function |
| `(Source)-[:DESCRIBES {at}]->(CodeAnchor)` | this doc describes this code |
| `(Change)-[:TOUCHED]->(CodeAnchor \| Source)` | the change edited it |
| `(Change)-[:SUSPECTED {at}]->(Fact)` | the change made the fact suspect |
| `(Fact)-[:VERIFIED_BY {at, commit, outcome}]->(Agent)` | an agent re-checked it (`confirmed` / `changed`) |
