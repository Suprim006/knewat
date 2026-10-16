# Demo video script (target 2:50, hard limit 3:00)

Track 02: Agent Memory and Coordination. Nine beats from `docs/PLAN.md` P6, plus the P7 beat (memory that notices change, forgetting). Narration is at most 25 words per beat, so
the voice-over runs about 80 seconds and the screen carries the rest. Every id below was read from a replay of the real
recording `acme-claude-sonnet` (`plexus demo replay acme-claude-sonnet --tenant demo`: 247 nodes, 708 edges, 83 steps,
three unmodified Claude Code agents, Sonnet). Ids are copy-pasteable into the View (`/why/<id>`) and the API.

## Before recording

1. `docker compose up -d --wait --build`, then `docker compose run --rm plexus-cli demo replay acme-claude-sonnet --tenant demo` and the same with `acme-scripted --tenant demo_scripted` and `physio-stale-sonnet --tenant physio_stale` (beat 7 uses the physio replay; the public site has the two Acme tenants).
2. Open the View on http://localhost:5180 (or `<RENDER_URL>`), tenant `demo`. Open the FalkorDB Browser http://localhost:3000, graph `plexus_t_demo`, in a second tab. Have a terminal in the repo root.
3. Pre-open: `/why/d6cdfc22-7653-43dc-a025-31167e8ae048`, the Time Machine, the Results page scrolled to "L2 at scale", and the Verify page of `physio_stale`. For beat 7 have `plexus/demo_data/recordings/physio-stale-sonnet/transcripts/02-run2-after-fix.jsonl` open (or `docs/staleness.md` "Real run"), and the hook output line from `docs/staleness.md`.
4. Rehearse once: the Flow replay and the ablation command each take a few seconds; cut, do not wait.

## Recording ids (tenant `demo`)

| Thing | Value |
|---|---|
| Agents | `planner`, `researcher`, `builder` |
| Builder's task when it dies | `t03-design-endpoints` (claimed at step 16, last call = `recall` at step 17) |
| Who reclaims it | `researcher`, `claim_next_task` at step 19, edge `CLAIMED {reclaimed_from: 'builder'}` |
| v1 fact (superseded) | `666d2f62-d330-4ac4-9a3b-db0b76efa904` `api_version = v1` |
| v2 fact (active) | `41b8a3e6-11c5-4338-8ef2-613e74bda2b7` `api_version = v2`, asserted by `researcher` at step 27 |
| Decision "build against v1" | `6fcb6a65-be96-4c16-b0e9-3c49a688e388` (step 13, rests on the now-superseded v1 fact) |
| Decision "Adopt API v2" | `d6cdfc22-7653-43dc-a025-31167e8ae048` (planner, step 31) |
| Contradiction | `27ed13ad-13bd-473d-ac0f-36d048f899b0` `auth_method = Long-lived API key in X-Api-Key header` (planner, step 50, customer request) `CONTRADICTS` `608a66f1-056e-47fb-ad32-d32c9fd5fbcf` `JWT bearer tokens (RS256)` (researcher, step 44, security note) |
| Newest decision | `94c89d80-3135-4187-93b4-61d423f2b510` "Approve the CRUD spec on API v2 ..." (also `/why/latest`) |
| Source of the v2 fact | `acme-docs/06_api_style_guide_v2.md` (`b668c0e4-0a23-43df-ab76-618a2d0f9631`) |

## The nine beats

| # | Time | On screen (exact action) | Narration (≤ 25 words) |
|---|---|---|---|
| 1 | 0:00-0:12 | README top in the browser, then the Claude Code terminal. Point at the one-line pitch and "Track 02". Cut to the View header with tenant `demo` selected. | "Agents remember in text files and share task lists, so nobody can ask why a decision was made. Plexus keeps memory in one FalkorDB graph." |
| 2 | 0:12-0:30 | View → **Flow**, tenant `demo`, press replay at 4×. Events scroll: step 1 `planner start_session`, step 2 `create_tasks`, step 4 `researcher claim_next_task`, steps 7-8 `assert_fact`. Click step 13 `record_decision`: the panel shows the Cypher (`relay/record_decision`) and the mini-graph of the nodes it created. | "Three real Claude Code agents, replayed. Every tool call is a node with edges to what it created. This one wrote a decision." |
| 3 | 0:30-0:48 | Still **Flow**. Scrub to step 16: `builder claim_next_task` (task `t03-design-endpoints`), step 17: `recall`, then nothing from the builder. Step 19: `researcher claim_next_task`. Switch to the FalkorDB Browser and run `MATCH (a:Agent)-[c:CLAIMED]->(t:Task) WHERE c.reclaimed_from <> '' RETURN a.id, t.id, c.reclaimed_from`. Result: `researcher, t03-design-endpoints, builder`. | "We killed the builder mid-task. Its lease expired, the researcher reclaimed t03, and the graph keeps the evidence: reclaimed from builder." |
| 4 | 0:48-1:05 | View → **Explorer**, tenant `demo`, filter to `Fact`, `Decision`, `Source`. Click fact `666d2f62` (`api_version v1`, status superseded) → `SUPERSEDES` edge from `41b8a3e6` (`v2`). Then click `27ed13ad` (API key) and its `CONTRADICTS` edge to `608a66f1` (JWT); the side panel shows the asserting agents `planner` and `researcher`. | "Version two replaced version one: the old fact is closed, not deleted. Two agents disagreed on authentication; the conflict was flagged at write time." |
| 5 | 1:05-1:22 | View → **Time Machine**, agent `builder`. Slider at step 17: reads `api_version = v1` (shown superseded today). Drag to step 38: reads `api_version = v2`, valid, wrote `t12-update-endpoints-for-v2` and a handoff. | "What did the builder know at step 17? Version one. At step 38? Version two. Time travel is one graph query." |
| 6 | 1:22-1:40 | View → **Why**, open `/why/d6cdfc22-7653-43dc-a025-31167e8ae048` ("Adopt API v2 ..."). Trace: decision → v2 fact `41b8a3e6` → asserted by `researcher` → step → source `06_api_style_guide_v2.md`, and the `SUPERSEDES` link to v1. Counts on screen: 1 fact, 2 agents, 1 source, 2 steps. | "Why v2? The decision rests on one fact, asserted by the researcher from the v2 style guide, superseding v1. A path, not a guess." |
| 7 | 1:40-2:05 | Tenant `physio_stale` (the replayed real run on a copy of a real project's memory). Terminal: an edit to `gateway.py`, then the Claude Code hook prints "Plexus: 1 memory about gateway.py may be stale". View → **Verify**: the payment-gateway fact ⚠ suspect, "changed in working tree", 3 decisions at risk, README under "Docs to update". Cut to the Claude Code transcript: `facts_to_verify` → `Read gateway.py` → `verify_fact(still_true=false, …)`. Back in **Explorer**, click the new fact: the panel shows the old one superseded with `valid_to` = the change time, and **Memory strength** (activation, surprise 0.6, protected). | "Code changed, the doc didn't. The hook flags the memory, Claude re-verifies, the old fact closes at the change time. Unused memories fade." |
| 8 | 2:05-2:28 | Tenant selector: switch `demo` → `demo_scripted`; counts change (199 nodes, 581 edges). Terminal: `curl <RENDER_URL>/api/demo_scripted/why/d6cdfc22-7653-43dc-a025-31167e8ae048` → `404`. Then View → **Results**: L1 table (all four arms 0 violations), "L2 at scale" P 36/36, B1 32, B0 30, B2 23 with "P vs B1 p = 0.125", the L4 callout "fastest median claim: SQLite", and the L5 lines: staleness "symbol anchors 100% / 100%", forgetting "floor 0.5 failed, 0.9 confirmed". | "Each tenant is its own graph; nothing leaks. Honestly: all backends are correct, SQLite claims faster, and our first forgetting default failed its own test." |
| 9 | 2:28-2:50 | Terminal: `docker compose run --rm plexus-cli demo ablation --tenant demo`. Table appears: `why(decision)` works vs BROKEN, `knew_at` BROKEN, `dependency-aware claim` BROKEN, controls work; last lines "6 of 6 edge-dependent features break; 2 of 2 controls are unaffected". Flash `<RENDER_URL>` and the `team_` bring-your-own-agent line. | "Cut four edge types and six of six features break; the controls don't. The graph does the work. Try it with your own agent." |

## Notes for the recording

- **Step numbers.** `PLAN.md` imagined "what did the builder know at step 12". In the real run the builder first acts at step 15 (starts a session), claims at 16 and reads at 17, so the video uses **17 → 38**. Step 12 is the planner's read of v1 (`/api/demo/step/12`).
- **Beat 2 is a replay of a recorded real run**, not a live LLM call. Say "replayed" (the narration does). If you want live action instead, open Flow on tenant `live` and run `docker compose run --rm plexus-cli demo live --scripted --tenant live --speed 4` (scripted agents, 67 steps, builder killed at 15, v2 at 20); the ids above then differ, so re-read them from that tenant.
- **Beat 7 (staleness) is a replay** of the real run `physio-stale-sonnet` (Sonnet, 5 turns, $0.04; `docs/staleness.md` "Real run"). Its ids are in that recording, not in `acme-claude-sonnet`; the Verify page shows them by name, so none need to be typed. The forgetting half is the **Memory strength** panel (`docs/forgetting.md`); don't claim it improves accuracy (L5b: same recall@5 within 2 points, less noise).
- **Beat 8 on the public site:** `demo_scripted` is the second public tenant. The 404 text is the API's; `demo*` tenants refuse MCP tool calls but their API reads work.
- **Beat 8 must stay honest** (and say that the first forgetting default failed its pre-registered test; that is in `docs/BASELINE.md` L5b). Do not say Plexus is faster or more correct than SQLite; the page says it is not on claims, and the B1 gap is within noise (p = 0.125).
- **Word counts:** each narration cell is ≤ 25 words (checked by `scripts/verify_readme.py`).
- Total on-screen time 2:50. If the take runs long, drop the FalkorDB Browser query in beat 3 first, then the L4/L5 callouts in beat 8, then the Memory-strength panel in beat 7.
