# Crucible L3 pilot: real 3-agent team, one run per arm

Model `sonnet`, n=1 per arm.

| Metric | P | B0 | B1 |
|---|---|---|---|
| status | completed | completed | completed |
| tasks done | 12/12 | 12/12 | 12/12 |
| builder killed -> reclaimed by | researcher, finished=True | researcher, finished=True | researcher, finished=True |
| decisions (with evidence) | 4 (4) | 4 (4) | 4 (4) |
| handoffs (carrying facts) | 4 (4) | 4 (4) | 4 (4) |
| stale artifacts | 0 | 0 | 0 |
| contradictions surfaced at write time | 1 | 1 | 1 |
| tool calls / errors | 82 / 0 | 81 / 0 | 83 / 0 |
| claude processes | 16 | 16 | 16 |
| tokens | 1,723,458 | 981,150 | 993,051 |
| cost (USD) | 0.692 | 0.515 | 0.491 |
| wall time (s) | 420.1 | 316.4 | 324.1 |

## Headline

- L3 pilot (n=1 per arm): tasks done P 12/12, B0 12/12, B1 12/12.
- L3: the killed builder's task was reclaimed and finished in 3 of 3 arms (P, B0, B1).
- L3: no separation between arms on evidence-carrying decisions, fact-carrying handoffs, stale artifacts or surfaced contradictions (identical counts).
- L3: cost per full run P $0.69, B0 $0.52, B1 $0.49; with n=1 this is noise-level, not a ranking.

## Honesty

- L3 pilot: ONE run per arm (BASELINE §3 asks for >= 5 with fixed seeds); LLM runs are noisy, so nothing here is a ranking.
- B0/B1 agents talk to a purpose-built stdio MCP server with the same tool names and argument names as the Knewat tools the scenario uses (crucible/l3/baseline_mcp.py); they have no lineage tools and `verify_artifact` is only acknowledged. P uses the real knewat-mcp.
- The scheduler, prompts, faults (builder killed at step 15, style guide v2 at step 20) and model are the P3 demo's and identical across arms. The poison fault is off.
- Metrics come from the agents' stream-json transcripts and the final task states; 'stale artifacts' is a text heuristic (an artifact summary written after v2 was published that names v1 and not v2).
