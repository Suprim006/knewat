# L7 family J: concurrent session populations (20261018T095841Z-j)

scale `full`; measured 30.0 s after 5.0 s warm-up; reps 1; seed 20261016; embedder `hash` (F); FTS5 (S). Median of repetitions, [min..max] in brackets. Throughput = completed tool calls/s (ok + no_task + claim_conflict).

## Cells

| P | layout | mix | arm | reps ok/run | tput calls/s (excl. refill) | p50 ms | p99 ms | errors | err classes | FalkorDB cpu% mean/max | FalkorDB mem MiB | GRAPH.* cores busy | driver cpu cores | driver peak WS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | J-one | J-trav | F-mcp | 1/1 | 17.87 | 73.961 | 471.778 | 0/538 | - | 63.1/74 | 159.2 | 0.73 | 0.23 | 146.6 |
| 2 | J-one | J-trav | F-service | 1/1 | 25.47 | 37.348 | 402.506 | 0/766 | - | 66.2/70.8 | 161.9 | 0.71 | 0.29 | 147.6 |
| 2 | J-one | J-trav | S-file | 1/1 | 516.8 | 0.999 | 54.757 | 0/15506 | - | -/- | - | - | 0.58 | 83.5 |
| 2 | J-team | J-trav | F-mcp | 1/1 | 14.17 | 97.977 | 543.977 | 0/427 | - | 45.8/64 | 155.7 | 0.58 | 0.16 | 145.7 |
| 2 | J-team | J-trav | F-service | 1/1 | 5.7 | 102.701 | 7327.04 | 0/173 | - | 26/28.8 | 151.7 | 0.12 | 0.06 | 144.1 |
| 2 | J-team | J-trav | S-file | 1/1 | 471.27 | 1.128 | 63.09 | 0/14139 | - | -/- | - | - | 0.6 | 82.7 |
| 20 | J-one | J-trav | F-mcp | 1/1 | 30.93 | 585.312 | 1717.89 | 0/948 | - | 107.9/136.9 | 169.7 | 11.31 | 0.39 | 592.5 |
| 20 | J-one | J-trav | F-service | 1/1 | 58.5 | 287.767 | 1197.45 | 0/1775 | - | 128.4/139.6 | 178.7 | 15.27 | 1.02 | 609.3 |
| 20 | J-one | J-trav | S-file | 1/1 | 689.37 | 0.889 | 858.655 | 0/20700 | - | -/- | - | - | 0.96 | 335.6 |
| 20 | J-team | J-trav | F-mcp | 1/1 | 52.5 | 321.2 | 1289.18 | 0/1595 | - | 130.2/189.4 | 183 | 6.37 | 0.51 | 585.3 |
| 20 | J-team | J-trav | F-service | 1/1 | 63.53 | 224.713 | 1298.23 | 0/1925 | - | 137.8/225.6 | 220.6 | 4.2 | 0.51 | 587 |
| 20 | J-team | J-trav | S-file | 1/1 | 799.5 | 0.939 | 334.844 | 0/24005 | - | -/- | - | - | 0.94 | 351.3 |
| 200 | J-one | J-trav | F-mcp | 1/1 | 49.07 | 4332.41 | 7900.64 | 0/1672 | - | 134.5/159.7 | 209.7 | 198.91 | 0.57 | 616.8 |
| 200 | J-one | J-trav | F-service | 1/1 | 44.6 | 4595.16 | 8787.5 | 0/1538 | - | 136.4/151.7 | 192.6 | 195.62 | 0.47 | 612.9 |
| 200 | J-one | J-trav | S-file | 1/1 | 335.6 | 0.987 | 15339.7 | 0/10267 | - | -/- | - | - | 0.85 | 401.6 |
| 200 | J-team | J-trav | F-mcp | 1/1 | 122.03 | 1369.83 | 5239.43 | 0/3861 | - | 328/393.3 | 440.9 | 135.77 | 1.01 | 603.9 |
| 200 | J-team | J-trav | F-service | 1/1 | 287.43 | 566.19 | 3039.75 | 0/8823 | - | 421.1/451.2 | 403.7 | 134.92 | 1.97 | 610.3 |
| 200 | J-team | J-trav | S-file | 1/1 | 5042.47 | 0.849 | 508.643 | 0/151474 | - | -/- | - | - | 4.64 | 606.9 |
| 1000 | J-one | J-trav | F-mcp | 0/1 | FAILED at setup: ResponseError: Query timed out | | | | | | | | | | |
| 1000 | J-one | J-trav | F-service | 0/1 | FAILED at setup: ResponseError: Query timed out | | | | | | | | | | |
| 1000 | J-one | J-trav | S-file | 1/1 | 494.17 | 0.829 | 36923 | 0/15825 | - | -/- | - | - | 1.5 | 802.4 |
| 1000 | J-team | J-trav | F-mcp | 1/1 | 268.3 | 1245.29 | 3685.38 | 64985/73680 | max_pending=64985 | 302.9/386.3 | 923.3 | 504.98 | 4.07 | 719.7 |
| 1000 | J-team | J-trav | F-service | 1/1 | 386.53 | 1059.67 | 2840.52 | 69743/81910 | max_pending=69743 | 320/388.9 | 1070.1 | 487.49 | 2.8 | 718.1 |
| 1000 | J-team | J-trav | S-file | 1/1 | 4038.9 | 1.17 | 6667.24 | 0/122167 | - | -/- | - | - | 3.77 | 1025.6 |

## Per-tool latency, p50/p99 ms (median over repetitions)

### P=2 J-one J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 20/65.11 (n=25) | 12.76/114.3 (n=38) | 0.31/40.37 (n=1222) |
| assert_fact | 121.16/300.61 (n=20) | 105.09/286.34 (n=32) | 1.34/65.09 (n=1251) |
| claim_next_task | 66.35/163.94 (n=82) | 37.45/149.45 (n=112) | 1.56/51.79 (n=2220) |
| complete_task | 67.79/231.47 (n=70) | 37.35/131.41 (n=94) | 0.45/46.72 (n=1859) |
| create_tasks | 62.73/162.43 (n=15) | 18.75/131.04 (n=27) | 1.04/49.71 (n=402) |
| handoff | 76.6/192.05 (n=31) | 55.76/130.15 (n=37) | 0.91/42.66 (n=517) |
| impact | 58.16/133.81 (n=24) | 11.86/85.72 (n=39) | 1.44/9.77 (n=720) |
| recall | 274.72/604.04 (n=92) | 257.38/563.91 (n=129) | 2.77/86.32 (n=2164) |
| record_decision | 78.71/171.97 (n=18) | 48.25/156.76 (n=37) | 0.94/51.74 (n=691) |
| remember_episode | 62.78/170.92 (n=27) | 30.03/66.2 (n=30) | 0.44/35.1 (n=706) |
| start_session | 53.15/175.16 (n=104) | 11.49/75.67 (n=148) | 0.31/46.17 (n=2876) |
| verify_artifact | 76.25/100.46 (n=3) | 8.28/28.8 (n=6) | 0.33/92.83 (n=140) |
| why | 77.81/161.37 (n=27) | 42.54/79.91 (n=37) | 1.15/18.07 (n=738) |

### P=2 J-team J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 14.32/109.81 (n=19) | 47.37/479.77 (n=13) | 0.32/59.13 (n=1076) |
| assert_fact | 146.72/317.45 (n=15) | 321.08/7541.38 (n=10) | 1.35/65.15 (n=1097) |
| claim_next_task | 84.55/228.64 (n=67) | 117.09/394.07 (n=26) | 2.21/61.51 (n=2014) |
| complete_task | 87.85/293.29 (n=60) | 97.68/390.14 (n=23) | 0.49/45.3 (n=1675) |
| create_tasks | 76.55/108 (n=8) | 37.78/208.41 (n=3) | 1.12/71.34 (n=392) |
| handoff | 114.37/409.41 (n=30) | 94.16/4145.99 (n=9) | 0.87/63.96 (n=462) |
| impact | 82.27/242.85 (n=19) | 134.67/310.09 (n=7) | 1.76/15.29 (n=668) |
| recall | 334.15/645.36 (n=76) | 444.05/7327.04 (n=26) | 3.31/98.03 (n=2017) |
| record_decision | 103.9/206.33 (n=10) | 89.83/483.6 (n=6) | 0.89/57.3 (n=669) |
| remember_episode | 77.69/269.6 (n=24) | 92.41/183 (n=7) | 0.46/42.95 (n=621) |
| start_session | 62/271.98 (n=76) | 30.89/266.35 (n=32) | 0.32/40.7 (n=2616) |
| verify_artifact | 39.02/49.73 (n=2) | 6.35/6.35 (n=1) | 0.33/136.25 (n=137) |
| why | 132.64/248.81 (n=21) | 78.53/281.63 (n=10) | 1.57/15.06 (n=695) |

### P=20 J-one J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 142.19/631.27 (n=75) | 131.88/423.92 (n=127) | 0.23/263.83 (n=1570) |
| assert_fact | 867.82/1707.82 (n=72) | 502.12/1264.56 (n=132) | 0.96/547.63 (n=1590) |
| claim_next_task | 613.7/1123.56 (n=130) | 317.36/776.4 (n=263) | 2.52/494.95 (n=3017) |
| complete_task | 542.2/995.83 (n=111) | 320.19/753.03 (n=215) | 0.35/865.02 (n=2473) |
| create_tasks | 658.89/1029.01 (n=29) | 196.67/986.27 (n=45) | 0.95/548.26 (n=523) |
| handoff | 674.16/1062.46 (n=34) | 384.35/840.98 (n=66) | 0.65/515.87 (n=752) |
| impact | 421.47/972.88 (n=47) | 11.25/86.96 (n=80) | 1.68/16.91 (n=961) |
| recall | 1093.79/1928.65 (n=131) | 675.37/1280.88 (n=265) | 2.89/1869.71 (n=2920) |
| record_decision | 669.84/1174.24 (n=52) | 436.54/1241.64 (n=75) | 0.63/958.47 (n=877) |
| remember_episode | 505/901.28 (n=48) | 303.81/1065.08 (n=79) | 0.33/541.99 (n=963) |
| start_session | 482.55/863.89 (n=167) | 141.44/473.41 (n=331) | 0.24/507.04 (n=3850) |
| verify_artifact | 520.3/828.24 (n=10) | 114.64/325.69 (n=13) | 0.24/771.64 (n=183) |
| why | 441.81/1060.26 (n=42) | 34.52/218.18 (n=84) | 1.2/10.91 (n=1021) |

### P=20 J-team J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 74.56/263.65 (n=114) | 81.17/389.26 (n=143) | 0.35/219.7 (n=1846) |
| assert_fact | 547.99/1665.62 (n=118) | 533.9/1278.16 (n=145) | 1.62/254.28 (n=1820) |
| claim_next_task | 300.48/840.57 (n=238) | 257.58/884.79 (n=283) | 1.17/143.22 (n=3483) |
| complete_task | 324.61/1319.77 (n=202) | 237.77/784.77 (n=236) | 0.52/187.95 (n=2866) |
| create_tasks | 299.96/637.87 (n=40) | 185.65/772.24 (n=51) | 0.95/2244 (n=592) |
| create_tasks_refill | - | - | 1.35/6.65 (n=3) |
| handoff | 372.54/1361.36 (n=59) | 339.68/1298.23 (n=77) | 1.03/484.11 (n=887) |
| impact | 259.73/1147.75 (n=75) | 84.3/523.96 (n=83) | 1.49/17.83 (n=1141) |
| recall | 668.73/2008.12 (n=244) | 700.57/1878.15 (n=287) | 2.47/1437.16 (n=3409) |
| record_decision | 364.47/802.36 (n=69) | 312.21/1076.61 (n=86) | 1.05/214.52 (n=1014) |
| remember_episode | 262.7/1031.71 (n=70) | 190.41/650.98 (n=88) | 0.51/1369.41 (n=1144) |
| start_session | 259.48/572.32 (n=288) | 80.83/385.02 (n=349) | 0.36/152.65 (n=4484) |
| verify_artifact | 247.27/453.19 (n=15) | 108.77/508.05 (n=16) | 0.34/59.27 (n=204) |
| why | 287.93/1244.57 (n=63) | 105.49/362.11 (n=81) | 0.97/10.27 (n=1112) |

### P=200 J-one J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 687.35/4526.11 (n=145) | 2588.61/4288.76 (n=151) | 0.23/13590.5 (n=737) |
| assert_fact | 5521.45/8833.4 (n=143) | 7142.24/9559.9 (n=150) | 0.95/15339.7 (n=731) |
| claim_next_task | 4887.73/7531.59 (n=313) | 5042.95/6543.09 (n=255) | 11.21/11569.6 (n=1496) |
| complete_task | 3820.65/7095.9 (n=159) | 5057.92/6655.95 (n=161) | 0.33/13536 (n=1179) |
| create_tasks | 6254.67/7458.7 (n=92) | 2878.57/4318.55 (n=35) | 1.35/21155.4 (n=308) |
| handoff | 6680.04/8883 (n=32) | 6157.6/9291.92 (n=30) | 0.64/11450.7 (n=355) |
| impact | 2699.34/5632.2 (n=57) | 20.93/111.65 (n=49) | 1.23/20.53 (n=462) |
| recall | 4408.23/7557.72 (n=219) | 5206.7/8336.11 (n=234) | 2.02/17220.9 (n=1516) |
| record_decision | 4470.59/8819.39 (n=87) | 7966.38/9145.27 (n=103) | 0.67/17711.3 (n=481) |
| remember_episode | 4160.94/7517.12 (n=68) | 4814.05/6355.29 (n=56) | 0.33/14081.7 (n=489) |
| start_session | 4110.01/7393.93 (n=295) | 2649.43/4257.74 (n=258) | 0.23/20279.4 (n=1985) |
| verify_artifact | - | - | 0.36/14669.5 (n=76) |
| why | 2483.75/5904.18 (n=62) | 41.72/122.4 (n=56) | 1.06/10.99 (n=452) |

### P=200 J-team J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 318.94/1560.27 (n=260) | 214.68/1881.61 (n=566) | 0.29/324.6 (n=10890) |
| assert_fact | 2554.52/5240.9 (n=308) | 1295.71/3094.69 (n=601) | 1.48/553.99 (n=10824) |
| claim_next_task | 1311.49/3801.97 (n=522) | 624.52/2277.02 (n=1252) | 0.98/332.67 (n=21977) |
| complete_task | 1343.91/3763.34 (n=465) | 622.89/2317.76 (n=1090) | 0.45/460.76 (n=17877) |
| create_tasks | 1148.39/3744.94 (n=96) | 403.3/660.33 (n=258) | 0.99/452.16 (n=4254) |
| create_tasks_refill | - | - | 1.05/240.31 (n=29) |
| handoff | 1682.05/4371.66 (n=141) | 788.14/2553.13 (n=337) | 1/407 (n=5475) |
| impact | 1078.25/3762.79 (n=153) | 198.99/347.81 (n=419) | 0.7/79.18 (n=7132) |
| recall | 2728.72/5546.85 (n=585) | 1524.58/3308.76 (n=1344) | 2.09/1338.06 (n=22129) |
| record_decision | 1587.87/4368.85 (n=210) | 816.31/1315.68 (n=419) | 0.97/565.69 (n=7042) |
| remember_episode | 1069.06/3680.37 (n=268) | 418.82/2008.79 (n=473) | 0.45/531.72 (n=6765) |
| start_session | 1057.53/3472.08 (n=685) | 209.52/398.37 (n=1641) | 0.32/374.31 (n=28453) |
| verify_artifact | 1497.02/2149.79 (n=10) | 218.86/476.45 (n=60) | 0.3/585.33 (n=1414) |
| why | 1140.42/3832.68 (n=158) | 226.89/379.79 (n=363) | 1.04/70.76 (n=7213) |

### P=1000 J-one J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | - | - | 0.19/34428.9 (n=1197) |
| assert_fact | - | - | 0.75/25245.6 (n=1128) |
| claim_next_task | - | - | 9.25/32909.6 (n=2408) |
| complete_task | - | - | 0.26/24829.6 (n=1588) |
| create_tasks | - | - | 1.42/36573.1 (n=554) |
| handoff | - | - | 0.52/19196 (n=464) |
| impact | - | - | 0.91/6.55 (n=696) |
| recall | - | - | 1.47/34322.8 (n=2175) |
| record_decision | - | - | 0.55/27235.3 (n=664) |
| remember_episode | - | - | 0.26/27422.9 (n=717) |
| start_session | - | - | 0.22/40686 (n=3436) |
| verify_artifact | - | - | 0.24/21955.3 (n=91) |
| why | - | - | 0.88/4.45 (n=707) |

### P=1000 J-team J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 835.43/1854.34 (n=3461) | 1037.09/1730.99 (n=4774) | 0.36/3755.5 (n=9172) |
| assert_fact | 2419.46/4436.99 (n=3507) | 2634.19/5425.97 (n=4917) | 14.63/7074.56 (n=9179) |
| claim_next_task | 2238.27/4191.27 (n=4348) | 2226.84/3629.05 (n=6230) | 0.85/2796.9 (n=17743) |
| complete_task | 1965.3/2135.2 (n=51) | 2537.28/3147.81 (n=166) | 0.71/6874.1 (n=14153) |
| create_tasks | 2402.43/4525.58 (n=1842) | 1942.83/2879.36 (n=2314) | 2.35/4182.94 (n=3469) |
| handoff | 2489.16/4353.06 (n=387) | 2444.85/4031.73 (n=636) | 4.19/6336.05 (n=4251) |
| impact | 1283.91/3312.95 (n=1358) | 1026.16/1651.62 (n=1911) | 0.61/103.75 (n=5690) |
| recall | 2658.04/5807.6 (n=2727) | 2695.35/5633.14 (n=3977) | 4.03/8603.95 (n=17397) |
| record_decision | 2487.43/3923.42 (n=504) | 2693.24/4194.51 (n=829) | 4.54/7441.72 (n=5509) |
| remember_episode | 1178.99/4099.94 (n=603) | 1273.9/2303.06 (n=1105) | 0.85/6006.76 (n=5558) |
| start_session | 1258.3/3270.37 (n=53531) | 1038.9/1743.41 (n=53176) | 0.47/10673 (n=23177) |
| verify_artifact | - | 1157.95/1157.95 (n=5) | 0.57/4050.25 (n=1029) |
| why | 1380.86/3203.11 (n=1361) | 1135.12/1800.82 (n=1870) | 0.99/265.18 (n=5840) |

## Realized mix (share of attempted calls, first repetition)

* P=2 J-one J-trav F-mcp: {'start_session': 19.3, 'recall': 17.1, 'claim_next_task': 15.2, 'complete_task': 13.0, 'handoff': 5.8, 'why': 5.0, 'remember_episode': 5.0, 'add_source': 4.6, 'impact': 4.5, 'assert_fact': 3.7, 'record_decision': 3.3, 'create_tasks': 2.8, 'verify_artifact': 0.6}
* P=2 J-one J-trav F-service: {'start_session': 19.3, 'recall': 16.8, 'claim_next_task': 14.6, 'complete_task': 12.3, 'impact': 5.1, 'add_source': 5.0, 'record_decision': 4.8, 'why': 4.8, 'handoff': 4.8, 'assert_fact': 4.2, 'remember_episode': 3.9, 'create_tasks': 3.5, 'verify_artifact': 0.8}
* P=2 J-one J-trav S-file: {'start_session': 18.5, 'claim_next_task': 14.3, 'recall': 14.0, 'complete_task': 12.0, 'assert_fact': 8.1, 'add_source': 7.9, 'why': 4.8, 'impact': 4.6, 'remember_episode': 4.6, 'record_decision': 4.5, 'handoff': 3.3, 'create_tasks': 2.6, 'verify_artifact': 0.9}
* P=2 J-team J-trav F-mcp: {'recall': 17.8, 'start_session': 17.8, 'claim_next_task': 15.7, 'complete_task': 14.1, 'handoff': 7.0, 'remember_episode': 5.6, 'why': 4.9, 'impact': 4.4, 'add_source': 4.4, 'assert_fact': 3.5, 'record_decision': 2.3, 'create_tasks': 1.9, 'verify_artifact': 0.5}
* P=2 J-team J-trav F-service: {'start_session': 18.5, 'recall': 15.0, 'claim_next_task': 15.0, 'complete_task': 13.3, 'add_source': 7.5, 'assert_fact': 5.8, 'why': 5.8, 'handoff': 5.2, 'impact': 4.0, 'remember_episode': 4.0, 'record_decision': 3.5, 'create_tasks': 1.7, 'verify_artifact': 0.6}
* P=2 J-team J-trav S-file: {'start_session': 18.5, 'recall': 14.3, 'claim_next_task': 14.2, 'complete_task': 11.8, 'assert_fact': 7.8, 'add_source': 7.6, 'why': 4.9, 'record_decision': 4.7, 'impact': 4.7, 'remember_episode': 4.4, 'handoff': 3.3, 'create_tasks': 2.8, 'verify_artifact': 1.0}
* P=20 J-one J-trav F-mcp: {'start_session': 17.6, 'recall': 13.8, 'claim_next_task': 13.7, 'complete_task': 11.7, 'add_source': 7.9, 'assert_fact': 7.6, 'record_decision': 5.5, 'remember_episode': 5.1, 'impact': 5.0, 'why': 4.4, 'handoff': 3.6, 'create_tasks': 3.1, 'verify_artifact': 1.1}
* P=20 J-one J-trav F-service: {'start_session': 18.6, 'recall': 14.9, 'claim_next_task': 14.8, 'complete_task': 12.1, 'assert_fact': 7.4, 'add_source': 7.2, 'why': 4.7, 'impact': 4.5, 'remember_episode': 4.5, 'record_decision': 4.2, 'handoff': 3.7, 'create_tasks': 2.5, 'verify_artifact': 0.7}
* P=20 J-one J-trav S-file: {'start_session': 18.6, 'claim_next_task': 14.6, 'recall': 14.1, 'complete_task': 11.9, 'assert_fact': 7.7, 'add_source': 7.6, 'why': 4.9, 'remember_episode': 4.7, 'impact': 4.6, 'record_decision': 4.2, 'handoff': 3.6, 'create_tasks': 2.5, 'verify_artifact': 0.9}
* P=20 J-team J-trav F-mcp: {'start_session': 18.1, 'recall': 15.3, 'claim_next_task': 14.9, 'complete_task': 12.7, 'assert_fact': 7.4, 'add_source': 7.1, 'impact': 4.7, 'remember_episode': 4.4, 'record_decision': 4.3, 'why': 3.9, 'handoff': 3.7, 'create_tasks': 2.5, 'verify_artifact': 0.9}
* P=20 J-team J-trav F-service: {'start_session': 18.1, 'recall': 14.9, 'claim_next_task': 14.7, 'complete_task': 12.3, 'assert_fact': 7.5, 'add_source': 7.4, 'remember_episode': 4.6, 'record_decision': 4.5, 'impact': 4.3, 'why': 4.2, 'handoff': 4.0, 'create_tasks': 2.6, 'verify_artifact': 0.8}
* P=20 J-team J-trav S-file: {'start_session': 18.7, 'claim_next_task': 14.5, 'recall': 14.2, 'complete_task': 11.9, 'add_source': 7.7, 'assert_fact': 7.6, 'remember_episode': 4.8, 'impact': 4.8, 'why': 4.6, 'record_decision': 4.2, 'handoff': 3.7, 'create_tasks': 2.5, 'verify_artifact': 0.8, 'create_tasks_refill': 0.0}
* P=200 J-one J-trav F-mcp: {'claim_next_task': 18.7, 'start_session': 17.6, 'recall': 13.1, 'complete_task': 9.5, 'add_source': 8.7, 'assert_fact': 8.6, 'create_tasks': 5.5, 'record_decision': 5.2, 'remember_episode': 4.1, 'why': 3.7, 'impact': 3.4, 'handoff': 1.9}
* P=200 J-one J-trav F-service: {'start_session': 16.8, 'claim_next_task': 16.6, 'recall': 15.2, 'complete_task': 10.5, 'add_source': 9.8, 'assert_fact': 9.8, 'record_decision': 6.7, 'remember_episode': 3.6, 'why': 3.6, 'impact': 3.2, 'create_tasks': 2.3, 'handoff': 2.0}
* P=200 J-one J-trav S-file: {'start_session': 19.3, 'recall': 14.8, 'claim_next_task': 14.6, 'complete_task': 11.5, 'add_source': 7.2, 'assert_fact': 7.1, 'remember_episode': 4.8, 'record_decision': 4.7, 'impact': 4.5, 'why': 4.4, 'handoff': 3.5, 'create_tasks': 3.0, 'verify_artifact': 0.7}
* P=200 J-team J-trav F-mcp: {'start_session': 17.7, 'recall': 15.2, 'claim_next_task': 13.5, 'complete_task': 12.0, 'assert_fact': 8.0, 'remember_episode': 6.9, 'add_source': 6.7, 'record_decision': 5.4, 'why': 4.1, 'impact': 4.0, 'handoff': 3.7, 'create_tasks': 2.5, 'verify_artifact': 0.3}
* P=200 J-team J-trav F-service: {'start_session': 18.6, 'recall': 15.2, 'claim_next_task': 14.2, 'complete_task': 12.4, 'assert_fact': 6.8, 'add_source': 6.4, 'remember_episode': 5.4, 'record_decision': 4.7, 'impact': 4.7, 'why': 4.1, 'handoff': 3.8, 'create_tasks': 2.9, 'verify_artifact': 0.7}
* P=200 J-team J-trav S-file: {'start_session': 18.8, 'recall': 14.6, 'claim_next_task': 14.5, 'complete_task': 11.8, 'add_source': 7.2, 'assert_fact': 7.1, 'why': 4.8, 'impact': 4.7, 'record_decision': 4.6, 'remember_episode': 4.5, 'handoff': 3.6, 'create_tasks': 2.8, 'verify_artifact': 0.9, 'create_tasks_refill': 0.0}
* P=1000 J-one J-trav S-file: {'start_session': 21.7, 'claim_next_task': 15.2, 'recall': 13.7, 'complete_task': 10.0, 'add_source': 7.6, 'assert_fact': 7.1, 'remember_episode': 4.5, 'why': 4.5, 'impact': 4.4, 'record_decision': 4.2, 'create_tasks': 3.5, 'handoff': 2.9, 'verify_artifact': 0.6}
* P=1000 J-team J-trav F-mcp: {'start_session': 72.7, 'claim_next_task': 5.9, 'assert_fact': 4.8, 'add_source': 4.7, 'recall': 3.7, 'create_tasks': 2.5, 'why': 1.8, 'impact': 1.8, 'remember_episode': 0.8, 'record_decision': 0.7, 'handoff': 0.5, 'complete_task': 0.1}
* P=1000 J-team J-trav F-service: {'start_session': 64.9, 'claim_next_task': 7.6, 'assert_fact': 6.0, 'add_source': 5.8, 'recall': 4.9, 'create_tasks': 2.8, 'impact': 2.3, 'why': 2.3, 'remember_episode': 1.3, 'record_decision': 1.0, 'handoff': 0.8, 'complete_task': 0.2, 'verify_artifact': 0.0}
* P=1000 J-team J-trav S-file: {'start_session': 19.0, 'claim_next_task': 14.5, 'recall': 14.2, 'complete_task': 11.6, 'assert_fact': 7.5, 'add_source': 7.5, 'why': 4.8, 'impact': 4.7, 'remember_episode': 4.5, 'record_decision': 4.5, 'handoff': 3.5, 'create_tasks': 2.8, 'verify_artifact': 0.8}

## Recorded mix (pre-registration)

{'start_session': 20, 'recall': 16, 'claim_next_task': 16, 'complete_task': 14, 'add_source': 8, 'assert_fact': 8, 'remember_episode': 5, 'record_decision': 5, 'handoff': 4, 'create_tasks': 3, 'verify_artifact': 1}

## Failures

* F-mcp P=1000 J-one J-trav rep 0: setup: ResponseError: Query timed out
* F-service P=1000 J-one J-trav rep 0: setup: ResponseError: Query timed out

S-shared (optional, J-team): not run.
