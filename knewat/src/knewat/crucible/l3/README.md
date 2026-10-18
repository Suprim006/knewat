# Crucible Layer 3 pilot: the real team on each arm

One end-to-end run per arm (P, B0, B1) with the real three-agent Acme team: unmodified `claude -p --model sonnet`,
the P3 scheduler, role prompts, per-turn prompts and fault script (builder killed at step ~15, style guide v2 at
step ~20), the same `--max-turns`. Only the MCP server behind the `knewat` name differs.

```bash
cd knewat
uv run python -m knewat.crucible.l3.run run --arms P,B0,B1 --model sonnet --embedder fastembed --port 6378 --budget-usd 4
```

* `baseline_mcp.py`: stdio MCP server with the Knewat tool names and argument names the scenario uses, over the B0 / B1 /
  B2 backends. Its argument names are pinned to `tests/mcp/snapshots/tools.json` by a test, and the P3 scripted agents
  play the whole scenario through it on B0 and B1 (`tests/crucible/l3`). No lineage tools; `verify_artifact` is only
  acknowledged.
* `run.py`: `BackendWorld` lets the P3 scheduler read task state from a baseline backend; metrics are computed from the
  agents' own stream-json transcripts and the final task states, with the same code for every arm.

Result of the pilot (`demo_data/crucible/l3/<run>/`, transcripts included): all three arms finished 12/12 tasks,
reclaimed and finished the killed builder's task, surfaced the JWT/API-key contradiction at write time and
recorded the same number of evidence-carrying decisions and fact-carrying handoffs; no stale artifacts in any arm.
Cost was $0.69 (P), $0.52 (B0), $0.49 (B1), one run each: that is noise-level, not a ranking.
B2 was not run in L3, and BASELINE §3's >= 5 runs per arm with fixed seeds were not run.
