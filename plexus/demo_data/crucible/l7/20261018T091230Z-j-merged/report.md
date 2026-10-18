# L7 family J: concurrent session populations (20261018T091230Z-j-merged)

scale `full`; measured 30.0 s after 5.0 s warm-up; reps 1; seed 20261016; embedder `hash` (F); FTS5 (S). Median of repetitions, [min..max] in brackets. Throughput = completed tool calls/s (ok + no_task + claim_conflict).

## Cells

| P | layout | mix | arm | reps ok/run | tput calls/s (excl. refill) | p50 ms | p99 ms | errors | err classes | FalkorDB cpu% mean/max | FalkorDB mem MiB | GRAPH.* cores busy | driver cpu cores | driver peak WS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | J-one | J-real | F-mcp | 1/1 | 13.53 | 85.638 | 789.733 | 0/408 | - | 34.8/59.5 | 103.4 | 0.4 | 0.2 | 146.4 |
| 2 | J-one | J-real | F-service | 1/1 | 40.7 | 14.515 | 321.319 | 0/1223 | - | 69.4/76.5 | 118.8 | 0.84 | 0.68 | 150.3 |
| 2 | J-one | J-real | S-file | 1/1 | 795 | 0.574 | 45.31 | 0/23852 | - | -/- | - | - | 0.82 | 82.3 |
| 2 | J-one | J-trav | F-mcp | 1/1 | 17.87 | 73.961 | 471.778 | 0/538 | - | 63.1/74 | 159.2 | 0.73 | 0.23 | 146.6 |
| 2 | J-one | J-trav | F-service | 1/1 | 25.47 | 37.348 | 402.506 | 0/766 | - | 66.2/70.8 | 161.9 | 0.71 | 0.29 | 147.6 |
| 2 | J-one | J-trav | S-file | 1/1 | 516.8 | 0.999 | 54.757 | 0/15506 | - | -/- | - | - | 0.58 | 83.5 |
| 2 | J-team | J-real | F-mcp | 1/1 | 36.17 | 23.876 | 299.312 | 0/1087 | - | 81.8/96 | 115.5 | 0.92 | 0.6 | 149.9 |
| 2 | J-team | J-real | F-service | 1/1 | 27.13 | 15.868 | 813.538 | 0/816 | - | 59.4/83.1 | 113.1 | 0.7 | 0.53 | 149.8 |
| 2 | J-team | J-real | S-file | 1/1 | 606.3 | 0.565 | 53.041 | 0/18191 | - | -/- | - | - | 0.47 | 81.7 |
| 2 | J-team | J-trav | F-mcp | 1/1 | 14.17 | 97.977 | 543.977 | 0/427 | - | 45.8/64 | 155.7 | 0.58 | 0.16 | 145.7 |
| 2 | J-team | J-trav | F-service | 1/1 | 5.7 | 102.701 | 7327.04 | 0/173 | - | 26/28.8 | 151.7 | 0.12 | 0.06 | 144.1 |
| 2 | J-team | J-trav | S-file | 1/1 | 471.27 | 1.128 | 63.09 | 0/14139 | - | -/- | - | - | 0.6 | 82.7 |
| 20 | J-one | J-real | F-mcp | 1/1 | 37.17 | 483.96 | 1487.56 | 0/1135 | - | 115.7/137.6 | 121.5 | 14.87 | 0.7 | 597.3 |
| 20 | J-one | J-real | F-service | 1/1 | 37.97 | 389.134 | 2623.22 | 0/1159 | - | 110.2/137.9 | 121.5 | 10.28 | 0.75 | 605.5 |
| 20 | J-one | J-real | S-file | 1/1 | 531.33 | 0.678 | 1101.61 | 0/15960 | - | -/- | - | - | 0.74 | 326.5 |
| 20 | J-one | J-trav | F-mcp | 1/1 | 30.93 | 585.312 | 1717.89 | 0/948 | - | 107.9/136.9 | 169.7 | 11.31 | 0.39 | 592.5 |
| 20 | J-one | J-trav | F-service | 1/1 | 58.5 | 287.767 | 1197.45 | 0/1775 | - | 128.4/139.6 | 178.7 | 15.27 | 1.02 | 609.3 |
| 20 | J-one | J-trav | S-file | 1/1 | 689.37 | 0.889 | 858.655 | 0/20700 | - | -/- | - | - | 0.96 | 335.6 |
| 20 | J-team | J-real | F-mcp | 1/1 | 87.23 | 186.761 | 776.508 | 0/2637 | - | 197.3/265.6 | 136.9 | 8.88 | 1.26 | 593.7 |
| 20 | J-team | J-real | F-service | 1/1 | 88.37 | 155.516 | 1000.61 | 0/2671 | - | 163.5/211.8 | 159.1 | 6.3 | 1.34 | 600.8 |
| 20 | J-team | J-real | S-file | 1/1 | 2423.3 | 0.862 | 152.78 | 0/72719 | - | -/- | - | - | 2.98 | 347.7 |
| 20 | J-team | J-trav | F-mcp | 1/1 | 52.5 | 321.2 | 1289.18 | 0/1595 | - | 130.2/189.4 | 183 | 6.37 | 0.51 | 585.3 |
| 20 | J-team | J-trav | F-service | 1/1 | 63.53 | 224.713 | 1298.23 | 0/1925 | - | 137.8/225.6 | 220.6 | 4.2 | 0.51 | 587 |
| 20 | J-team | J-trav | S-file | 1/1 | 799.5 | 0.939 | 334.844 | 0/24005 | - | -/- | - | - | 0.94 | 351.3 |
| 200 | J-one | J-real | F-mcp | 1/1 | 22.7 | 8263.81 | 16275 | 0/881 | - | 112.4/124.6 | 143.2 | 190.89 | 0.27 | 610.1 |
| 200 | J-one | J-real | S-file | 1/1 | 202.4 | 1.544 | 19091.8 | 0/6272 | - | -/- | - | - | 0.63 | 379.2 |
| 200 | J-one | J-trav | F-mcp | 1/1 | 49.07 | 4332.41 | 7900.64 | 0/1672 | - | 134.5/159.7 | 209.7 | 198.91 | 0.57 | 616.8 |
| 200 | J-one | J-trav | F-service | 1/1 | 44.6 | 4595.16 | 8787.5 | 0/1538 | - | 136.4/151.7 | 192.6 | 195.62 | 0.47 | 612.9 |
| 200 | J-one | J-trav | S-file | 1/1 | 335.6 | 0.987 | 15339.7 | 0/10267 | - | -/- | - | - | 0.85 | 401.6 |
| 200 | J-team | J-real | F-mcp | 1/1 | 118.97 | 1536.42 | 4079.13 | 0/3769 | - | 241.7/314.4 | 290.8 | 48.96 | 0.92 | 601.5 |
| 200 | J-team | J-real | F-service | 1/1 | 226.4 | 642.439 | 4267.36 | 0/6992 | - | 325.7/498.6 | 298.7 | 90.87 | 1.67 | 613.4 |
| 200 | J-team | J-real | S-file | 1/1 | 9441.1 | 0.783 | 485.043 | 0/283433 | - | -/- | - | - | 6.1 | 569.4 |
| 200 | J-team | J-trav | F-mcp | 1/1 | 122.03 | 1369.83 | 5239.43 | 0/3861 | - | 328/393.3 | 440.9 | 135.77 | 1.01 | 603.9 |
| 200 | J-team | J-trav | F-service | 1/1 | 287.43 | 566.19 | 3039.75 | 0/8823 | - | 421.1/451.2 | 403.7 | 134.92 | 1.97 | 610.3 |
| 200 | J-team | J-trav | S-file | 1/1 | 5042.47 | 0.849 | 508.643 | 0/151474 | - | -/- | - | - | 4.64 | 606.9 |
| 1000 | J-one | J-real | F-mcp | 1/1 | 33.47 | 14567 | 56500.1 | 0/1094 | - | 113.3/126.7 | 182.6 | 750.94 | 0.21 | 656.3 |
| 1000 | J-one | J-trav | S-file | 1/1 | 494.17 | 0.829 | 36923 | 0/15825 | - | -/- | - | - | 1.5 | 802.4 |
| 1000 | J-team | J-real | F-mcp | 1/1 | 175.5 | 2087.37 | 8558.3 | 34831/40765 | max_pending=34831 | 272.3/341.6 | 655.4 | 447.73 | 2.44 | 711 |
| 1000 | J-team | J-real | F-service | 1/1 | 408 | 792.035 | 4891.45 | 34523/47443 | max_pending=34523 | 319.1/457 | 699.2 | 408.25 | 2.61 | 724.2 |
| 1000 | J-team | J-real | S-file | 1/1 | 5040.37 | 2.229 | 5690.87 | 0/152211 | - | -/- | - | - | 4.55 | 968.5 |
| 1000 | J-team | J-trav | F-mcp | 1/1 | 268.3 | 1245.29 | 3685.38 | 64985/73680 | max_pending=64985 | 302.9/386.3 | 923.3 | 504.98 | 4.07 | 719.7 |
| 1000 | J-team | J-trav | F-service | 1/1 | 386.53 | 1059.67 | 2840.52 | 69743/81910 | max_pending=69743 | 320/388.9 | 1070.1 | 487.49 | 2.8 | 718.1 |
| 1000 | J-team | J-trav | S-file | 1/1 | 4038.9 | 1.17 | 6667.24 | 0/122167 | - | -/- | - | - | 3.77 | 1025.6 |
| 200 | J-one | J-real | F-service | 1/1 | 62.57 | 3219.11 | 7895.14 | 0/2077 | - | 142.3/169.4 | 168.2 | 202.23 | 0.7 | 621.5 |
| 1000 | J-one | J-real | F-service | 1/1 | 49.33 | 14806.9 | 32080.9 | 0/2480 | - | 120.1/143.2 | 164.1 | 915.55 | 0.35 | 666.1 |
| 1000 | J-one | J-real | S-file | 1/1 | 187.83 | 23.673 | 42422.9 | 0/6635 | - | -/- | - | - | 1.21 | 678.1 |
| 1000 | J-one | J-trav | F-mcp | 1/1 | 51.8 | 9279.58 | 28304.9 | 0/2554 | - | 117.5/130 | 170.7 | 888.72 | 0.36 | 666.9 |
| 1000 | J-one | J-trav | F-service | 1/1 | 43.07 | 19392 | 38079.6 | 0/2292 | - | 123.8/135 | 163.9 | 746.52 | 0.35 | 665.4 |

## Per-tool latency, p50/p99 ms (median over repetitions)

### P=2 J-one J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 10.37/94.43 (n=18) | 3.94/28.96 (n=87) | 0.21/14.28 (n=1947) |
| assert_fact | 120.06/326.03 (n=18) | 35.03/146.04 (n=87) | 0.9/32.65 (n=1947) |
| claim_next_task | 69.31/416.25 (n=64) | 14.14/101.89 (n=192) | 2.12/28.34 (n=3809) |
| complete_task | 65.85/537.3 (n=56) | 13.9/128.5 (n=168) | 0.3/25.22 (n=3336) |
| create_tasks | 69.03/344.25 (n=19) | 9.89/47.08 (n=41) | 0.86/31.17 (n=721) |
| handoff | 86.22/313.94 (n=16) | 17.9/133.01 (n=49) | 0.53/21.66 (n=928) |
| recall | 335.64/1082.2 (n=79) | 182.83/389.77 (n=208) | 1.84/92.54 (n=3774) |
| record_decision | 67.89/427.83 (n=34) | 17.48/83.58 (n=73) | 0.53/29.21 (n=1192) |
| remember_episode | 45.67/325.06 (n=13) | 10.43/90.63 (n=58) | 0.29/18.56 (n=1188) |
| start_session | 55.87/370.56 (n=84) | 4.32/65.22 (n=244) | 0.21/18.94 (n=4774) |
| verify_artifact | 109.41/178.36 (n=7) | 3.89/56.49 (n=16) | 0.21/5.4 (n=236) |

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

### P=2 J-team J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 3.63/59.21 (n=66) | 3.85/73.34 (n=41) | 0.2/30.94 (n=1421) |
| assert_fact | 40.95/165.4 (n=66) | 35.87/159.22 (n=41) | 0.92/56.95 (n=1424) |
| claim_next_task | 21.98/76.49 (n=173) | 15.41/279.78 (n=132) | 1.45/47.61 (n=2915) |
| complete_task | 21.27/70.11 (n=148) | 15.34/338.37 (n=110) | 0.29/32.02 (n=2534) |
| create_tasks | 22.88/81.36 (n=39) | 9.47/101.78 (n=31) | 0.75/37.03 (n=575) |
| handoff | 22.26/81.91 (n=45) | 18.13/164.57 (n=35) | 0.54/44.42 (n=708) |
| recall | 179.07/355.65 (n=196) | 192.79/1169.41 (n=156) | 1.51/115.12 (n=2932) |
| record_decision | 24.1/138.43 (n=71) | 19.81/537.78 (n=57) | 0.54/30.41 (n=945) |
| remember_episode | 18.18/76.99 (n=48) | 10.78/140.4 (n=34) | 0.28/19.49 (n=885) |
| start_session | 17.11/67.06 (n=220) | 4.28/135.64 (n=166) | 0.2/25.18 (n=3667) |
| verify_artifact | 17.77/42.61 (n=15) | 3.6/130.02 (n=13) | 0.18/18.56 (n=185) |

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

### P=20 J-one J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 128.62/424.27 (n=96) | 150.83/715.82 (n=93) | 0.21/494.2 (n=1310) |
| assert_fact | 698.72/1590.94 (n=96) | 736.6/2255.75 (n=100) | 0.9/273.91 (n=1310) |
| claim_next_task | 453.26/1028.68 (n=184) | 379.07/1208.99 (n=186) | 3.17/129.26 (n=2526) |
| complete_task | 405.66/976.71 (n=163) | 381.9/1328.72 (n=165) | 0.32/677.3 (n=2225) |
| create_tasks | 485.6/953.19 (n=28) | 273.68/741.94 (n=30) | 0.86/434.12 (n=492) |
| handoff | 497.78/1155.45 (n=50) | 439.53/1129.99 (n=54) | 0.57/424.45 (n=608) |
| recall | 707.18/1728.83 (n=180) | 782.24/3403.93 (n=184) | 2.05/2735.39 (n=2531) |
| record_decision | 631.72/1307.25 (n=46) | 610.63/1143.78 (n=48) | 0.53/544.86 (n=828) |
| remember_episode | 398.12/878.51 (n=61) | 353.19/800.51 (n=61) | 0.29/916.6 (n=783) |
| start_session | 418.3/895.57 (n=222) | 170.82/624.24 (n=229) | 0.22/442.86 (n=3180) |
| verify_artifact | 406.76/772.78 (n=9) | 205.53/667.87 (n=9) | 0.21/1380.23 (n=167) |

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

### P=20 J-team J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 36.88/776.51 (n=187) | 46.14/418.95 (n=187) | 0.26/62.13 (n=5844) |
| assert_fact | 269.05/1096.84 (n=188) | 298.01/1250.25 (n=189) | 1.23/86.43 (n=5843) |
| claim_next_task | 178.84/775.16 (n=421) | 161.59/680.58 (n=433) | 2.14/53.38 (n=11644) |
| complete_task | 165.31/456.72 (n=364) | 159.68/620.03 (n=372) | 0.4/92.29 (n=10203) |
| create_tasks | 174.07/1144.12 (n=90) | 101.43/390.29 (n=89) | 1.09/57.45 (n=2117) |
| create_tasks_refill | - | - | 1.04/10.1 (n=6) |
| handoff | 196.21/615.94 (n=106) | 211.53/720.78 (n=113) | 0.75/121.06 (n=2941) |
| recall | 415.11/1836.31 (n=442) | 480.88/1701.38 (n=451) | 3.23/297.66 (n=11614) |
| record_decision | 204.51/1048.83 (n=150) | 206.46/567.3 (n=145) | 0.76/125.12 (n=3543) |
| remember_episode | 158.56/388.06 (n=127) | 119.78/401.07 (n=120) | 0.37/129.12 (n=3733) |
| start_session | 143.16/404.11 (n=532) | 51.33/270.01 (n=542) | 0.26/97.74 (n=14518) |
| verify_artifact | 140.88/380.89 (n=30) | 49.57/188.44 (n=30) | 0.27/68.94 (n=713) |

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

### P=200 J-one J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 1109.59/11408 (n=133) | - | 0.33/11547.6 (n=570) |
| assert_fact | 9506.51/16903 (n=136) | - | 1.54/13839.6 (n=556) |
| claim_next_task | 9649.11/16275 (n=237) | - | 17.7/13995.5 (n=1006) |
| complete_task | 5837.37/6684.31 (n=4) | - | 0.54/14757.5 (n=815) |
| create_tasks | 15779.8/16288.1 (n=82) | - | 2.11/22401.6 (n=199) |
| handoff | - | - | 1.02/10943.6 (n=200) |
| recall | 6824.28/16387.8 (n=133) | - | 3.78/17485.4 (n=943) |
| record_decision | 6624.67/8543.08 (n=23) | - | 0.99/14489.5 (n=301) |
| remember_episode | - | - | 0.47/10613.8 (n=345) |
| start_session | 7438.71/15646.5 (n=133) | - | 0.33/30019 (n=1294) |
| verify_artifact | - | - | 0.46/9762.05 (n=43) |

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

### P=200 J-team J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 300.78/873.92 (n=328) | 215.99/1109.99 (n=567) | 0.26/209.96 (n=22658) |
| assert_fact | 2474.82/4319.06 (n=387) | 1352.48/4080.95 (n=579) | 1.35/519.87 (n=22663) |
| claim_next_task | 1518.83/2587.61 (n=517) | 666.59/2112.94 (n=1132) | 1/256.21 (n=45368) |
| complete_task | 1366.22/2627.33 (n=531) | 644.28/2100.16 (n=950) | 0.4/362.72 (n=39644) |
| create_tasks | 1862.85/2524.01 (n=101) | 465.08/1736.29 (n=189) | 0.93/404.12 (n=8513) |
| create_tasks_refill | - | - | 1.22/48.11 (n=13) |
| handoff | 1234.32/2775.07 (n=148) | 802.18/3133.31 (n=299) | 0.88/382.67 (n=11366) |
| recall | 2933.91/4572.42 (n=561) | 1645.14/5321.78 (n=1133) | 1.61/1175.62 (n=45380) |
| record_decision | 1921.82/3171.99 (n=213) | 883.82/2844.49 (n=316) | 0.8/505.71 (n=14140) |
| remember_episode | 1320.34/2398.23 (n=291) | 420.77/1549.36 (n=429) | 0.4/361.24 (n=14169) |
| start_session | 1127.92/2203.63 (n=692) | 229.61/1137.23 (n=1344) | 0.29/328.1 (n=56705) |
| verify_artifact | - | 238.92/569.72 (n=54) | 0.26/308.22 (n=2814) |

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

### P=1000 J-one J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 18670.5/21196.7 (n=13) | - | - |
| claim_next_task | 39474.4/56830.8 (n=74) | - | - |
| create_tasks | 40203.4/57122.5 (n=47) | - | - |
| start_session | 14196.9/20066 (n=960) | - | - |

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

### P=1000 J-team J-real

| tool | F-mcp | F-service | S-file |
|---|---|---|---|
| add_source | 1036.13/2111.92 (n=2749) | 721.46/1664.72 (n=4174) | 0.77/1876.81 (n=12200) |
| assert_fact | 4706.49/9812.59 (n=2673) | 4278.28/9108.27 (n=4295) | 8.9/5476.6 (n=12168) |
| claim_next_task | 3874.02/9172.33 (n=3152) | 1991.93/3958.68 (n=5587) | 1.71/2179.36 (n=24387) |
| complete_task | 3187.49/6301.38 (n=89) | 1829.42/2427.63 (n=828) | 1.47/5435.6 (n=20866) |
| create_tasks | 3899.09/9067.19 (n=1445) | 1454.77/2685.57 (n=1968) | 4.56/5449.97 (n=4791) |
| handoff | 3975.86/8814.04 (n=160) | 2794.52/4670.31 (n=692) | 4.92/3012.55 (n=5914) |
| recall | 4730.73/10394.6 (n=1729) | 3911.32/7759.62 (n=3819) | 4.11/8324.01 (n=24316) |
| record_decision | 4083.76/7970.63 (n=208) | 2700.12/4951.48 (n=975) | 5.07/4736.57 (n=7686) |
| remember_episode | 1943.46/8807.02 (n=248) | 1128.76/2197.51 (n=1228) | 1.61/3727.37 (n=7629) |
| start_session | 2132.05/8382.36 (n=28311) | 727.01/1537.84 (n=23868) | 0.99/7546.14 (n=30806) |
| verify_artifact | -/- (n=1) | 573.47/938.57 (n=9) | 1.18/2959.32 (n=1448) |

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
| add_source | - | 11016.5/17856.9 (n=524) | 0.49/32239.5 (n=564) |
| assert_fact | - | 11859.6/31509.5 (n=46) | 2.75/32253.9 (n=503) |
| claim_next_task | - | 19109.2/28728.1 (n=972) | 27.28/37060 (n=1146) |
| complete_task | - | - | 1.02/29141.1 (n=605) |
| create_tasks | - | 7581.8/11374.9 (n=246) | 237.22/39324.6 (n=356) |
| handoff | - | - | 1.54/29483.5 (n=144) |
| recall | - | 17425.2/32807.3 (n=364) | 494.51/37302.9 (n=904) |
| record_decision | - | - | 2.85/33856.2 (n=262) |
| remember_episode | - | - | 0.8/21158.6 (n=300) |
| start_session | - | 14286.8/18023.9 (n=328) | 4690.91/45016 (n=1841) |
| verify_artifact | - | - | 1.45/8088.1 (n=10) |

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

* P=2 J-one J-real F-mcp: {'start_session': 20.6, 'recall': 19.4, 'claim_next_task': 15.7, 'complete_task': 13.7, 'record_decision': 8.3, 'create_tasks': 4.7, 'assert_fact': 4.4, 'add_source': 4.4, 'handoff': 3.9, 'remember_episode': 3.2, 'verify_artifact': 1.7}
* P=2 J-one J-real F-service: {'start_session': 20.0, 'recall': 17.0, 'claim_next_task': 15.7, 'complete_task': 13.7, 'add_source': 7.1, 'assert_fact': 7.1, 'record_decision': 6.0, 'remember_episode': 4.7, 'handoff': 4.0, 'create_tasks': 3.4, 'verify_artifact': 1.3}
* P=2 J-one J-real S-file: {'start_session': 20.0, 'claim_next_task': 16.0, 'recall': 15.8, 'complete_task': 14.0, 'add_source': 8.2, 'assert_fact': 8.2, 'record_decision': 5.0, 'remember_episode': 5.0, 'handoff': 3.9, 'create_tasks': 3.0, 'verify_artifact': 1.0}
* P=2 J-one J-trav F-mcp: {'start_session': 19.3, 'recall': 17.1, 'claim_next_task': 15.2, 'complete_task': 13.0, 'handoff': 5.8, 'why': 5.0, 'remember_episode': 5.0, 'add_source': 4.6, 'impact': 4.5, 'assert_fact': 3.7, 'record_decision': 3.3, 'create_tasks': 2.8, 'verify_artifact': 0.6}
* P=2 J-one J-trav F-service: {'start_session': 19.3, 'recall': 16.8, 'claim_next_task': 14.6, 'complete_task': 12.3, 'impact': 5.1, 'add_source': 5.0, 'record_decision': 4.8, 'why': 4.8, 'handoff': 4.8, 'assert_fact': 4.2, 'remember_episode': 3.9, 'create_tasks': 3.5, 'verify_artifact': 0.8}
* P=2 J-one J-trav S-file: {'start_session': 18.5, 'claim_next_task': 14.3, 'recall': 14.0, 'complete_task': 12.0, 'assert_fact': 8.1, 'add_source': 7.9, 'why': 4.8, 'impact': 4.6, 'remember_episode': 4.6, 'record_decision': 4.5, 'handoff': 3.3, 'create_tasks': 2.6, 'verify_artifact': 0.9}
* P=2 J-team J-real F-mcp: {'start_session': 20.2, 'recall': 18.0, 'claim_next_task': 15.9, 'complete_task': 13.6, 'record_decision': 6.5, 'add_source': 6.1, 'assert_fact': 6.1, 'remember_episode': 4.4, 'handoff': 4.1, 'create_tasks': 3.6, 'verify_artifact': 1.4}
* P=2 J-team J-real F-service: {'start_session': 20.3, 'recall': 19.1, 'claim_next_task': 16.2, 'complete_task': 13.5, 'record_decision': 7.0, 'add_source': 5.0, 'assert_fact': 5.0, 'handoff': 4.3, 'remember_episode': 4.2, 'create_tasks': 3.8, 'verify_artifact': 1.6}
* P=2 J-team J-real S-file: {'start_session': 20.2, 'recall': 16.1, 'claim_next_task': 16.0, 'complete_task': 13.9, 'assert_fact': 7.8, 'add_source': 7.8, 'record_decision': 5.2, 'remember_episode': 4.9, 'handoff': 3.9, 'create_tasks': 3.2, 'verify_artifact': 1.0}
* P=2 J-team J-trav F-mcp: {'recall': 17.8, 'start_session': 17.8, 'claim_next_task': 15.7, 'complete_task': 14.1, 'handoff': 7.0, 'remember_episode': 5.6, 'why': 4.9, 'impact': 4.4, 'add_source': 4.4, 'assert_fact': 3.5, 'record_decision': 2.3, 'create_tasks': 1.9, 'verify_artifact': 0.5}
* P=2 J-team J-trav F-service: {'start_session': 18.5, 'recall': 15.0, 'claim_next_task': 15.0, 'complete_task': 13.3, 'add_source': 7.5, 'assert_fact': 5.8, 'why': 5.8, 'handoff': 5.2, 'impact': 4.0, 'remember_episode': 4.0, 'record_decision': 3.5, 'create_tasks': 1.7, 'verify_artifact': 0.6}
* P=2 J-team J-trav S-file: {'start_session': 18.5, 'recall': 14.3, 'claim_next_task': 14.2, 'complete_task': 11.8, 'assert_fact': 7.8, 'add_source': 7.6, 'why': 4.9, 'record_decision': 4.7, 'impact': 4.7, 'remember_episode': 4.4, 'handoff': 3.3, 'create_tasks': 2.8, 'verify_artifact': 1.0}
* P=20 J-one J-real F-mcp: {'start_session': 19.6, 'claim_next_task': 16.2, 'recall': 15.9, 'complete_task': 14.4, 'add_source': 8.5, 'assert_fact': 8.5, 'remember_episode': 5.4, 'handoff': 4.4, 'record_decision': 4.1, 'create_tasks': 2.5, 'verify_artifact': 0.8}
* P=20 J-one J-real F-service: {'start_session': 19.8, 'claim_next_task': 16.0, 'recall': 15.9, 'complete_task': 14.2, 'assert_fact': 8.6, 'add_source': 8.0, 'remember_episode': 5.3, 'handoff': 4.7, 'record_decision': 4.1, 'create_tasks': 2.6, 'verify_artifact': 0.8}
* P=20 J-one J-real S-file: {'start_session': 19.9, 'recall': 15.9, 'claim_next_task': 15.8, 'complete_task': 13.9, 'add_source': 8.2, 'assert_fact': 8.2, 'record_decision': 5.2, 'remember_episode': 4.9, 'handoff': 3.8, 'create_tasks': 3.1, 'verify_artifact': 1.0}
* P=20 J-one J-trav F-mcp: {'start_session': 17.6, 'recall': 13.8, 'claim_next_task': 13.7, 'complete_task': 11.7, 'add_source': 7.9, 'assert_fact': 7.6, 'record_decision': 5.5, 'remember_episode': 5.1, 'impact': 5.0, 'why': 4.4, 'handoff': 3.6, 'create_tasks': 3.1, 'verify_artifact': 1.1}
* P=20 J-one J-trav F-service: {'start_session': 18.6, 'recall': 14.9, 'claim_next_task': 14.8, 'complete_task': 12.1, 'assert_fact': 7.4, 'add_source': 7.2, 'why': 4.7, 'impact': 4.5, 'remember_episode': 4.5, 'record_decision': 4.2, 'handoff': 3.7, 'create_tasks': 2.5, 'verify_artifact': 0.7}
* P=20 J-one J-trav S-file: {'start_session': 18.6, 'claim_next_task': 14.6, 'recall': 14.1, 'complete_task': 11.9, 'assert_fact': 7.7, 'add_source': 7.6, 'why': 4.9, 'remember_episode': 4.7, 'impact': 4.6, 'record_decision': 4.2, 'handoff': 3.6, 'create_tasks': 2.5, 'verify_artifact': 0.9}
* P=20 J-team J-real F-mcp: {'start_session': 20.2, 'recall': 16.8, 'claim_next_task': 16.0, 'complete_task': 13.8, 'assert_fact': 7.1, 'add_source': 7.1, 'record_decision': 5.7, 'remember_episode': 4.8, 'handoff': 4.0, 'create_tasks': 3.4, 'verify_artifact': 1.1}
* P=20 J-team J-real F-service: {'start_session': 20.3, 'recall': 16.9, 'claim_next_task': 16.2, 'complete_task': 13.9, 'assert_fact': 7.1, 'add_source': 7.0, 'record_decision': 5.4, 'remember_episode': 4.5, 'handoff': 4.2, 'create_tasks': 3.3, 'verify_artifact': 1.1}
* P=20 J-team J-real S-file: {'start_session': 20.0, 'claim_next_task': 16.0, 'recall': 16.0, 'complete_task': 14.0, 'add_source': 8.0, 'assert_fact': 8.0, 'remember_episode': 5.1, 'record_decision': 4.9, 'handoff': 4.0, 'create_tasks': 2.9, 'verify_artifact': 1.0, 'create_tasks_refill': 0.0}
* P=20 J-team J-trav F-mcp: {'start_session': 18.1, 'recall': 15.3, 'claim_next_task': 14.9, 'complete_task': 12.7, 'assert_fact': 7.4, 'add_source': 7.1, 'impact': 4.7, 'remember_episode': 4.4, 'record_decision': 4.3, 'why': 3.9, 'handoff': 3.7, 'create_tasks': 2.5, 'verify_artifact': 0.9}
* P=20 J-team J-trav F-service: {'start_session': 18.1, 'recall': 14.9, 'claim_next_task': 14.7, 'complete_task': 12.3, 'assert_fact': 7.5, 'add_source': 7.4, 'remember_episode': 4.6, 'record_decision': 4.5, 'impact': 4.3, 'why': 4.2, 'handoff': 4.0, 'create_tasks': 2.6, 'verify_artifact': 0.8}
* P=20 J-team J-trav S-file: {'start_session': 18.7, 'claim_next_task': 14.5, 'recall': 14.2, 'complete_task': 11.9, 'add_source': 7.7, 'assert_fact': 7.6, 'remember_episode': 4.8, 'impact': 4.8, 'why': 4.6, 'record_decision': 4.2, 'handoff': 3.7, 'create_tasks': 2.5, 'verify_artifact': 0.8, 'create_tasks_refill': 0.0}
* P=200 J-one J-real F-mcp: {'claim_next_task': 26.9, 'assert_fact': 15.4, 'start_session': 15.1, 'recall': 15.1, 'add_source': 15.1, 'create_tasks': 9.3, 'record_decision': 2.6, 'complete_task': 0.5}
* P=200 J-one J-real S-file: {'start_session': 20.6, 'claim_next_task': 16.0, 'recall': 15.0, 'complete_task': 13.0, 'add_source': 9.1, 'assert_fact': 8.9, 'remember_episode': 5.5, 'record_decision': 4.8, 'handoff': 3.2, 'create_tasks': 3.2, 'verify_artifact': 0.7}
* P=200 J-one J-trav F-mcp: {'claim_next_task': 18.7, 'start_session': 17.6, 'recall': 13.1, 'complete_task': 9.5, 'add_source': 8.7, 'assert_fact': 8.6, 'create_tasks': 5.5, 'record_decision': 5.2, 'remember_episode': 4.1, 'why': 3.7, 'impact': 3.4, 'handoff': 1.9}
* P=200 J-one J-trav F-service: {'start_session': 16.8, 'claim_next_task': 16.6, 'recall': 15.2, 'complete_task': 10.5, 'add_source': 9.8, 'assert_fact': 9.8, 'record_decision': 6.7, 'remember_episode': 3.6, 'why': 3.6, 'impact': 3.2, 'create_tasks': 2.3, 'handoff': 2.0}
* P=200 J-one J-trav S-file: {'start_session': 19.3, 'recall': 14.8, 'claim_next_task': 14.6, 'complete_task': 11.5, 'add_source': 7.2, 'assert_fact': 7.1, 'remember_episode': 4.8, 'record_decision': 4.7, 'impact': 4.5, 'why': 4.4, 'handoff': 3.5, 'create_tasks': 3.0, 'verify_artifact': 0.7}
* P=200 J-team J-real F-mcp: {'start_session': 18.4, 'recall': 14.9, 'complete_task': 14.1, 'claim_next_task': 13.7, 'assert_fact': 10.3, 'add_source': 8.7, 'remember_episode': 7.7, 'record_decision': 5.7, 'handoff': 3.9, 'create_tasks': 2.7}
* P=200 J-team J-real F-service: {'start_session': 19.2, 'recall': 16.2, 'claim_next_task': 16.2, 'complete_task': 13.6, 'assert_fact': 8.3, 'add_source': 8.1, 'remember_episode': 6.1, 'record_decision': 4.5, 'handoff': 4.3, 'create_tasks': 2.7, 'verify_artifact': 0.8}
* P=200 J-team J-real S-file: {'start_session': 20.0, 'recall': 16.0, 'claim_next_task': 16.0, 'complete_task': 14.0, 'assert_fact': 8.0, 'add_source': 8.0, 'remember_episode': 5.0, 'record_decision': 5.0, 'handoff': 4.0, 'create_tasks': 3.0, 'verify_artifact': 1.0, 'create_tasks_refill': 0.0}
* P=200 J-team J-trav F-mcp: {'start_session': 17.7, 'recall': 15.2, 'claim_next_task': 13.5, 'complete_task': 12.0, 'assert_fact': 8.0, 'remember_episode': 6.9, 'add_source': 6.7, 'record_decision': 5.4, 'why': 4.1, 'impact': 4.0, 'handoff': 3.7, 'create_tasks': 2.5, 'verify_artifact': 0.3}
* P=200 J-team J-trav F-service: {'start_session': 18.6, 'recall': 15.2, 'claim_next_task': 14.2, 'complete_task': 12.4, 'assert_fact': 6.8, 'add_source': 6.4, 'remember_episode': 5.4, 'record_decision': 4.7, 'impact': 4.7, 'why': 4.1, 'handoff': 3.8, 'create_tasks': 2.9, 'verify_artifact': 0.7}
* P=200 J-team J-trav S-file: {'start_session': 18.8, 'recall': 14.6, 'claim_next_task': 14.5, 'complete_task': 11.8, 'add_source': 7.2, 'assert_fact': 7.1, 'why': 4.8, 'impact': 4.7, 'record_decision': 4.6, 'remember_episode': 4.5, 'handoff': 3.6, 'create_tasks': 2.8, 'verify_artifact': 0.9, 'create_tasks_refill': 0.0}
* P=1000 J-one J-real F-mcp: {'start_session': 87.8, 'claim_next_task': 6.8, 'create_tasks': 4.3, 'add_source': 1.2}
* P=1000 J-one J-trav S-file: {'start_session': 21.7, 'claim_next_task': 15.2, 'recall': 13.7, 'complete_task': 10.0, 'add_source': 7.6, 'assert_fact': 7.1, 'remember_episode': 4.5, 'why': 4.5, 'impact': 4.4, 'record_decision': 4.2, 'create_tasks': 3.5, 'handoff': 2.9, 'verify_artifact': 0.6}
* P=1000 J-team J-real F-mcp: {'start_session': 69.4, 'claim_next_task': 7.7, 'add_source': 6.7, 'assert_fact': 6.6, 'recall': 4.2, 'create_tasks': 3.5, 'remember_episode': 0.6, 'record_decision': 0.5, 'handoff': 0.4, 'complete_task': 0.2, 'verify_artifact': 0.0}
* P=1000 J-team J-real F-service: {'start_session': 50.3, 'claim_next_task': 11.8, 'assert_fact': 9.1, 'add_source': 8.8, 'recall': 8.0, 'create_tasks': 4.1, 'remember_episode': 2.6, 'record_decision': 2.1, 'complete_task': 1.7, 'handoff': 1.5, 'verify_artifact': 0.0}
* P=1000 J-team J-real S-file: {'start_session': 20.2, 'claim_next_task': 16.0, 'recall': 16.0, 'complete_task': 13.7, 'add_source': 8.0, 'assert_fact': 8.0, 'record_decision': 5.0, 'remember_episode': 5.0, 'handoff': 3.9, 'create_tasks': 3.1, 'verify_artifact': 1.0}
* P=1000 J-team J-trav F-mcp: {'start_session': 72.7, 'claim_next_task': 5.9, 'assert_fact': 4.8, 'add_source': 4.7, 'recall': 3.7, 'create_tasks': 2.5, 'why': 1.8, 'impact': 1.8, 'remember_episode': 0.8, 'record_decision': 0.7, 'handoff': 0.5, 'complete_task': 0.1}
* P=1000 J-team J-trav F-service: {'start_session': 64.9, 'claim_next_task': 7.6, 'assert_fact': 6.0, 'add_source': 5.8, 'recall': 4.9, 'create_tasks': 2.8, 'impact': 2.3, 'why': 2.3, 'remember_episode': 1.3, 'record_decision': 1.0, 'handoff': 0.8, 'complete_task': 0.2, 'verify_artifact': 0.0}
* P=1000 J-team J-trav S-file: {'start_session': 19.0, 'claim_next_task': 14.5, 'recall': 14.2, 'complete_task': 11.6, 'assert_fact': 7.5, 'add_source': 7.5, 'why': 4.8, 'impact': 4.7, 'remember_episode': 4.5, 'record_decision': 4.5, 'handoff': 3.5, 'create_tasks': 2.8, 'verify_artifact': 0.8}
* P=200 J-one J-real F-service: {'claim_next_task': 19.1, 'start_session': 18.2, 'recall': 15.7, 'add_source': 10.3, 'assert_fact': 9.8, 'complete_task': 9.6, 'record_decision': 7.1, 'remember_episode': 5.5, 'create_tasks': 3.4, 'handoff': 1.5}
* P=1000 J-one J-real F-service: {'claim_next_task': 39.2, 'add_source': 21.1, 'recall': 14.7, 'start_session': 13.2, 'create_tasks': 9.9, 'assert_fact': 1.9}
* P=1000 J-one J-real S-file: {'start_session': 27.7, 'claim_next_task': 17.3, 'recall': 13.6, 'complete_task': 9.1, 'add_source': 8.5, 'assert_fact': 7.6, 'create_tasks': 5.4, 'remember_episode': 4.5, 'record_decision': 3.9, 'handoff': 2.2, 'verify_artifact': 0.2}
* P=1000 J-one J-trav F-mcp: {'start_session': 37.9, 'claim_next_task': 23.0, 'create_tasks': 12.1, 'add_source': 11.2, 'recall': 7.4, 'impact': 3.9, 'why': 3.9, 'assert_fact': 0.7}
* P=1000 J-one J-trav F-service: {'claim_next_task': 36.9, 'start_session': 17.7, 'add_source': 15.4, 'recall': 11.8, 'create_tasks': 10.6, 'impact': 3.0, 'why': 2.4, 'assert_fact': 2.1, 'record_decision': 0.1, 'complete_task': 0.0}

## Recorded mix (pre-registration)

{'start_session': 20, 'recall': 16, 'claim_next_task': 16, 'complete_task': 14, 'add_source': 8, 'assert_fact': 8, 'remember_episode': 5, 'record_decision': 5, 'handoff': 4, 'create_tasks': 3, 'verify_artifact': 1}

## Failures

none

S-shared (optional, J-team): not run.
