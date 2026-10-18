# L7 family J: concurrent session populations (20261018T102639Z-j)

scale `full`; measured 30.0 s after 5.0 s warm-up; reps 1; seed 20261016; embedder `hash` (F); FTS5 (S). Median of repetitions, [min..max] in brackets. Throughput = completed tool calls/s (ok + no_task + claim_conflict).

## Cells

| P | layout | mix | arm | reps ok/run | tput calls/s (excl. refill) | p50 ms | p99 ms | errors | err classes | FalkorDB cpu% mean/max | FalkorDB mem MiB | GRAPH.* cores busy | driver cpu cores | driver peak WS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 200 | J-one | J-real | F-service | 1/1 | 62.57 | 3219.11 | 7895.14 | 0/2077 | - | 142.3/169.4 | 168.2 | 202.23 | 0.7 | 621.5 |
| 1000 | J-one | J-real | F-service | 1/1 | 49.33 | 14806.9 | 32080.9 | 0/2480 | - | 120.1/143.2 | 164.1 | 915.55 | 0.35 | 666.1 |
| 1000 | J-one | J-trav | F-mcp | 1/1 | 51.8 | 9279.58 | 28304.9 | 0/2554 | - | 117.5/130 | 170.7 | 888.72 | 0.36 | 666.9 |
| 1000 | J-one | J-trav | F-service | 1/1 | 43.07 | 19392 | 38079.6 | 0/2292 | - | 123.8/135 | 163.9 | 746.52 | 0.35 | 665.4 |

## Per-tool latency, p50/p99 ms (median over repetitions)

### P=200 J-one J-real (extra)

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | - | 1993.21/3474.3 (n=213) | - |
| assert_fact | - | 3949.16/8169.3 (n=203) | - |
| claim_next_task | - | 3858.84/5782.78 (n=396) | - |
| complete_task | - | 2378.62/5333.24 (n=199) | - |
| create_tasks | - | 1834.87/3628.54 (n=70) | - |
| handoff | - | 7307.83/8355.24 (n=32) | - |
| recall | - | 3717.17/7378.92 (n=326) | - |
| record_decision | - | 3947.01/8344.03 (n=147) | - |
| remember_episode | - | 3481/5242.06 (n=114) | - |
| start_session | - | 1695.33/3576.36 (n=377) | - |

### P=1000 J-one J-real (extra)

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | - | 11016.5/17856.9 (n=524) | - |
| assert_fact | - | 11859.6/31509.5 (n=46) | - |
| claim_next_task | - | 19109.2/28728.1 (n=972) | - |
| create_tasks | - | 7581.8/11374.9 (n=246) | - |
| recall | - | 17425.2/32807.3 (n=364) | - |
| start_session | - | 14286.8/18023.9 (n=328) | - |

### P=1000 J-one J-trav (extra)

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 5503.01/16189.6 (n=285) | 13777.3/21848.2 (n=353) | - |
| assert_fact | 7595.04/32224.2 (n=18) | 34316.5/41234 (n=49) | - |
| claim_next_task | 26499.3/28309.8 (n=587) | 26077.8/32947.7 (n=845) | - |
| complete_task | - | 20686.9/20686.9 (n=1) | - |
| create_tasks | 26489/28304.9 (n=309) | 7943.6/11066.6 (n=243) | - |
| impact | 11104.9/22675.8 (n=99) | 5.05/24.81 (n=68) | - |
| recall | 8704.93/30497.3 (n=189) | 25173.6/39018.3 (n=271) | - |
| record_decision | - | 23127.5/25568.7 (n=2) | - |
| start_session | 6726.32/27805.3 (n=968) | 12439.8/21941.1 (n=405) | - |
| why | 11416.4/22402.6 (n=99) | 14.75/44.99 (n=55) | - |

## Realized mix (share of attempted calls, first repetition)

* P=200 J-one J-real F-service: {'claim_next_task': 19.1, 'start_session': 18.2, 'recall': 15.7, 'add_source': 10.3, 'assert_fact': 9.8, 'complete_task': 9.6, 'record_decision': 7.1, 'remember_episode': 5.5, 'create_tasks': 3.4, 'handoff': 1.5}
* P=1000 J-one J-real F-service: {'claim_next_task': 39.2, 'add_source': 21.1, 'recall': 14.7, 'start_session': 13.2, 'create_tasks': 9.9, 'assert_fact': 1.9}
* P=1000 J-one J-trav F-mcp: {'start_session': 37.9, 'claim_next_task': 23.0, 'create_tasks': 12.1, 'add_source': 11.2, 'recall': 7.4, 'impact': 3.9, 'why': 3.9, 'assert_fact': 0.7}
* P=1000 J-one J-trav F-service: {'claim_next_task': 36.9, 'start_session': 17.7, 'add_source': 15.4, 'recall': 11.8, 'create_tasks': 10.6, 'impact': 3.0, 'why': 2.4, 'assert_fact': 2.1, 'record_decision': 0.1, 'complete_task': 0.0}

## Recorded mix (pre-registration)

{'start_session': 20, 'recall': 16, 'claim_next_task': 16, 'complete_task': 14, 'add_source': 8, 'assert_fact': 8, 'remember_episode': 5, 'record_decision': 5, 'handoff': 4, 'create_tasks': 3, 'verify_artifact': 1}

## Failures

none

S-shared (optional, J-team): not run.
