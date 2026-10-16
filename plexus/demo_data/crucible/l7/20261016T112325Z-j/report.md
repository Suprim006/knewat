# L7 family J: concurrent session populations (20261016T112325Z-j)

scale `full`; measured 30.0 s after 5.0 s warm-up; reps 3; seed 20261016; embedder `hash` (F); FTS5 (S). Median of repetitions, [min..max] in brackets. Throughput = completed tool calls/s (ok + no_task + claim_conflict).

## Cells

| P | layout | mix | arm | reps ok/run | tput calls/s (excl. refill) | p50 ms | p99 ms | errors | err classes | FalkorDB cpu% mean/max | FalkorDB mem MiB | GRAPH.* cores busy | driver cpu cores | driver peak WS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | J-one | J-real | F-mcp | 3/3 | 110.87 [110.5..112.33] | 14.277 [14.084..14.342] | 47.945 [47.722..48.345] | 0/10017 | - | 87.2/91.4 | 135.3 | 0.9 | 0.47 | 144.7 |
| 2 | J-one | J-real | F-service | 3/3 | 180.2 [168.23..181.47] | 4.808 [4.686..5.027] | 42.54 [41.819..56.899] | 0/15903 | - | 75.2/84.5 | 137.6 | 0.82 | 0.61 | 145 |
| 2 | J-one | J-real | S-file | 3/3 | 1167.17 [1164.23..1179.1] | 0.269 [0.263..0.303] | 31.599 [31.423..32.067] | 0/105321 | - | -/- | - | - | 1.01 | 84.7 |
| 2 | J-team | J-real | F-mcp | 3/3 | 111.83 [110.13..112.37] | 14.129 [14.065..14.356] | 48.155 [46.911..48.406] | 0/10036 | - | 86.7/90.6 | 138 | 0.9 | 0.49 | 144.9 |
| 2 | J-team | J-real | F-service | 3/3 | 179.23 [178.9..183.67] | 4.811 [4.565..4.884] | 42.725 [42.633..43.451] | 0/16260 | - | 72.5/84.3 | 139.1 | 0.82 | 0.61 | 145.2 |
| 2 | J-team | J-real | S-file | 3/3 | 1158.77 [1136.77..1220.63] | 0.263 [0.258..0.277] | 31.744 [31.321..32.02] | 0/105490 | - | -/- | - | - | 1 | 84.3 |
| 20 | J-one | J-real | F-mcp | 3/3 | 158.5 [158.4..160.97] | 130.21 [128.356..131.2] | 208.999 [200.968..210.088] | 0/14396 | - | 139.6/145.9 | 149.6 | 18.02 | 0.69 | 577.5 |
| 20 | J-one | J-real | F-service | 3/3 | 268.27 [262.17..274.67] | 55.515 [53.076..56.107] | 198.258 [190.633..205.859] | 0/24214 | - | 140.5/144.5 | 151.5 | 17.66 | 0.94 | 578.5 |
| 20 | J-one | J-real | S-file | 3/3 | 1125.07 [796.97..1144.8] | 0.269 [0.269..0.369] | 151.915 [140.767..154.92] | 0/92065 | - | -/- | - | - | 1.04 | 334.1 |
| 20 | J-team | J-real | F-mcp | 3/3 | 261.63 [241.83..264.9] | 75.138 [74.786..81.428] | 146.91 [146.471..164.472] | 0/23111 | - | 235.4/244.6 | 167.3 | 12.02 | 1.35 | 578.5 |
| 20 | J-team | J-real | F-service | 3/3 | 473.2 [450.37..487.33] | 26.282 [25.499..27.605] | 137.163 [134.983..146.958] | 0/42386 | - | 255.4/275.3 | 174 | 10.19 | 2.04 | 581.5 |
| 20 | J-team | J-real | S-file | 3/3 | 3939.47 [2731.03..4015.2] | 0.432 [0.4..0.439] | 64.071 [63.086..64.201] | 0/320628 | - | -/- | - | - | 3.84 | 369.6 |
| 200 | J-one | J-real | F-mcp | 3/3 | 111.1 [108.27..111.57] | 1798.28 [1763.27..1870.93] | 3867.49 [3751.41..3933.62] | 0/10528 | - | 131/149.9 | 164.9 | 198.04 | 0.42 | 595.1 |
| 200 | J-one | J-real | F-service | 3/3 | 161.47 [160.23..164.53] | 1031.89 [1023.46..1047.27] | 3325.27 [3301.51..3573.01] | 0/15187 | - | 129.4/138.5 | 155.5 | 199.82 | 0.49 | 597.9 |
| 200 | J-one | J-real | S-file | 3/3 | 691.83 [675.8..710.73] | 0.282 [0.274..0.284] | 13289.9 [12604.8..13538.8] | 0/62951 | - | -/- | - | - | 1.14 | 394.5 |
| 200 | J-team | J-real | F-mcp | 3/3 | 349.4 [347.6..350.87] | 538.476 [537.146..540.336] | 1213.6 [1213.58..1216.84] | 0/32036 | - | 297.1/320.1 | 350.8 | 170.16 | 1.87 | 602 |
| 200 | J-team | J-real | F-service | 3/3 | 672.2 [627.4..677.57] | 146.808 [146.48..163.348] | 1035.26 [996.285..1127.43] | 0/59915 | - | 393.3/429.2 | 371.4 | 153.78 | 3.08 | 607.3 |
| 200 | J-team | J-real | S-file | 3/3 | 11449 [10071.3..11568.4] | 1.071 [1.069..1.077] | 321.907 [314.492..330.284] | 0/993256 | - | -/- | - | - | 10.1 | 557 |
| 1000 | J-one | J-real | F-mcp | 3/3 | 57.23 [46.5..66.83] | 7905.11 [7724.8..9108.11] | 28124 [27275.7..28640.6] | 0/8118 | - | 115.4/144.7 | 178.5 | 1016.81 | 0.34 | 665.4 |
| 1000 | J-one | J-real | F-service | 3/3 | 82 [79.9..83.87] | 9824.88 [9811.63..10247.7] | 29478.2 [29268.6..31216] | 0/10373 | - | 119.4/142 | 161.7 | 1003.77 | 0.37 | 674 |
| 1000 | J-one | J-real | S-file | 3/3 | 649.9 [642.07..653.37] | 0.359 [0.346..0.364] | 39321.8 [38833.4..39520.3] | 0/61359 | - | -/- | - | - | 1.7 | 813.1 |
| 1000 | J-team | J-real | F-mcp | 3/3 | 313.97 [310.43..322.2] | 1232.08 [1214.89..1240.66] | 3201.89 [3159.43..3287.28] | 255343/285575 | max_pending=255304, other=39 | 236.4/258.5 | 646.9 | 501.64 | 5.41 | 725.7 |
| 1000 | J-team | J-real | F-service | 3/3 | 540.33 [508.77..543.27] | 869.715 [848.514..898.855] | 1598.76 [1173.51..1613.4] | 425818/475331 | max_pending=425818 | 211.4/226.7 | 601 | 503.09 | 5.05 | 737.9 |
| 1000 | J-team | J-real | S-file | 3/3 | 7905.03 [7689.97..9848.73] | 7.54 [5.463..8.662] | 2714.81 [2247.72..2872.45] | 0/766313 | - | -/- | - | - | 8.19 | 1021.9 |

## Per-tool latency, p50/p99 ms (median over repetitions)

### P=2 J-one J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 2.49/6.06 (n=776) | 2.51/7.58 (n=1231) | 0.1/11.34 (n=8643) |
| assert_fact | 24.53/34.53 (n=778) | 20.07/31.39 (n=1231) | 0.44/19.53 (n=8643) |
| claim_next_task | 14.66/22.32 (n=1602) | 4.32/9.94 (n=2570) | 1.67/16.26 (n=16815) |
| complete_task | 14.34/20.96 (n=1393) | 3.63/9.49 (n=2233) | 0.14/13.31 (n=14771) |
| create_tasks | 15.99/23.19 (n=299) | 5.71/11.27 (n=459) | 0.72/17.64 (n=3093) |
| create_tasks_refill | 13.74/13.74 (n=1) | 5.05/8.28 (n=14) | - |
| handoff | 13.79/20.72 (n=408) | 9.73/17.03 (n=684) | 0.24/8.9 (n=4163) |
| recall | 39.54/77.77 (n=1641) | 34.27/72.35 (n=2582) | 1.71/63.66 (n=16642) |
| record_decision | 13.93/21.68 (n=515) | 9.92/18.48 (n=758) | 0.26/15.35 (n=5153) |
| remember_episode | 11.15/18.17 (n=497) | 6.7/12.95 (n=813) | 0.14/15.97 (n=5354) |
| start_session | 10.45/17.64 (n=1999) | 2.83/7.27 (n=3179) | 0.09/12.32 (n=21014) |
| verify_artifact | 9.97/16.47 (n=108) | 2.5/5.84 (n=149) | 0.11/8.24 (n=1030) |

### P=2 J-team J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 2.49/6.76 (n=784) | 2.51/7.05 (n=1244) | 0.11/11.32 (n=8519) |
| assert_fact | 24.47/36.17 (n=783) | 20.11/32.42 (n=1246) | 0.43/19.29 (n=8520) |
| claim_next_task | 14.65/22.47 (n=1603) | 4.41/9.55 (n=2613) | 1.85/17.74 (n=16867) |
| complete_task | 14.19/22.65 (n=1392) | 3.58/8.9 (n=2277) | 0.13/13.45 (n=14793) |
| create_tasks | 16.12/24.42 (n=304) | 5.81/10.73 (n=495) | 0.69/16.22 (n=3118) |
| handoff | 13.53/21.55 (n=400) | 9.6/16.82 (n=678) | 0.24/13.73 (n=4222) |
| recall | 39.14/79.56 (n=1639) | 34.37/75.19 (n=2657) | 1.57/64.61 (n=16795) |
| record_decision | 14/21.8 (n=523) | 9.84/18.35 (n=826) | 0.26/17.85 (n=5198) |
| remember_episode | 11.04/18.33 (n=495) | 6.7/12.17 (n=802) | 0.14/12.18 (n=5349) |
| start_session | 10.49/17.2 (n=2004) | 2.87/7.32 (n=3256) | 0.09/6.9 (n=21069) |
| verify_artifact | 10.35/19.63 (n=109) | 2.55/7.54 (n=166) | 0.1/9.16 (n=1040) |

### P=20 J-one J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 33.25/54.21 (n=1110) | 42.04/73.48 (n=1950) | 0.11/41.84 (n=7460) |
| assert_fact | 158.68/240.53 (n=1116) | 147.94/264.78 (n=1953) | 0.43/39.54 (n=7465) |
| claim_next_task | 142.89/194.44 (n=2301) | 46.19/80.34 (n=3832) | 1.88/19.12 (n=14742) |
| complete_task | 142.34/211.43 (n=2015) | 43.96/75.37 (n=3366) | 0.14/58.37 (n=12911) |
| create_tasks | 144.92/202.43 (n=455) | 48.76/84.66 (n=770) | 0.68/31.66 (n=2717) |
| handoff | 132.7/184.09 (n=586) | 118.49/183.35 (n=922) | 0.24/30.78 (n=3701) |
| recall | 134.27/190.61 (n=2334) | 117.97/175.57 (n=3861) | 1.4/2051.42 (n=14661) |
| record_decision | 134.92/188.01 (n=759) | 122.72/190.34 (n=1296) | 0.26/44.87 (n=4504) |
| remember_episode | 105.82/150.12 (n=687) | 88.43/137.32 (n=1171) | 0.13/38.08 (n=4627) |
| start_session | 105.22/155.87 (n=2885) | 42.77/74.73 (n=4832) | 0.09/31.69 (n=18384) |
| verify_artifact | 107.49/153.89 (n=148) | 44.43/86.94 (n=261) | 0.11/34.55 (n=893) |

### P=20 J-team J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 18.67/38.61 (n=1797) | 17.2/42.03 (n=3264) | 0.16/22.47 (n=25696) |
| assert_fact | 109.89/177.07 (n=1807) | 93.71/170.5 (n=3268) | 0.68/33.13 (n=25697) |
| claim_next_task | 80.13/121.3 (n=3675) | 20.9/44.16 (n=6789) | 1.63/26.94 (n=51228) |
| complete_task | 78.13/120.96 (n=3208) | 19.64/43.3 (n=5921) | 0.21/31.7 (n=44905) |
| create_tasks | 79.85/130.19 (n=743) | 22.54/52.29 (n=1295) | 0.83/38.95 (n=9719) |
| create_tasks_refill | - | - | 0.56/0.9 (n=12) |
| handoff | 72.01/118.53 (n=873) | 51.9/101.94 (n=1719) | 0.39/32.22 (n=12751) |
| recall | 105.48/169.04 (n=3749) | 90.81/162.29 (n=6914) | 1.73/265.36 (n=51198) |
| record_decision | 73.19/119.2 (n=1259) | 52.97/105.68 (n=2172) | 0.4/46.48 (n=16125) |
| remember_episode | 60.42/95.77 (n=1103) | 38.96/74.41 (n=2115) | 0.21/46.17 (n=15960) |
| start_session | 58.44/92.22 (n=4639) | 18.25/45.47 (n=8490) | 0.15/26.04 (n=64135) |
| verify_artifact | 59.01/111.02 (n=258) | 16.93/38.2 (n=439) | 0.16/31.69 (n=3202) |

### P=200 J-one J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 417.19/746.97 (n=1001) | 850.11/1367.32 (n=1237) | 0.11/3686.21 (n=5166) |
| assert_fact | 2396.85/3692.61 (n=996) | 2189.76/3937.75 (n=1468) | 0.42/2699.9 (n=5132) |
| claim_next_task | 2432.74/3885.51 (n=1629) | 878.13/1379.43 (n=2235) | 6.03/2166.6 (n=10141) |
| complete_task | 1916.72/2842.34 (n=1252) | 696.24/1246.52 (n=1935) | 0.13/6810.35 (n=8573) |
| create_tasks | 2674.45/3889.85 (n=415) | 851.84/1294.89 (n=437) | 0.79/14146.4 (n=1959) |
| handoff | 1981.54/2532.2 (n=267) | 1963.97/3152.16 (n=593) | 0.25/92.94 (n=2408) |
| recall | 1605.37/2566.69 (n=1584) | 1622.48/4486.4 (n=2481) | 0.91/16638 (n=9947) |
| record_decision | 1854.61/2539.67 (n=623) | 1933.49/3264.85 (n=890) | 0.26/7881.36 (n=3045) |
| remember_episode | 1593.44/2690.64 (n=688) | 1511.53/2236.97 (n=915) | 0.14/6981.77 (n=3184) |
| start_session | 1561.98/2594.66 (n=2073) | 790.48/1255.3 (n=2868) | 0.09/26972 (n=12841) |
| verify_artifact | - | 648.43/1085.18 (n=128) | 0.12/1099.36 (n=555) |

### P=200 J-team J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 133.52/186.23 (n=2558) | 122.6/231.09 (n=4818) | 0.33/174.79 (n=79115) |
| assert_fact | 973.26/1403.22 (n=2624) | 788.92/1225.49 (n=4859) | 1.95/238.47 (n=79130) |
| claim_next_task | 548.46/740.96 (n=5036) | 124.24/241.18 (n=9509) | 1.64/157.7 (n=158779) |
| complete_task | 550.32/745.86 (n=4366) | 123.7/237.54 (n=8301) | 0.51/240.87 (n=138973) |
| create_tasks | 551.62/708.66 (n=954) | 125.9/242.71 (n=1816) | 1.35/185.86 (n=30032) |
| create_tasks_refill | - | - | 0.94/55.73 (n=64) |
| handoff | 523.04/748.97 (n=1303) | 352.53/565.12 (n=2395) | 1.2/217.78 (n=39659) |
| recall | 822.9/1038.83 (n=5202) | 647.09/883.64 (n=9704) | 4.26/816.35 (n=159258) |
| record_decision | 538.1/742.28 (n=1631) | 361.83/586.49 (n=3058) | 1.14/262.15 (n=50022) |
| remember_episode | 415.02/605.85 (n=1770) | 252.37/439.69 (n=2895) | 0.5/238.68 (n=49530) |
| start_session | 414.19/603.43 (n=6281) | 123.18/233.52 (n=11903) | 0.35/210.36 (n=198708) |
| verify_artifact | 415.25/598.86 (n=311) | 122.02/269.66 (n=657) | 0.34/199.81 (n=9986) |

### P=1000 J-one J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 2158.85/10758.4 (n=1529) | 10447.1/17869.2 (n=1990) | 0.12/21198.7 (n=4785) |
| assert_fact | 4018.3/9718.97 (n=163) | 9323.83/24745 (n=735) | 0.44/20515.3 (n=4671) |
| claim_next_task | 25198.1/28153.2 (n=1969) | 10163.6/17818 (n=2632) | 6.88/34282.1 (n=10073) |
| complete_task | - | - | 0.14/18378.6 (n=7558) |
| create_tasks | 27726.6/28160 (n=1042) | 11626/18086.1 (n=840) | 0.87/37724.6 (n=2390) |
| handoff | - | - | 0.26/19661.7 (n=2069) |
| recall | 5228.14/20174.5 (n=876) | 12873.6/30879 (n=1661) | 0.89/32168.9 (n=9502) |
| record_decision | - | 6692.35/6692.35 (n=2) | 0.27/23194.1 (n=3084) |
| remember_episode | - | - | 0.14/21391.3 (n=2852) |
| start_session | 8157.87/9172.96 (n=2539) | 6828.27/17729.2 (n=2513) | 0.1/45813.7 (n=13903) |
| verify_artifact | - | - | 0.13/12090.1 (n=472) |

### P=1000 J-team J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 848.13/1316.4 (n=14584) | 863.47/1518.83 (n=25062) | 1.76/1759.97 (n=60714) |
| assert_fact | 2338.38/4958.34 (n=14796) | 976.5/1515.65 (n=25038) | 26.4/2545.9 (n=60733) |
| claim_next_task | 1238.35/4086.14 (n=16335) | 881.51/1338.89 (n=28813) | 5.55/1462.47 (n=122662) |
| complete_task | 1338.35/3075.4 (n=913) | 865.3/1302.64 (n=943) | 3.93/2376.46 (n=106672) |
| create_tasks | 1258.06/4143.84 (n=7435) | 880.7/1261.52 (n=12671) | 17.64/1812.8 (n=23272) |
| create_tasks_refill | - | - | 85.15/597.98 (n=9) |
| handoff | 1647.17/2774.21 (n=802) | 1090.05/2807.26 (n=1555) | 18.36/2267.58 (n=30576) |
| recall | 2454.66/4040.16 (n=9117) | 1250.13/3390.48 (n=16457) | 33.65/5120.2 (n=123579) |
| record_decision | 1524.72/3849.45 (n=1015) | 1124.75/2421.24 (n=2073) | 17.78/2398.71 (n=38616) |
| remember_episode | 1251.89/3449.41 (n=1225) | 976.62/1819.37 (n=2504) | 4.39/2205.1 (n=38248) |
| start_session | 1260.26/2997.45 (n=219353) | 868.37/1566.28 (n=360213) | 2.37/2226.16 (n=153610) |
| verify_artifact | - | -/- (n=2) | 2.94/2271.4 (n=7622) |

## Realized mix (share of attempted calls, first repetition)

* P=2 J-one J-real F-mcp: {'start_session': 20.1, 'recall': 16.6, 'claim_next_task': 16.0, 'complete_task': 13.8, 'assert_fact': 7.6, 'add_source': 7.5, 'record_decision': 5.3, 'remember_episode': 4.9, 'handoff': 3.9, 'create_tasks': 3.1, 'verify_artifact': 1.1}
* P=2 J-one J-real F-service: {'start_session': 20.1, 'recall': 16.6, 'claim_next_task': 16.1, 'complete_task': 13.9, 'add_source': 7.4, 'assert_fact': 7.4, 'record_decision': 5.3, 'remember_episode': 4.8, 'handoff': 4.2, 'create_tasks': 3.1, 'verify_artifact': 1.1}
* P=2 J-one J-real S-file: {'start_session': 19.9, 'claim_next_task': 15.9, 'recall': 15.6, 'complete_task': 14.0, 'add_source': 8.4, 'assert_fact': 8.4, 'remember_episode': 5.0, 'record_decision': 5.0, 'handoff': 3.8, 'create_tasks': 3.0, 'verify_artifact': 1.0}
* P=2 J-team J-real F-mcp: {'start_session': 20.0, 'recall': 16.6, 'claim_next_task': 16.0, 'complete_task': 13.8, 'add_source': 7.6, 'assert_fact': 7.6, 'record_decision': 5.3, 'remember_episode': 5.0, 'handoff': 4.0, 'create_tasks': 3.0, 'verify_artifact': 1.1}
* P=2 J-team J-real F-service: {'start_session': 20.1, 'recall': 16.7, 'claim_next_task': 16.1, 'complete_task': 13.9, 'assert_fact': 7.3, 'add_source': 7.3, 'record_decision': 5.3, 'remember_episode': 4.8, 'handoff': 4.2, 'create_tasks': 3.1, 'verify_artifact': 1.1}
* P=2 J-team J-real S-file: {'start_session': 20.0, 'claim_next_task': 15.9, 'recall': 15.9, 'complete_task': 14.0, 'add_source': 8.2, 'assert_fact': 8.2, 'record_decision': 5.0, 'remember_episode': 5.0, 'handoff': 3.9, 'create_tasks': 3.0, 'verify_artifact': 1.0}
* P=20 J-one J-real F-mcp: {'start_session': 20.0, 'recall': 16.2, 'claim_next_task': 15.7, 'complete_task': 14.0, 'assert_fact': 7.8, 'add_source': 7.8, 'record_decision': 5.5, 'remember_episode': 4.6, 'handoff': 3.9, 'create_tasks': 3.3, 'verify_artifact': 1.1}
* P=20 J-one J-real F-service: {'start_session': 19.9, 'recall': 16.1, 'claim_next_task': 15.7, 'complete_task': 13.9, 'add_source': 7.9, 'assert_fact': 7.9, 'record_decision': 5.5, 'remember_episode': 4.8, 'handoff': 3.9, 'create_tasks': 3.2, 'verify_artifact': 1.1}
* P=20 J-one J-real S-file: {'start_session': 20.1, 'claim_next_task': 16.0, 'recall': 15.9, 'complete_task': 14.0, 'assert_fact': 8.1, 'add_source': 8.1, 'remember_episode': 5.0, 'record_decision': 4.9, 'handoff': 4.0, 'create_tasks': 3.0, 'verify_artifact': 0.9}
* P=20 J-team J-real F-mcp: {'start_session': 20.2, 'recall': 16.7, 'claim_next_task': 16.2, 'complete_task': 13.9, 'assert_fact': 7.4, 'add_source': 7.3, 'record_decision': 5.2, 'remember_episode': 4.8, 'handoff': 4.2, 'create_tasks': 3.2, 'verify_artifact': 1.0}
* P=20 J-team J-real F-service: {'start_session': 20.1, 'recall': 16.5, 'claim_next_task': 16.1, 'complete_task': 14.0, 'assert_fact': 7.5, 'add_source': 7.5, 'record_decision': 5.1, 'remember_episode': 5.0, 'handoff': 4.2, 'create_tasks': 3.1, 'verify_artifact': 1.0}
* P=20 J-team J-real S-file: {'start_session': 20.0, 'claim_next_task': 16.0, 'recall': 15.9, 'complete_task': 14.0, 'add_source': 8.1, 'assert_fact': 8.1, 'remember_episode': 5.0, 'record_decision': 5.0, 'handoff': 4.0, 'create_tasks': 3.0, 'verify_artifact': 1.0, 'create_tasks_refill': 0.0}
* P=200 J-one J-real F-mcp: {'start_session': 19.4, 'claim_next_task': 15.5, 'recall': 14.8, 'complete_task': 12.3, 'add_source': 9.6, 'assert_fact': 9.4, 'remember_episode': 7.1, 'record_decision': 5.7, 'create_tasks': 3.5, 'handoff': 2.7}
* P=200 J-one J-real F-service: {'start_session': 18.5, 'recall': 16.2, 'claim_next_task': 14.8, 'complete_task': 12.8, 'assert_fact': 9.8, 'add_source': 8.6, 'remember_episode': 6.4, 'record_decision': 5.4, 'handoff': 4.1, 'create_tasks': 2.5, 'verify_artifact': 0.8}
* P=200 J-one J-real S-file: {'start_session': 20.6, 'claim_next_task': 16.1, 'recall': 15.7, 'complete_task': 13.6, 'add_source': 8.2, 'assert_fact': 8.2, 'remember_episode': 5.0, 'record_decision': 4.9, 'handoff': 3.7, 'create_tasks': 3.2, 'verify_artifact': 0.9}
* P=200 J-team J-real F-mcp: {'start_session': 19.7, 'recall': 16.5, 'claim_next_task': 15.9, 'complete_task': 13.7, 'assert_fact': 8.0, 'add_source': 7.8, 'remember_episode': 5.5, 'record_decision': 4.9, 'handoff': 4.3, 'create_tasks': 2.9, 'verify_artifact': 0.9}
* P=200 J-team J-real F-service: {'start_session': 19.9, 'recall': 16.1, 'claim_next_task': 15.9, 'complete_task': 13.8, 'assert_fact': 8.2, 'add_source': 8.1, 'record_decision': 5.1, 'remember_episode': 4.8, 'handoff': 4.0, 'create_tasks': 3.1, 'verify_artifact': 1.1}
* P=200 J-team J-real S-file: {'start_session': 20.0, 'recall': 16.1, 'claim_next_task': 16.0, 'complete_task': 14.0, 'assert_fact': 8.0, 'add_source': 8.0, 'remember_episode': 5.0, 'record_decision': 5.0, 'handoff': 4.0, 'create_tasks': 3.0, 'verify_artifact': 1.0, 'create_tasks_refill': 0.0}
* P=1000 J-one J-real F-mcp: {'start_session': 31.5, 'claim_next_task': 24.2, 'add_source': 18.3, 'create_tasks': 12.7, 'recall': 11.6, 'assert_fact': 1.7}
* P=1000 J-one J-real F-service: {'claim_next_task': 25.0, 'start_session': 22.6, 'add_source': 19.4, 'recall': 17.0, 'assert_fact': 8.4, 'create_tasks': 7.6, 'record_decision': 0.0}
* P=1000 J-one J-real S-file: {'start_session': 22.7, 'claim_next_task': 16.3, 'recall': 15.3, 'complete_task': 12.3, 'add_source': 7.9, 'assert_fact': 7.7, 'record_decision': 5.2, 'remember_episode': 4.5, 'create_tasks': 4.0, 'handoff': 3.2, 'verify_artifact': 0.8}
* P=1000 J-team J-real F-mcp: {'start_session': 77.3, 'claim_next_task': 5.6, 'assert_fact': 5.1, 'add_source': 5.1, 'recall': 3.1, 'create_tasks': 2.6, 'remember_episode': 0.4, 'record_decision': 0.3, 'complete_task': 0.3, 'handoff': 0.3}
* P=1000 J-team J-real F-service: {'start_session': 76.2, 'claim_next_task': 5.9, 'add_source': 5.2, 'assert_fact': 5.2, 'recall': 3.4, 'create_tasks': 2.6, 'remember_episode': 0.5, 'record_decision': 0.4, 'handoff': 0.3, 'complete_task': 0.2, 'verify_artifact': 0.0}
* P=1000 J-team J-real S-file: {'start_session': 20.0, 'recall': 16.0, 'claim_next_task': 16.0, 'complete_task': 13.9, 'assert_fact': 8.0, 'add_source': 8.0, 'remember_episode': 5.0, 'record_decision': 5.0, 'handoff': 4.0, 'create_tasks': 3.0, 'verify_artifact': 1.0, 'create_tasks_refill': 0.0}

## Recorded mix (pre-registration)

{'start_session': 20, 'recall': 16, 'claim_next_task': 16, 'complete_task': 14, 'add_source': 8, 'assert_fact': 8, 'remember_episode': 5, 'record_decision': 5, 'handoff': 4, 'create_tasks': 3, 'verify_artifact': 1}

## Failures

none

S-shared (optional, J-team): not run.
