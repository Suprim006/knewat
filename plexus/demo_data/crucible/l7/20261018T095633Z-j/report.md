# L7 family J: concurrent session populations (20261018T095633Z-j)

scale `full`; measured 30.0 s after 5.0 s warm-up; reps 1; seed 20261016; embedder `hash` (F); FTS5 (S). Median of repetitions, [min..max] in brackets. Throughput = completed tool calls/s (ok + no_task + claim_conflict).

## Cells

| P | layout | mix | arm | reps ok/run | tput calls/s (excl. refill) | p50 ms | p99 ms | errors | err classes | FalkorDB cpu% mean/max | FalkorDB mem MiB | GRAPH.* cores busy | driver cpu cores | driver peak WS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 200 | J-one | J-real | F-service | 0/1 | FAILED at setup: ResponseError: Query timed out | | | | | | | | | | |
| 1000 | J-one | J-real | F-service | 0/1 | FAILED at setup: ResponseError: Query timed out | | | | | | | | | | |
| 1000 | J-one | J-real | S-file | 1/1 | 187.83 | 23.673 | 42422.9 | 0/6635 | - | -/- | - | - | 1.21 | 678.1 |

## Per-tool latency, p50/p99 ms (median over repetitions)

### P=200 J-one J-real (extra)

| tool | F-mcp | F-service | S-file |
|---|---|---|---|

### P=1000 J-one J-real (extra)

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | - | - | 0.49/32239.5 (n=564) |
| assert_fact | - | - | 2.75/32253.9 (n=503) |
| claim_next_task | - | - | 27.28/37060 (n=1146) |
| complete_task | - | - | 1.02/29141.1 (n=605) |
| create_tasks | - | - | 237.22/39324.6 (n=356) |
| handoff | - | - | 1.54/29483.5 (n=144) |
| recall | - | - | 494.51/37302.9 (n=904) |
| record_decision | - | - | 2.85/33856.2 (n=262) |
| remember_episode | - | - | 0.8/21158.6 (n=300) |
| start_session | - | - | 4690.91/45016 (n=1841) |
| verify_artifact | - | - | 1.45/8088.1 (n=10) |

## Realized mix (share of attempted calls, first repetition)

* P=1000 J-one J-real S-file: {'start_session': 27.7, 'claim_next_task': 17.3, 'recall': 13.6, 'complete_task': 9.1, 'add_source': 8.5, 'assert_fact': 7.6, 'create_tasks': 5.4, 'remember_episode': 4.5, 'record_decision': 3.9, 'handoff': 2.2, 'verify_artifact': 0.2}

## Recorded mix (pre-registration)

{'start_session': 20, 'recall': 16, 'claim_next_task': 16, 'complete_task': 14, 'add_source': 8, 'assert_fact': 8, 'remember_episode': 5, 'record_decision': 5, 'handoff': 4, 'create_tasks': 3, 'verify_artifact': 1}

## Failures

* F-service P=200 J-one J-real rep 0: setup: ResponseError: Query timed out
* F-service P=1000 J-one J-real rep 0: setup: ResponseError: Query timed out

S-shared (optional, J-team): not run.
