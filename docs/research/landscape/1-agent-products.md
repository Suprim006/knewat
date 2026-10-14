# Landscape 1: How AI agent products implement memory and multi-agent state

Graph Hacks / FalkorDB, Track 02. Researched 2026-10-14 from vendor docs. `[inf]` = my inference. `[obs]` = first-hand observation by the Hermes orchestrator today. `[sentiment]` = user complaint, not vendor-documented. The brief listed Hermes docs under "Claude Code"; I treated **Hermes Agent** (Nous Research) and **Claude Code** (Anthropic) as separate products. Windsurf is covered via its current Devin Desktop/Cascade docs.

## 1. Comparison table

E/S/P = episodic/semantic/procedural. n/d = not documented in what I read.

| Product | Memory types | Storage | Update / aging / conflicts | Sharing across agents/sessions | Concurrency | Scoping | Explainability | USP |
|---|---|---|---|---|---|---|---|---|
| **Hermes Agent** | S: MEMORY.md 2,200 + USER.md 1,375 chars ([mem](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)); E: SQLite+FTS5 ([sessions](https://hermes-agent.nousresearch.com/docs/user-guide/sessions)); P: skills ([curator](https://hermes-agent.nousresearch.com/docs/user-guide/features/curator)) | Files + `state.db`; one optional external provider ([providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers)) | Agent add/patch/remove; exact dupes rejected ([mem](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)); skills age active/stale/archived ([curator](https://hermes-agent.nousresearch.com/docs/user-guide/features/curator)); no fact validity [obs] | Frozen snapshot at session start ([files](https://hermes-agent.nousresearch.com/docs/user-guide/which-file-does-what)); subagents return only a summary ([deleg](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation)); Kanban DB across profiles ([kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)) | Two writers on one profile "compound" ([profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)); atomic Kanban claims ([kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)); batch edit failed on stale view [obs] | Per profile ([profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)); global within it [obs] | Readable files; no "why injected" | Self-improving skills; pluggable memory providers |
| **Claude Code** | S: CLAUDE.md + auto-memory (user/feedback/project/reference); P: skills; E: transcripts ([mem](https://code.claude.com/docs/en/memory)) | Markdown in `~/.claude/projects/<project>/memory/`, machine-local ([mem](https://code.claude.com/docs/en/memory)) | Index cap 200 lines/25KB; `modified` timestamp; conflicting rules picked "arbitrarily"; `/doctor prompt-audit` ([mem](https://code.claude.com/docs/en/memory)) | Per git repo, across worktrees; subagent `memory` field ([sub](https://code.claude.com/docs/en/sub-agents)); teams share a task list ([teams](https://code.claude.com/docs/en/agent-teams)) | Team task status can lag ([teams](https://code.claude.com/docs/en/agent-teams)); no memory locking documented | Managed/user/project/local + path rules ([mem](https://code.claude.com/docs/en/memory)) | `/memory`, `/context` list files ([mem](https://code.claude.com/docs/en/memory)) | Layered hierarchy + editable auto-memory |
| **ChatGPT** | S: saved memories; chat-history reference; memory summary ([FAQ](https://help.openai.com/en/articles/8590148-memory-faq)) | OpenAI cloud, per account ([OpenAI](https://openai.com/index/memory-and-new-controls-for-chatgpt/)) | Automatic updates; old system went stale/contradictory ([FAQ](https://help.openai.com/en/articles/8590148-memory-faq)) | Across chats; project chats share within project ([projects](https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt)) | n/d | User, project, Temporary Chat ([OpenAI](https://openai.com/index/memory-and-new-controls-for-chatgpt/)) | Per-response sources + reason, "may not show every factor" ([FAQ](https://help.openai.com/en/articles/8590148-memory-faq)) | Always-on consumer personalisation |
| **Codex** | S/E: generated memory files; rules: AGENTS.md ([agents](https://developers.openai.com/codex/guides/agents-md)) | `~/.codex/memories/`, off by default ([mem](https://learn.chatgpt.com/docs/customization/memories?surface=app)) | Background extraction after idle; secrets redacted; consolidation model ([mem](https://learn.chatgpt.com/docs/customization/memories?surface=app)) | Separate from ChatGPT memory; AGENTS.md chain, 32 KiB cap ([agents](https://developers.openai.com/codex/guides/agents-md)) | n/d | Per machine, per-chat toggle ([mem](https://learn.chatgpt.com/docs/customization/memories?surface=app)) | Inspectable files ([mem](https://learn.chatgpt.com/docs/customization/memories?surface=app)) | Rules (AGENTS.md) split from recall (memories) |
| **Cursor** | P/S via Rules; Memories removed ([forum](https://forum.cursor.com/t/are-my-memories-gone/144057/3)) | `.cursor/rules`, dashboard Team Rules ([rules](https://cursor.com/docs/context/rules)) | Static, human-edited; earlier sources win conflicts ([rules](https://cursor.com/docs/context/rules)) | Team Rules across repos ([rules](https://cursor.com/docs/context/rules)) | n/d | Team > Project > User ([rules](https://cursor.com/docs/context/rules)) | Visible rule files | Versioned, enforceable rules |
| **Windsurf / Devin** | Windsurf: auto Memories + Rules + Skills; Devin: Knowledge (deprecated) | Windsurf local, per workspace ([mem](https://docs.devin.ai/desktop/cascade/memories)); Devin cloud, org/enterprise ([know](https://docs.devin.ai/product-guides/knowledge)) | Devin suggests new/updated Knowledge from chat ([know](https://docs.devin.ai/product-guides/knowledge)) | Devin org-wide, promotable ([know](https://docs.devin.ai/product-guides/knowledge)) | n/d | Windsurf not across workspaces ([mem](https://docs.devin.ai/desktop/cascade/memories)); Devin pin to repo/all ([know](https://docs.devin.ai/product-guides/knowledge)) | Retrieval trigger descriptions; no trace documented | Org Knowledge with triggers and folders |
| **Gemini app** | S/E: past-chat memory, Google apps, instructions ([G](https://support.google.com/gemini/answer/16598623)) | Google account, needs Keep Activity ([G](https://support.google.com/gemini/answer/16598469)) | Correct in chat; delete via chat activity ([G](https://support.google.com/gemini/answer/16598469)) | Cross-chat, personal accounts only ([G](https://support.google.com/gemini/answer/16598469)) | n/d | Per account ([G](https://support.google.com/gemini/answer/16598469)) | Ask "did you use past chats?" ([G](https://support.google.com/gemini/answer/16598469)) | Memory fused with Google apps |
| **OpenClaw** | E: daily notes; S: MEMORY.md/USER.md; prospective intents ([arch](https://docs.openclaw.ai/concepts/memory-architecture)) | Markdown + SQLite index; LanceDB/Honcho plugins ([mem](https://docs.openclaw.ai/concepts/memory)) | Dreaming consolidates; USER.md active/superseded metadata ([dream](https://docs.openclaw.ai/concepts/dreaming), [mem](https://docs.openclaw.ai/concepts/memory)) | Imports Codex/Claude/Hermes memory ([mem](https://docs.openclaw.ai/concepts/memory)) | Plugin state locks ([dream](https://docs.openclaw.ai/concepts/dreaming)); else n/d | Per agent workspace | Session lineage, `memory forget` ([prov](https://docs.openclaw.ai/concepts/memory-provenance)) | Explicit memory lifecycle and provenance |
| **Letta** | Core blocks, recall, archival; MemFS git files ([memfs](https://docs.letta.com/concepts/memfs)) | DB + per-agent git repo ([agents](https://docs.letta.com/v1-sdk/concepts/stateful-agents)) | Self-edit; sleep-time agents reorganise ([blog](https://www.letta.com/blog/sleep-time-compute/)) | Shared blocks across agents ([blocks](https://docs.letta.com/guides/core-concepts/memory/memory-blocks)) | insert safe, replace "mostly", rethink last-writer-wins ([shared](https://docs.letta.com/v1-sdk/memory/shared-memory/)) | Per agent; independent conversations ([agents](https://docs.letta.com/v1-sdk/concepts/stateful-agents)) | ADE shows block changes ([skill](https://github.com/letta-ai/skills/blob/HEAD/letta/letta-api-client/sleeptime.md)); git history | Memory as first-class state; shared blocks |

## 2. Per product

### Hermes Agent
- **USP:** self-improving agent with agent-written skills and swappable memory providers ([llms.txt](https://hermes-agent.nousresearch.com/docs/llms.txt)).
- **Strengths:**
  - Writes are injection-scanned ([mem](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)).
  - Kanban has atomic claims, comments as the inter-agent protocol, and a live-claim guard on completion ([kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)).
  - Providers include Honcho (peer modelling) and Hindsight (knowledge graph, entity resolution) ([providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers)).
- **Documented limits:**
  - Only one external provider at a time ([providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers)).
  - Context files are first-match-wins ([ctx](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files)).
  - The curator tracks views, uses and patches, not success ([curator](https://hermes-agent.nousresearch.com/docs/user-guide/features/curator)).
  - The Kanban REST surface is unauthenticated on the host ([kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)).
- **First-hand [obs]:**
  - (a) Both stores hit their cap and needed manual merging; three near-duplicate profile entries had to be merged by hand.
  - (b) Memory is global, so HRM-backend notes were injected into this project.
  - (c) "Docker won't start" stayed current after it became false.
  - (d) A batched memory edit was rejected all-or-nothing after the entry changed underneath it.
  - (e) Skills work well but have no outcome tracking.
  - (f) Session FTS5 search is not linked to entities or decisions.
  - (g) Subagents are isolated and cannot write memory; their summaries are self-reported; an exported env var leaked between parallel agents; there is no shared structured state.
  - (h) Context files are static and first-match-wins.

### Claude Code
- **USP:** human-written hierarchy plus agent-written, plain-markdown auto-memory ([mem](https://code.claude.com/docs/en/memory)).
- **Strengths:**
  - Typed notes with a `modified` timestamp; topic files load on demand ([mem](https://code.claude.com/docs/en/memory)).
  - Subagents get optional persistent memory and worktree isolation ([sub](https://code.claude.com/docs/en/sub-agents)).
  - Agent teams message each other and share a task list ([teams](https://code.claude.com/docs/en/agent-teams)).
- **Documented limits:**
  - CLAUDE.md is "context, not enforced configuration" ([mem](https://code.claude.com/docs/en/memory)).
  - Auto-memory is not shared across machines ([mem](https://code.claude.com/docs/en/memory)).
  - Teams are experimental: no in-process resume, one team per session, status can lag ([teams](https://code.claude.com/docs/en/agent-teams)).
- **Sentiment:**
  - Rules ignored, especially after compaction ([#26160](https://github.com/anthropics/claude-code/issues/26160)).
  - Compaction re-injects a stale in-memory copy of CLAUDE.md/MEMORY.md ([#92949](https://github.com/anthropics/claude-code/issues/92949)).
  - Skill context lost after compaction ([#13919](https://github.com/anthropics/claude-code/issues/13919)).

### ChatGPT
- **USP:** automatic memory via saved memories plus chat-history reference ([OpenAI](https://openai.com/index/memory-and-new-controls-for-chatgpt/)).
- **Strengths:**
  - Best consumer explainability found: per-response memory sources with a reason ([FAQ](https://help.openai.com/en/articles/8590148-memory-faq)).
  - Project-scoped memory ([projects](https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt)).
- **Documented limits:**
  - The summary "will not include everything" ([FAQ](https://help.openai.com/en/articles/8590148-memory-faq)).
  - Full deletion means removing every source: chats, files, summary, connected apps ([FAQ](https://help.openai.com/en/articles/8590148-memory-faq)).
- **Sentiment:**
  - Stale items shape answers ([ZDNet](https://zdnet.com/article/chatgpts-new-memory-upgrade-can-also-worsen-answers)).
  - Remembers the user, not project state or rejected approaches ([forum](https://community.openai.com/t/chatgpt-s-memory-is-failing-serious-users-this-needs-to-be-fixed/1403753/2)).
  - Third-party audit lists a confirmed Nov 2025 missing-memories incident ([audit](https://cameron.stream/knowledge/ai-memory-complaint-inventory)).

### Codex
- **USP:** AGENTS.md for rules; memories are "a helpful recall layer, not the only source" ([mem](https://learn.chatgpt.com/docs/customization/memories?surface=app)).
- **Strengths:**
  - Clear discovery chain with per-directory override ([agents](https://developers.openai.com/codex/guides/agents-md)).
  - Controls: rate-limit guard, exclude chats that used MCP or web search ([mem](https://learn.chatgpt.com/docs/customization/memories?surface=app)).
- **Documented limits:**
  - Off by default, local, delayed generation ([mem](https://learn.chatgpt.com/docs/customization/memories?surface=app)).
  - 32 KiB AGENTS.md cap ([agents](https://developers.openai.com/codex/guides/agents-md)).
  - Multi-agent sharing: n/d.
- **Sentiment:** background inference consumes quota ([audit](https://cameron.stream/knowledge/ai-memory-complaint-inventory)).

### Cursor
- **USP:** versioned, scoped, team-enforceable rules ([rules](https://cursor.com/docs/context/rules)).
- **Strengths:** Team > Project > User precedence with glob scoping ([rules](https://cursor.com/docs/context/rules)).
- **Documented limits:**
  - Models "don't retain memory between completions" ([rules](https://cursor.com/docs/context/rules)).
  - Staff: Memories "intentionally removed starting from version 2.1.x" ([forum](https://forum.cursor.com/t/are-my-memories-gone/144057/3)), but old ones still leaked into context with no UI ([forum](https://forum.cursor.com/t/cant-clear-memories/148254/2)).
- **Sentiment (secondary):** the old beta was account-tied, not project-tied, and did not persist in dev containers ([archcore](https://archcore.ai/blog/cursor-memories-removed)).

### Windsurf / Devin
- **USP:** Windsurf splits Memories, Rules, Workflows and Skills ([docs](https://docs.devin.ai/desktop/cascade/memories)); Devin has org-wide trigger-recalled Knowledge ([know](https://docs.devin.ai/product-guides/knowledge)).
- **Strengths:**
  - Rule activation modes control context cost ([docs](https://docs.devin.ai/desktop/cascade/memories)).
  - Knowledge has folders, per-user toggles, repo pinning and enterprise promotion ([know](https://docs.devin.ai/product-guides/knowledge)).
- **Documented limits:**
  - Auto memories are workspace-local and uncommitted ([docs](https://docs.devin.ai/desktop/cascade/memories)).
  - They apply only to legacy Cascade, not the Devin Local agent ([docs](https://docs.devin.ai/desktop/cascade/memories)).
  - Knowledge is deprecated in favour of Skills ([know](https://docs.devin.ai/product-guides/knowledge)).
  - The vendor recommends Rules or AGENTS.md over auto-memory ([docs](https://docs.devin.ai/desktop/cascade/memories)).
  - Multi-Devin shared state: not read.

### Gemini app
- **USP:** past-chat memory plus connected Google apps ([G](https://support.google.com/gemini/answer/16598623)).
- **Strengths:** on/off switch; ask whether past chats were used ([G](https://support.google.com/gemini/answer/16598469)).
- **Documented limits:**
  - Personal accounts, 18+, Keep Activity on ([G](https://support.google.com/gemini/answer/16598469)).
  - Deleting means deleting source chats and disconnecting apps ([G](https://support.google.com/gemini/answer/16598469)).
  - "Saved info" is not the current name in the pages I read; the instructions page was not read; agent-to-agent sharing: n/d.

### OpenClaw
- **USP:** "no hidden state"; tiered files with gated promotion and provenance ([arch](https://docs.openclaw.ai/concepts/memory-architecture)).
- **Strengths:**
  - Dreaming plus a human-review surface ([dream](https://docs.openclaw.ai/concepts/dreaming)).
  - Lineage-based `memory forget` ([prov](https://docs.openclaw.ai/concepts/memory-provenance)).
  - Active-memory sub-agent and standing intents ([active](https://docs.openclaw.ai/concepts/active-memory)).
- **Documented limits:**
  - Memory "does not enforce policy" ([mem](https://docs.openclaw.ai/concepts/memory)).
  - Over-budget MEMORY.md is truncated in context ([mem](https://docs.openclaw.ai/concepts/memory)).
  - Purge is per session; mixed-lineage entries are removed whole ([prov](https://docs.openclaw.ai/concepts/memory-provenance)).
  - Flat retrieval is weaker on temporal and multi-session questions ([active](https://docs.openclaw.ai/concepts/active-memory)).

### Letta
- **USP:** stateful agents; shared blocks as a coordination primitive ([blocks](https://docs.letta.com/guides/core-concepts/memory/memory-blocks)).
- **Strengths:**
  - Sleep-time agents ([blog](https://www.letta.com/blog/sleep-time-compute/)).
  - MemFS gives git history and worktree-based concurrent memory writers ([memfs](https://docs.letta.com/letta-code/memfs)).
  - Candid concurrency guidance ([shared](https://docs.letta.com/v1-sdk/memory/shared-memory/)).
- **Documented limits:**
  - Blocks "may be deprecated" in favour of MemFS ([shared](https://docs.letta.com/v1-sdk/memory/shared-memory/)).
  - Rethink loses updates under concurrency ([shared](https://docs.letta.com/v1-sdk/memory/shared-memory/)).
  - No vector index in MemFS by default ([memfs](https://docs.letta.com/concepts/memfs/index.md)).

## 3. Gaps a FalkorDB-based system could fill

FalkorDB features assumed from the brief: property graph, Cypher, graph per tenant, vector + full-text indexes, parallel reads, atomic single-query writes. All fixes below are [inf].

1. **Temporal validity / supersession.** Hermes [obs], ChatGPT ([ZDNet](https://zdnet.com/article/chatgpts-new-memory-upgrade-can-also-worsen-answers)), Claude (only `modified`, [mem](https://code.claude.com/docs/en/memory)). OpenClaw does it in prose ([mem](https://docs.openclaw.ai/concepts/memory)). Fix: `SUPERSEDES` edges with `valid_from`/`valid_to`; default "current only" query.
2. **Entities and decisions linked to episodes.** Hermes sessions are FTS5 only [obs]; OpenClaw flat retrieval ([active](https://docs.openclaw.ai/concepts/active-memory)). Fix: `Session-[:MENTIONS]->Entity`, `Decision-[:MADE_IN]->Session`; multi-hop traversal.
3. **Scoped memory with controlled inheritance.** Hermes is global in a profile [obs]; Claude is per repo, machine-local ([mem](https://code.claude.com/docs/en/memory)); Windsurf per workspace ([docs](https://docs.devin.ai/desktop/cascade/memories)). Fix: graph per tenant plus `Scope`/`Project` nodes so queries pull the active project and declared shared scopes.
4. **Atomic shared blackboard.** Hermes subagents share only files [obs]; Claude teams lag and are single-session ([teams](https://code.claude.com/docs/en/agent-teams)); Letta rethink loses updates ([shared](https://docs.letta.com/v1-sdk/memory/shared-memory/)). Fix: single-query atomic writes with a version predicate, plus parallel reads.
5. **Fact-level provenance and "why recalled".** ChatGPT's view is partial ([FAQ](https://help.openai.com/en/articles/8590148-memory-faq)); Claude `/memory` lists files only; OpenClaw lineage is per session ([prov](https://docs.openclaw.ai/concepts/memory-provenance)). Fix: `DERIVED_FROM` and `RECALLED_IN` edges; "why" returns a subgraph.
6. **Precise forgetting.** ChatGPT and Gemini need multi-source deletion ([FAQ](https://help.openai.com/en/articles/8590148-memory-faq), [G](https://support.google.com/gemini/answer/16598469)); OpenClaw drops whole entries ([prov](https://docs.openclaw.ai/concepts/memory-provenance)). Fix: traverse `DERIVED_FROM` from a source and cascade delete or flag for recompute.
7. **Caps on always-injected memory.** Hermes 2,200/1,375 chars ([mem](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)); Claude 200 lines/25KB ([mem](https://code.claude.com/docs/en/memory)); Windsurf 6k/12k chars ([docs](https://docs.devin.ai/desktop/cascade/memories)). Fix: top-k retrieval mixing vector, full-text and graph proximity, so store size is decoupled from prompt budget.
8. **Duplicate and contradiction detection at write time.** Hermes rejects only exact dupes ([mem](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)) and near-dupes built up [obs]; Claude may pick one of two conflicting rules arbitrarily ([mem](https://code.claude.com/docs/en/memory)). Fix: vector-similar candidates, then `DUPLICATES`/`CONTRADICTS` edges and a merge step.
9. **Procedural memory with outcomes.** Hermes curator counts usage only ([curator](https://hermes-agent.nousresearch.com/docs/user-guide/features/curator)); Claude skills lost after compaction ([#13919](https://github.com/anthropics/claude-code/issues/13919)). Fix: `Skill-[:USED_IN]->Run-[:RESULTED_IN]->Outcome`; success rate and staleness.
10. **Verifiable handoffs.** Hermes subagent summaries are self-reported [obs]; Kanban completion summaries cap at 400 chars ([kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban)); Claude task status lags ([teams](https://code.claude.com/docs/en/agent-teams)). Fix: `Task`/`Run`/`Artifact` nodes with `VERIFIED_BY` edges so the parent checks facts, not prose.
11. **Tool-neutral shared memory.** OpenClaw copies markdown from Codex, Claude and Hermes into import folders ([mem](https://docs.openclaw.ai/concepts/memory)); Cursor users add MCP servers ([archcore](https://archcore.ai/blog/cursor-memories-removed)). Fix: one graph over MCP, with `Source` nodes tagging origin.
12. **Concurrent multi-writer memory without an owner.** Hermes warns against two writers ([profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)); Letta says "designate one owner" ([shared](https://docs.letta.com/v1-sdk/memory/shared-memory/)). Fix: transactional writes plus parallel reads.

**What a graph does not give for free [inf]:** human-diffable plain files (Claude, OpenClaw, Letta MemFS), git-style history and merge, zero-infrastructure setup. A credible design exports the graph to markdown for review and keeps temporal edges as version history.

## 4. Source quality
- Primary: vendor docs and help centres.
- Secondary/sentiment: GitHub issues, OpenAI forum, ZDNet, archcore, cameron.stream.
- Not verified: Gemini instructions page, Devin multi-agent sharing, Codex multi-agent features, Cursor automation memories.
