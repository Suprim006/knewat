# Crucible L7 family G: multi-tenancy (full-n200, run 20261018T091202Z-g)

## G1 creation latency per tenant (ms) and totals

| N | arm | create p50 | create p99 | create total s | load p50 | load p99 | load total s |
|---|---|---|---|---|---|---|---|
| 1 | F | 199.765 | 199.765 | 0.2 | 186.133 | 186.133 | 0.19 |
| 1 | S-file | 46.017 | 46.017 | 0.05 | 29.411 | 29.411 | 0.03 |
| 1 | S-shared | 0.0 | 0.0 | 0.0 | 5.329 | 5.329 | 0.01 |
| 2 | F | 199.765 | 543.549 | 0.74 | 186.133 | 454.481 | 0.64 |
| 2 | S-file | 18.794 | 46.017 | 0.06 | 16.172 | 29.411 | 0.05 |
| 2 | S-shared | 0.0 | 0.0 | 0.0 | 5.329 | 5.652 | 0.01 |
| 20 | F | 900.042 | 1798.907 | 18.37 | 593.706 | 1480.669 | 13.38 |
| 20 | S-file | 26.481 | 50.681 | 0.57 | 21.115 | 34.614 | 0.47 |
| 20 | S-shared | 0.0 | 0.0 | 0.0 | 6.529 | 29.059 | 0.17 |
| 200 | F | 598.321 | 10325.109 | 220.02 | 468.28 | 5595.206 | 152.85 |
| 200 | S-file | 23.776 | 735.069 | 27.53 | 17.992 | 542.369 | 8.21 |
| 200 | S-shared | 0.0 | 0.0 | 0.0 | 6.134 | 76.21 | 2.42 |

## G2 footprint

Empty (schema only):

* {"tenants": 1, "f_used_memory_delta_per_tenant": 896264, "f_memory_usage_key": {"n": 1, "min": 40, "p50": 40, "mean": 40.0, "max": 40}, "s_file_bytes": {"n": 1, "min": 184320, "p50": 184320, "mean": 184320.0, "max": 184320}}
* {"tenants": 2, "f_used_memory_delta_per_tenant": 820836, "f_memory_usage_key": {"n": 2, "min": 40, "p50": 40, "mean": 40.0, "max": 40}, "s_file_bytes": {"n": 2, "min": 184320, "p50": 184320, "mean": 184320.0, "max": 184320}}
* {"tenants": 20, "f_used_memory_delta_per_tenant": 753083, "f_memory_usage_key": {"n": 20, "min": 40, "p50": 40, "mean": 40.0, "max": 40}, "s_file_bytes": {"n": 20, "min": 184320, "p50": 184320, "mean": 184320.0, "max": 184320}}
* {"tenants": 200, "f_used_memory_delta_per_tenant": 731707, "f_memory_usage_key": {"n": 200, "min": 40, "p50": 40, "mean": 40.0, "max": 40}, "s_file_bytes": {"n": 200, "min": 184320, "p50": 184320, "mean": 184320.0, "max": 184320}, "f_rdb_bytes_per_tenant": 6809}

| N | F used_memory delta/tenant | F RDB/tenant | F MEMORY USAGE loaded p50 | S-file loaded p50 B | S-file empty p50 B | S-shared B/tenant |
|---|---|---|---|---|---|---|
| 1 | 2737520 | 50418 | 40 | 229376 | 184320 | 221184 |
| 2 | -32052820 | 146919 | 40 | 1396736 | 184320 | 454656 |
| 20 | 346446 | 70619 | 40 | 229376 | 184320 | 135373 |
| 200 | 3396685 | 68412 | 40 | 229376 | 184320 | 76984 |

## G3a product-path leakage (leaked rows, gate = 0)

| N | pairs | F | S-file | S-shared | F controls ok |
|---|---|---|---|---|---|
| 2 | 2 | 0 | 0 | 0 | 2/2 |
| 20 | 200 | 0 | 0 | 0 | 200/200 |
| 200 | 200 | 0 | 0 | 0 | 200/200 |

## G3b raw-channel matrix (leaks / blocked of N pairs)

| N | config | leaks | blocked | own ok |
|---|---|---|---|---|
| 2 | F_no_acl | 2 | 0 | 2 |
| 2 | F_acl | 0 | 2 | 2 |
| 2 | S_file_no_authorizer | 2 | 0 | 2 |
| 2 | S_file_authorizer_denies_attach | 0 | 2 | 2 |
| 2 | S_shared_no_protection | 2 | 0 | 2 |
| 2 | S_shared_views_authorizer | 0 | 2 | 2 |
| 20 | F_no_acl | 50 | 0 | 50 |
| 20 | F_acl | 0 | 50 | 50 |
| 20 | S_file_no_authorizer | 50 | 0 | 50 |
| 20 | S_file_authorizer_denies_attach | 0 | 50 | 50 |
| 20 | S_shared_no_protection | 50 | 0 | 50 |
| 20 | S_shared_views_authorizer | 0 | 50 | 50 |
| 200 | F_no_acl | 50 | 0 | 50 |
| 200 | F_acl | 0 | 50 | 50 |
| 200 | S_file_no_authorizer | 50 | 0 | 50 |
| 200 | S_file_authorizer_denies_attach | 0 | 50 | 50 |
| 200 | S_shared_no_protection | 50 | 0 | 50 |
| 200 | S_shared_views_authorizer | 0 | 50 | 50 |

## G4 latency (ms) p50 / p99 per op

| N | arm | q1 | q2 | q3 | q4 | wrong+errors |
|---|---|---|---|---|---|---|
| 1 | F | 2.499 / 5.367 | 2.717 / 12.511 | 2.785 / 9.456 | 9.081 / 183.409 | 0 |
| 1 | S-file-cached | 0.015 / 0.159 | 0.013 / 0.196 | 0.047 / 2.271 | 0.124 / 6.723 | 0 |
| 1 | S-file-open | 6.027 / 105.964 | 5.018 / 153.919 | 5.108 / 40.483 | 19.13 / 224.81 | 0 |
| 1 | S-shared | 0.012 / 0.058 | 0.01 / 0.033 | 0.158 / 0.684 | 0.127 / 11.627 | 0 |
| 2 | F | 2.774 / 20.275 | 2.997 / 55.736 | 3.089 / 26.492 | 6.016 / 35.751 | 0 |
| 2 | S-file-cached | 0.016 / 0.057 | 0.013 / 0.051 | 0.046 / 0.666 | 0.141 / 2.373 | 0 |
| 2 | S-file-open | 4.691 / 14.026 | 4.69 / 15.713 | 4.676 / 28.736 | 18.681 / 99.622 | 0 |
| 2 | S-shared | 0.012 / 0.127 | 0.01 / 0.388 | 0.604 / 18.205 | 0.152 / 6.813 | 0 |
| 20 | F | 5.336 / 216.813 | 2.91 / 8.991 | 2.608 / 5.969 | 5.658 / 151.416 | 0 |
| 20 | S-file-cached | 0.029 / 0.729 | 0.028 / 1.297 | 0.071 / 2.504 | 0.259 / 11.003 | 0 |
| 20 | S-file-open | 5.766 / 36.277 | 5.977 / 100.712 | 5.916 / 53.896 | 11.044 / 69.934 | 0 |
| 20 | S-shared | 0.014 / 0.044 | 0.011 / 0.09 | 0.226 / 12.267 | 0.149 / 10.049 | 0 |
| 200 | F | 7.661 / 97.47 | 8.094 / 60.597 | 7.581 / 70.97 | 7.845 / 35.983 | 0 |
| 200 | S-file-cached | 0.06 / 1.611 | 0.044 / 1.153 | 0.12 / 2.354 | 0.31 / 5.341 | 0 |
| 200 | S-file-open | 8.628 / 30.079 | 9.576 / 49.998 | 13.271 / 54.83 | 12.121 / 26.922 | 0 |
| 200 | S-shared | 0.098 / 8.007 | 0.013 / 1.274 | 0.234 / 10.112 | 0.215 / 18.006 | 0 |

Ratio p50 N_max/N_min: {"N_hi": 200, "N_lo": 1, "F": {"q1": 3.07, "q2": 2.98, "q3": 2.72, "q4": 0.86}, "S-file-cached": {"q1": 4.0, "q2": 3.38, "q3": 2.55, "q4": 2.5}, "S-file-open": {"q1": 1.43, "q2": 1.91, "q3": 2.6, "q4": 0.63}, "S-shared": {"q1": 8.17, "q2": 1.3, "q3": 1.48, "q4": 1.69}}
Tenant handling: {"S-shared_statements": 7, "S-shared_tenant_id_occurrences": 15, "S-file_tenant_predicates": 0}
