# L7 family J: concurrent session populations (20261016T122247Z-j)

scale `full`; measured 30.0 s after 5.0 s warm-up; reps 1; seed 20261016; embedder `hash` (F); FTS5 (S). Median of repetitions, [min..max] in brackets. Throughput = completed tool calls/s (ok + no_task + claim_conflict).

## Cells

| P | layout | mix | arm | reps ok/run | tput calls/s (excl. refill) | p50 ms | p99 ms | errors | err classes | FalkorDB cpu% mean/max | FalkorDB mem MiB | GRAPH.* cores busy | driver cpu cores | driver peak WS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | J-one | J-trav | F-mcp | 1/1 | 107.57 | 14.414 | 50.436 | 0/3229 | - | 86.6/91.3 | 140.9 | 0.91 | 0.49 | 144.7 |
| 2 | J-one | J-trav | F-service | 1/1 | 177.3 | 4.907 | 45.759 | 0/5321 | - | 80/82.6 | 141.8 | 0.83 | 0.62 | 145.1 |
| 2 | J-one | J-trav | S-file | 1/1 | 1083.67 | 0.375 | 31.947 | 0/32512 | - | -/- | - | - | 1.04 | 86 |
| 2 | J-team | J-trav | F-mcp | 1/1 | 108.2 | 14.303 | 51.775 | 0/3248 | - | 84.1/90.2 | 141.6 | 0.9 | 0.5 | 144.9 |
| 2 | J-team | J-trav | F-service | 1/1 | 177.27 | 4.945 | 44.983 | 0/5320 | - | 80.3/82.9 | 141.8 | 0.83 | 0.61 | 145.5 |
| 2 | J-team | J-trav | S-file | 1/1 | 1093.57 | 0.37 | 31.44 | 0/32809 | - | -/- | - | - | 1.03 | 86.1 |
| 20 | J-one | J-trav | F-mcp | 1/1 | 159.77 | 130.842 | 198.214 | 0/4813 | - | 139.6/148.7 | 154.3 | 17.93 | 0.69 | 577.6 |
| 20 | J-one | J-trav | F-service | 1/1 | 275.2 | 53.679 | 203.298 | 0/8276 | - | 147/158.4 | 155.1 | 17.45 | 0.95 | 579.1 |
| 20 | J-one | J-trav | S-file | 1/1 | 1077.33 | 0.403 | 174.542 | 0/32340 | - | -/- | - | - | 1.09 | 346.5 |
| 20 | J-team | J-trav | F-mcp | 1/1 | 255.4 | 76.435 | 155.146 | 0/7682 | - | 232.9/248.1 | 175 | 11.72 | 1.33 | 580.5 |
| 20 | J-team | J-trav | F-service | 1/1 | 481.47 | 26.435 | 139.063 | 0/14464 | - | 256.6/286.5 | 181 | 9.64 | 2 | 582 |
| 20 | J-team | J-trav | S-file | 1/1 | 3819.7 | 0.557 | 65.169 | 0/114612 | - | -/- | - | - | 4.18 | 379.5 |
| 200 | J-one | J-trav | F-mcp | 1/1 | 112.93 | 1738.3 | 2872.82 | 0/3588 | - | 131.2/152.1 | 177.3 | 198.47 | 0.44 | 596.7 |
| 200 | J-one | J-trav | F-service | 1/1 | 165.37 | 979.507 | 3609.21 | 0/5161 | - | 133.6/137 | 162.7 | 198.82 | 0.51 | 597.9 |
| 200 | J-one | J-trav | S-file | 1/1 | 690.07 | 0.378 | 12866.6 | 0/20902 | - | -/- | - | - | 1.19 | 419.5 |
| 200 | J-team | J-trav | F-mcp | 1/1 | 347.9 | 538.38 | 1202.3 | 0/10637 | - | 309.1/341.6 | 372.6 | 169.74 | 1.88 | 603 |
| 200 | J-team | J-trav | F-service | 1/1 | 675.8 | 152.291 | 994.59 | 0/20474 | - | 413.1/436.1 | 415.9 | 151.25 | 3.09 | 607.9 |
| 200 | J-team | J-trav | S-file | 1/1 | 7762 | 1.175 | 332.576 | 0/233060 | - | -/- | - | - | 7.62 | 592 |
| 1000 | J-one | J-trav | F-mcp | 1/1 | 64.73 | 6683.85 | 26793 | 0/2942 | - | 115.6/153.1 | 182.4 | 1016.47 | 0.38 | 667.4 |
| 1000 | J-one | J-trav | F-service | 1/1 | 99.3 | 8174.7 | 28070 | 0/3979 | - | 123.9/145.2 | 180.3 | 1005.77 | 0.46 | 676.5 |
| 1000 | J-one | J-trav | S-file | 1/1 | 658.33 | 0.477 | 40280.7 | 0/20750 | - | -/- | - | - | 1.79 | 823.9 |
| 1000 | J-team | J-trav | F-mcp | 1/1 | 295.2 | 1222.77 | 3611.02 | 90168/99622 | max_pending=90147, other=21 | 245.4/264.8 | 681.8 | 500.71 | 5.49 | 726.3 |
| 1000 | J-team | J-trav | F-service | 1/1 | 514.5 | 884.209 | 1700.43 | 145880/161871 | max_pending=145880 | 216/250.8 | 676.9 | 507.94 | 5.03 | 740.5 |
| 1000 | J-team | J-trav | S-file | 1/1 | 5331.5 | 5.284 | 3695.68 | 0/160944 | - | -/- | - | - | 6.05 | 1055 |

## Per-tool latency, p50/p99 ms (median over repetitions)

### P=2 J-one J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 2.53/7.51 (n=214) | 2.54/8.71 (n=362) | 0.11/24.54 (n=2333) |
| assert_fact | 25.38/37.05 (n=204) | 20.25/30.73 (n=351) | 0.45/23.75 (n=2357) |
| claim_next_task | 14.63/24.84 (n=460) | 4.51/10.48 (n=771) | 1.93/24.19 (n=4666) |
| complete_task | 14.37/22.39 (n=374) | 3.51/9.36 (n=626) | 0.14/23.28 (n=3822) |
| create_tasks | 16.49/36.18 (n=98) | 5.7/12.86 (n=149) | 0.65/13.53 (n=922) |
| handoff | 13.9/24.58 (n=118) | 9.53/17.27 (n=200) | 0.28/25.06 (n=1129) |
| impact | 12.03/22.2 (n=155) | 3.81/7.07 (n=256) | 0.76/2.02 (n=1546) |
| recall | 41.64/79.73 (n=501) | 36.06/81.02 (n=809) | 1.63/62.57 (n=4765) |
| record_decision | 14.29/21.44 (n=173) | 9.75/20.61 (n=263) | 0.29/30.06 (n=1579) |
| remember_episode | 11.43/21.89 (n=135) | 6.78/11.69 (n=240) | 0.14/28.17 (n=1401) |
| start_session | 10.48/18.26 (n=606) | 2.86/8.61 (n=995) | 0.1/18.37 (n=6126) |
| verify_artifact | 10.38/17.14 (n=39) | 2.75/9.08 (n=59) | 0.11/16.2 (n=324) |
| why | 21.88/35.46 (n=152) | 13.13/28.94 (n=240) | 0.86/4.08 (n=1542) |

### P=2 J-team J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 2.54/8.19 (n=214) | 2.53/8.25 (n=362) | 0.11/23.45 (n=2340) |
| assert_fact | 25.24/37.99 (n=204) | 20.19/31.76 (n=351) | 0.43/25.91 (n=2370) |
| claim_next_task | 14.75/23.42 (n=462) | 4.5/11.22 (n=772) | 1.91/24.96 (n=4718) |
| complete_task | 14.19/23.24 (n=378) | 3.59/10.23 (n=625) | 0.14/27.24 (n=3847) |
| create_tasks | 15.9/25.14 (n=98) | 5.63/12.67 (n=149) | 0.65/20.58 (n=932) |
| handoff | 13.62/27.48 (n=119) | 9.94/17.62 (n=199) | 0.27/23.58 (n=1157) |
| impact | 11.66/19.35 (n=157) | 3.82/7.41 (n=256) | 0.78/2.01 (n=1540) |
| recall | 41.25/86.53 (n=502) | 35.8/73.35 (n=808) | 1.57/61.05 (n=4806) |
| record_decision | 14.11/24.53 (n=174) | 10.16/20.8 (n=263) | 0.29/28.36 (n=1598) |
| remember_episode | 11.15/20.12 (n=136) | 6.57/13.2 (n=240) | 0.14/29.41 (n=1427) |
| start_session | 10.35/17.54 (n=610) | 2.87/8.03 (n=996) | 0.1/26.11 (n=6180) |
| verify_artifact | 10.43/18.39 (n=40) | 2.66/8.71 (n=59) | 0.1/53.62 (n=330) |
| why | 21.87/35.14 (n=154) | 13.42/25.94 (n=240) | 0.82/4.46 (n=1564) |

### P=20 J-one J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 33.85/55.33 (n=310) | 44.3/84.24 (n=576) | 0.11/70.33 (n=2350) |
| assert_fact | 164.81/238.78 (n=317) | 159.86/258.37 (n=591) | 0.45/79.45 (n=2387) |
| claim_next_task | 148.21/192.47 (n=718) | 48.95/91.17 (n=1216) | 1.89/59.4 (n=4672) |
| complete_task | 145.85/188.97 (n=582) | 46.11/87.99 (n=982) | 0.14/169.44 (n=3814) |
| create_tasks | 149.11/194.3 (n=143) | 50.5/90.74 (n=225) | 0.65/95.29 (n=861) |
| handoff | 137.59/188.15 (n=184) | 124.52/201.24 (n=326) | 0.28/139.84 (n=1157) |
| impact | 79.16/106.59 (n=238) | 5.08/13.48 (n=399) | 1.03/7.14 (n=1559) |
| recall | 139.77/187.96 (n=720) | 123.63/191.03 (n=1209) | 1.65/1630.5 (n=4709) |
| record_decision | 139.55/193.78 (n=231) | 131.5/187.81 (n=368) | 0.3/274.94 (n=1454) |
| remember_episode | 108.25/144.84 (n=198) | 94.88/147.05 (n=366) | 0.14/168.67 (n=1472) |
| start_session | 109.02/147.71 (n=897) | 45.08/78.56 (n=1538) | 0.1/129.2 (n=6043) |
| verify_artifact | 105.88/137.56 (n=40) | 40.58/79 (n=69) | 0.1/71.51 (n=310) |
| why | 92.38/125.76 (n=235) | 20.13/50.03 (n=411) | 0.85/4.45 (n=1552) |

### P=20 J-team J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 18.5/39.45 (n=484) | 16.8/40.72 (n=1011) | 0.16/55.62 (n=8353) |
| assert_fact | 114.36/184.42 (n=473) | 96.11/176.75 (n=1003) | 0.69/56.81 (n=8256) |
| claim_next_task | 82.23/121.8 (n=1133) | 21.02/48.18 (n=2073) | 1.76/46.47 (n=16628) |
| complete_task | 81.61/128.39 (n=906) | 19.39/46.62 (n=1687) | 0.22/58.3 (n=13525) |
| create_tasks | 85.68/137.01 (n=232) | 23.68/43.06 (n=412) | 0.79/46.92 (n=3104) |
| create_tasks_refill | - | - | 0.76/7.15 (n=27) |
| handoff | 75.55/126.59 (n=298) | 53.85/94.26 (n=517) | 0.43/48.37 (n=4213) |
| impact | 49.46/77.11 (n=357) | 11.66/29.38 (n=699) | 1.11/5.33 (n=5420) |
| recall | 108.84/175.39 (n=1180) | 93.19/169.91 (n=2112) | 2.06/200.79 (n=16672) |
| record_decision | 75.94/145.06 (n=383) | 54.52/107.19 (n=708) | 0.45/63.56 (n=5154) |
| remember_episode | 61.73/97.3 (n=337) | 39.58/84.92 (n=650) | 0.22/62.61 (n=5260) |
| start_session | 60.35/94.81 (n=1445) | 18.37/44.25 (n=2707) | 0.16/48.29 (n=21512) |
| verify_artifact | 60.41/108.31 (n=80) | 18.7/47.74 (n=153) | 0.17/67.68 (n=1017) |
| why | 76.99/131.18 (n=374) | 40.21/100.71 (n=732) | 1.07/4.85 (n=5471) |

### P=200 J-one J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 469.76/791.36 (n=295) | 835.97/1292.24 (n=342) | 0.12/4327.01 (n=1507) |
| assert_fact | 2355.07/3373.61 (n=290) | 2456.75/4177.19 (n=427) | 0.44/10831.8 (n=1494) |
| claim_next_task | 2300.35/2781.89 (n=504) | 871.19/1305.42 (n=700) | 6.12/10513.4 (n=3052) |
| complete_task | 2045.21/2732.6 (n=383) | 799.03/1211.62 (n=594) | 0.14/9317.18 (n=2425) |
| create_tasks | 2279.75/2773.12 (n=97) | 899.84/1285.75 (n=132) | 0.79/11674.4 (n=620) |
| handoff | 2081.1/2708.46 (n=102) | 2365.17/3165.81 (n=212) | 0.28/7459.78 (n=713) |
| impact | 1131.25/1593.34 (n=141) | 4.72/15.09 (n=233) | 0.72/4.33 (n=1003) |
| recall | 1660.08/2304.01 (n=529) | 1683.99/4517.2 (n=808) | 1.15/17303.5 (n=3038) |
| record_decision | 1750.26/2528.18 (n=195) | 2249.11/3151.9 (n=255) | 0.3/12879.4 (n=969) |
| remember_episode | 1664.66/2244.16 (n=237) | 1661.6/2183.02 (n=292) | 0.15/9623.03 (n=928) |
| start_session | 1609.48/2194.68 (n=675) | 827.89/1236.72 (n=931) | 0.1/19789.4 (n=4010) |
| verify_artifact | - | 778.97/1163.85 (n=35) | 0.13/20334.5 (n=171) |
| why | 1082.31/1634.57 (n=140) | 16.11/33.26 (n=200) | 0.6/2.68 (n=972) |

### P=200 J-team J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 133.28/271.68 (n=695) | 120.44/241.78 (n=1455) | 0.34/253.21 (n=16886) |
| assert_fact | 976.21/1390.11 (n=727) | 776.06/1262.47 (n=1497) | 2.2/328.04 (n=16764) |
| claim_next_task | 546.43/743.09 (n=1525) | 122.69/244.21 (n=2989) | 1.39/210.47 (n=33940) |
| complete_task | 551.43/741.17 (n=1262) | 122.25/236.8 (n=2433) | 0.58/284.7 (n=27583) |
| create_tasks | 545.19/726.96 (n=314) | 121.49/250.61 (n=535) | 1.41/237.19 (n=6356) |
| create_tasks_refill | - | - | 0.88/114.16 (n=26) |
| handoff | 520.73/714.98 (n=412) | 341.5/559.74 (n=804) | 1.47/332.58 (n=8509) |
| impact | 405.45/582.29 (n=513) | 113.83/229.55 (n=968) | 1.07/62.45 (n=10934) |
| recall | 816.33/998.88 (n=1649) | 629.61/911 (n=3035) | 5.91/853.01 (n=34032) |
| record_decision | 539.1/736.72 (n=492) | 350.5/582.35 (n=877) | 1.34/327.93 (n=10565) |
| remember_episode | 413.76/603.57 (n=510) | 249.16/411.02 (n=923) | 0.55/315.14 (n=10495) |
| start_session | 409.93/601.96 (n=1962) | 121.58/240.33 (n=3798) | 0.39/273.09 (n=43772) |
| verify_artifact | 410.54/635.49 (n=95) | 119.25/243.48 (n=185) | 0.37/321.93 (n=2104) |
| why | 775.65/1063.69 (n=481) | 449.78/793.17 (n=975) | 1.46/58.12 (n=11094) |

### P=1000 J-one J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 2192.86/12440.2 (n=557) | 9478.22/16905.7 (n=596) | 0.12/28209.7 (n=1539) |
| assert_fact | 4988.84/10442.7 (n=68) | 10613/28004.8 (n=325) | 0.46/22583.9 (n=1456) |
| claim_next_task | 25749.5/26841.5 (n=621) | 8843.28/16798.6 (n=822) | 6.69/36872.7 (n=3132) |
| complete_task | - | 4952.76/13593.7 (n=6) | 0.14/23898.3 (n=2190) |
| create_tasks | 25780/26881.3 (n=311) | 9817.51/16788.6 (n=242) | 0.89/42062.2 (n=705) |
| handoff | - | - | 0.3/21619.2 (n=654) |
| impact | 4527.43/23025 (n=131) | 4.36/11.59 (n=147) | 0.72/6.84 (n=962) |
| recall | 6197.23/19168.8 (n=290) | 12229.7/29413.4 (n=618) | 1.15/31697.7 (n=2903) |
| record_decision | - | 8053.21/23939.1 (n=56) | 0.32/20004.5 (n=881) |
| remember_episode | - | 7253.33/10199.1 (n=2) | 0.15/28211.3 (n=915) |
| start_session | 6641.84/7905.11 (n=846) | 6091.52/16448.4 (n=1047) | 0.11/48072.2 (n=4357) |
| verify_artifact | - | - | 0.14/25943.2 (n=133) |
| why | 4720/23004 (n=118) | 15.73/26.21 (n=118) | 0.63/3.02 (n=923) |

### P=1000 J-team J-trav

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 875.34/1269.83 (n=4138) | 864.2/1614.6 (n=7562) | 1.22/2258.68 (n=11689) |
| assert_fact | 2323.38/4545.09 (n=4187) | 1054.84/1493.26 (n=7470) | 44.17/4068.94 (n=11694) |
| claim_next_task | 1258.35/3999.58 (n=4992) | 883.86/1653.17 (n=9044) | 2.56/2106.4 (n=23316) |
| complete_task | 1328.82/3122.45 (n=270) | 828.18/1811.88 (n=317) | 3.53/4169.07 (n=18840) |
| create_tasks | 1241.65/2876.74 (n=2117) | 872.87/1740.57 (n=3652) | 17.1/2762.15 (n=4474) |
| handoff | 1646.76/4272.44 (n=390) | 1112.83/2771.95 (n=732) | 29.34/3299.02 (n=5740) |
| impact | 1181.86/3931.94 (n=1513) | 867.54/1701.54 (n=2698) | 0.85/98.47 (n=7683) |
| recall | 2229.04/4985.52 (n=3009) | 1725.21/3274.35 (n=5442) | 38.71/6195.77 (n=23462) |
| record_decision | 1502.24/3204.51 (n=486) | 1136.33/2616.07 (n=985) | 29.48/4142.27 (n=7333) |
| remember_episode | 1183.65/4013.31 (n=637) | 954.04/1930.42 (n=1218) | 4.36/4655.97 (n=7279) |
| start_session | 1241.4/3205.31 (n=76330) | 883.9/1676.65 (n=119964) | 1.82/4322.55 (n=30389) |
| verify_artifact | -/- (n=3) | - | 2.26/3521.59 (n=1460) |
| why | 2080.57/4666.41 (n=1550) | 1086.35/1278.39 (n=2787) | 2.39/178.71 (n=7585) |

## Realized mix (share of attempted calls, first repetition)

* P=2 J-one J-trav F-mcp: {'start_session': 18.8, 'recall': 15.5, 'claim_next_task': 14.2, 'complete_task': 11.6, 'add_source': 6.6, 'assert_fact': 6.3, 'record_decision': 5.4, 'impact': 4.8, 'why': 4.7, 'remember_episode': 4.2, 'handoff': 3.7, 'create_tasks': 3.0, 'verify_artifact': 1.2}
* P=2 J-one J-trav F-service: {'start_session': 18.7, 'recall': 15.2, 'claim_next_task': 14.5, 'complete_task': 11.8, 'add_source': 6.8, 'assert_fact': 6.6, 'record_decision': 4.9, 'impact': 4.8, 'remember_episode': 4.5, 'why': 4.5, 'handoff': 3.8, 'create_tasks': 2.8, 'verify_artifact': 1.1}
* P=2 J-one J-trav S-file: {'start_session': 18.8, 'recall': 14.7, 'claim_next_task': 14.4, 'complete_task': 11.8, 'assert_fact': 7.2, 'add_source': 7.2, 'record_decision': 4.9, 'impact': 4.8, 'why': 4.7, 'remember_episode': 4.3, 'handoff': 3.5, 'create_tasks': 2.8, 'verify_artifact': 1.0}
* P=2 J-team J-trav F-mcp: {'start_session': 18.8, 'recall': 15.5, 'claim_next_task': 14.2, 'complete_task': 11.6, 'add_source': 6.6, 'assert_fact': 6.3, 'record_decision': 5.4, 'impact': 4.8, 'why': 4.7, 'remember_episode': 4.2, 'handoff': 3.7, 'create_tasks': 3.0, 'verify_artifact': 1.2}
* P=2 J-team J-trav F-service: {'start_session': 18.7, 'recall': 15.2, 'claim_next_task': 14.5, 'complete_task': 11.7, 'add_source': 6.8, 'assert_fact': 6.6, 'record_decision': 4.9, 'impact': 4.8, 'remember_episode': 4.5, 'why': 4.5, 'handoff': 3.7, 'create_tasks': 2.8, 'verify_artifact': 1.1}
* P=2 J-team J-trav S-file: {'start_session': 18.8, 'recall': 14.6, 'claim_next_task': 14.4, 'complete_task': 11.7, 'assert_fact': 7.2, 'add_source': 7.1, 'record_decision': 4.9, 'why': 4.8, 'impact': 4.7, 'remember_episode': 4.3, 'handoff': 3.5, 'create_tasks': 2.8, 'verify_artifact': 1.0}
* P=20 J-one J-trav F-mcp: {'start_session': 18.6, 'recall': 15.0, 'claim_next_task': 14.9, 'complete_task': 12.1, 'assert_fact': 6.6, 'add_source': 6.4, 'impact': 4.9, 'why': 4.9, 'record_decision': 4.8, 'remember_episode': 4.1, 'handoff': 3.8, 'create_tasks': 3.0, 'verify_artifact': 0.8}
* P=20 J-one J-trav F-service: {'start_session': 18.6, 'claim_next_task': 14.7, 'recall': 14.6, 'complete_task': 11.9, 'assert_fact': 7.1, 'add_source': 7.0, 'why': 5.0, 'impact': 4.8, 'record_decision': 4.4, 'remember_episode': 4.4, 'handoff': 3.9, 'create_tasks': 2.7, 'verify_artifact': 0.8}
* P=20 J-one J-trav S-file: {'start_session': 18.7, 'recall': 14.6, 'claim_next_task': 14.4, 'complete_task': 11.8, 'assert_fact': 7.4, 'add_source': 7.3, 'impact': 4.8, 'why': 4.8, 'remember_episode': 4.6, 'record_decision': 4.5, 'handoff': 3.6, 'create_tasks': 2.7, 'verify_artifact': 1.0}
* P=20 J-team J-trav F-mcp: {'start_session': 18.8, 'recall': 15.4, 'claim_next_task': 14.7, 'complete_task': 11.8, 'add_source': 6.3, 'assert_fact': 6.2, 'record_decision': 5.0, 'why': 4.9, 'impact': 4.6, 'remember_episode': 4.4, 'handoff': 3.9, 'create_tasks': 3.0, 'verify_artifact': 1.0}
* P=20 J-team J-trav F-service: {'start_session': 18.7, 'recall': 14.6, 'claim_next_task': 14.3, 'complete_task': 11.7, 'add_source': 7.0, 'assert_fact': 6.9, 'why': 5.1, 'record_decision': 4.9, 'impact': 4.8, 'remember_episode': 4.5, 'handoff': 3.6, 'create_tasks': 2.8, 'verify_artifact': 1.1}
* P=20 J-team J-trav S-file: {'start_session': 18.8, 'recall': 14.5, 'claim_next_task': 14.5, 'complete_task': 11.8, 'add_source': 7.3, 'assert_fact': 7.2, 'why': 4.8, 'impact': 4.7, 'remember_episode': 4.6, 'record_decision': 4.5, 'handoff': 3.7, 'create_tasks': 2.7, 'verify_artifact': 0.9, 'create_tasks_refill': 0.0}
* P=200 J-one J-trav F-mcp: {'start_session': 18.8, 'recall': 14.7, 'claim_next_task': 14.0, 'complete_task': 10.7, 'add_source': 8.2, 'assert_fact': 8.1, 'remember_episode': 6.6, 'record_decision': 5.4, 'impact': 3.9, 'why': 3.9, 'handoff': 2.8, 'create_tasks': 2.7}
* P=200 J-one J-trav F-service: {'start_session': 18.0, 'recall': 15.7, 'claim_next_task': 13.6, 'complete_task': 11.5, 'assert_fact': 8.3, 'add_source': 6.6, 'remember_episode': 5.7, 'record_decision': 4.9, 'impact': 4.5, 'handoff': 4.1, 'why': 3.9, 'create_tasks': 2.6, 'verify_artifact': 0.7}
* P=200 J-one J-trav S-file: {'start_session': 19.2, 'claim_next_task': 14.6, 'recall': 14.5, 'complete_task': 11.6, 'add_source': 7.2, 'assert_fact': 7.1, 'impact': 4.8, 'why': 4.7, 'record_decision': 4.6, 'remember_episode': 4.4, 'handoff': 3.4, 'create_tasks': 3.0, 'verify_artifact': 0.8}
* P=200 J-team J-trav F-mcp: {'start_session': 18.4, 'recall': 15.5, 'claim_next_task': 14.3, 'complete_task': 11.9, 'assert_fact': 6.8, 'add_source': 6.5, 'impact': 4.8, 'remember_episode': 4.8, 'record_decision': 4.6, 'why': 4.5, 'handoff': 3.9, 'create_tasks': 3.0, 'verify_artifact': 0.9}
* P=200 J-team J-trav F-service: {'start_session': 18.6, 'recall': 14.8, 'claim_next_task': 14.6, 'complete_task': 11.9, 'assert_fact': 7.3, 'add_source': 7.1, 'why': 4.8, 'impact': 4.7, 'remember_episode': 4.5, 'record_decision': 4.3, 'handoff': 3.9, 'create_tasks': 2.6, 'verify_artifact': 0.9}
* P=200 J-team J-trav S-file: {'start_session': 18.8, 'recall': 14.6, 'claim_next_task': 14.6, 'complete_task': 11.8, 'add_source': 7.2, 'assert_fact': 7.2, 'why': 4.8, 'impact': 4.7, 'record_decision': 4.5, 'remember_episode': 4.5, 'handoff': 3.7, 'create_tasks': 2.7, 'verify_artifact': 0.9, 'create_tasks_refill': 0.0}
* P=1000 J-one J-trav F-mcp: {'start_session': 28.8, 'claim_next_task': 21.1, 'add_source': 18.9, 'create_tasks': 10.6, 'recall': 9.9, 'impact': 4.5, 'why': 4.0, 'assert_fact': 2.3}
* P=1000 J-one J-trav F-service: {'start_session': 26.3, 'claim_next_task': 20.7, 'recall': 15.5, 'add_source': 15.0, 'assert_fact': 8.2, 'create_tasks': 6.1, 'impact': 3.7, 'why': 3.0, 'record_decision': 1.4, 'complete_task': 0.2, 'remember_episode': 0.1}
* P=1000 J-one J-trav S-file: {'start_session': 21.0, 'claim_next_task': 15.1, 'recall': 14.0, 'complete_task': 10.6, 'add_source': 7.4, 'assert_fact': 7.0, 'impact': 4.6, 'why': 4.4, 'remember_episode': 4.4, 'record_decision': 4.2, 'create_tasks': 3.4, 'handoff': 3.2, 'verify_artifact': 0.6}
* P=1000 J-team J-trav F-mcp: {'start_session': 76.6, 'claim_next_task': 5.0, 'assert_fact': 4.2, 'add_source': 4.2, 'recall': 3.0, 'create_tasks': 2.1, 'why': 1.6, 'impact': 1.5, 'remember_episode': 0.6, 'record_decision': 0.5, 'handoff': 0.4, 'complete_task': 0.3, 'verify_artifact': 0.0}
* P=1000 J-team J-trav F-service: {'start_session': 74.1, 'claim_next_task': 5.6, 'add_source': 4.7, 'assert_fact': 4.6, 'recall': 3.4, 'create_tasks': 2.3, 'why': 1.7, 'impact': 1.7, 'remember_episode': 0.8, 'record_decision': 0.6, 'handoff': 0.5, 'complete_task': 0.2}
* P=1000 J-team J-trav S-file: {'start_session': 18.9, 'recall': 14.6, 'claim_next_task': 14.5, 'complete_task': 11.7, 'assert_fact': 7.3, 'add_source': 7.3, 'impact': 4.8, 'why': 4.7, 'record_decision': 4.6, 'remember_episode': 4.5, 'handoff': 3.6, 'create_tasks': 2.8, 'verify_artifact': 0.9}

## Recorded mix (pre-registration)

{'start_session': 20, 'recall': 16, 'claim_next_task': 16, 'complete_task': 14, 'add_source': 8, 'assert_fact': 8, 'remember_episode': 5, 'record_decision': 5, 'handoff': 4, 'create_tasks': 3, 'verify_artifact': 1}

## Failures

none

S-shared (optional, J-team): not run.
