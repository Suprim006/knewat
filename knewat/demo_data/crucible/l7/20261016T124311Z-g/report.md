# Crucible L7 family G: multi-tenancy (full, run 20261016T124311Z-g)

## G1 creation latency per tenant (ms) and totals

| N | arm | create p50 | create p99 | create total s | load p50 | load p99 | load total s |
|---|---|---|---|---|---|---|---|
| 1 | F | 138.055 | 138.055 | 0.14 | 146.251 | 146.251 | 0.15 |
| 1 | S-file | 12.072 | 12.072 | 0.01 | 9.229 | 9.229 | 0.01 |
| 1 | S-shared | 0.0 | 0.0 | 0.0 | 2.99 | 2.99 | 0.0 |
| 2 | F | 133.144 | 138.055 | 0.27 | 139.14 | 146.251 | 0.29 |
| 2 | S-file | 12.072 | 19.517 | 0.03 | 9.2 | 9.229 | 0.02 |
| 2 | S-shared | 0.0 | 0.0 | 0.0 | 2.831 | 2.99 | 0.01 |
| 20 | F | 133.144 | 139.911 | 2.68 | 136.959 | 146.251 | 2.75 |
| 20 | S-file | 12.978 | 22.571 | 0.32 | 9.2 | 11.576 | 0.19 |
| 20 | S-shared | 0.0 | 0.0 | 0.0 | 2.987 | 10.764 | 0.08 |
| 200 | F | 134.836 | 152.123 | 27.07 | 136.959 | 154.083 | 27.63 |
| 200 | S-file | 15.122 | 22.941 | 3.28 | 9.464 | 13.99 | 1.97 |
| 200 | S-shared | 0.0 | 0.0 | 0.0 | 3.11 | 15.222 | 0.84 |

## G2 footprint

Empty (schema only):

* {"tenants": 1, "f_used_memory_delta_per_tenant": 728800, "f_memory_usage_key": {"n": 1, "min": 40, "p50": 40, "mean": 40.0, "max": 40}, "s_file_bytes": {"n": 1, "min": 184320, "p50": 184320, "mean": 184320.0, "max": 184320}}
* {"tenants": 2, "f_used_memory_delta_per_tenant": 737068, "f_memory_usage_key": {"n": 2, "min": 40, "p50": 40, "mean": 40.0, "max": 40}, "s_file_bytes": {"n": 2, "min": 184320, "p50": 184320, "mean": 184320.0, "max": 184320}}
* {"tenants": 20, "f_used_memory_delta_per_tenant": 743577, "f_memory_usage_key": {"n": 20, "min": 40, "p50": 40, "mean": 40.0, "max": 40}, "s_file_bytes": {"n": 20, "min": 184320, "p50": 184320, "mean": 184320.0, "max": 184320}}
* {"tenants": 200, "f_used_memory_delta_per_tenant": 744211, "f_memory_usage_key": {"n": 200, "min": 40, "p50": 40, "mean": 40.0, "max": 40}, "s_file_bytes": {"n": 200, "min": 184320, "p50": 184320, "mean": 184320.0, "max": 184320}, "f_rdb_bytes_per_tenant": 6644}

| N | F used_memory delta/tenant | F RDB/tenant | F MEMORY USAGE loaded p50 | S-file loaded p50 B | S-file empty p50 B | S-shared B/tenant |
|---|---|---|---|---|---|---|
| 1 | 3525584 | 50388 | 40 | 229376 | 184320 | 221184 |
| 2 | -32627384 | 145270 | 40 | 1396736 | 184320 | 454656 |
| 20 | 98854 | 69990 | 40 | 229376 | 184320 | 135373 |
| 200 | 3363090 | 68893 | 40 | 229376 | 184320 | 76984 |

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
| 1 | F | 1.708 / 2.402 | 1.738 / 2.362 | 1.803 / 2.45 | 3.07 / 4.274 | 0 |
| 1 | S-file-cached | 0.008 / 0.024 | 0.007 / 0.016 | 0.024 / 0.067 | 0.06 / 0.732 | 0 |
| 1 | S-file-open | 2.479 / 4.498 | 2.43 / 3.671 | 2.598 / 4.542 | 7.151 / 10.059 | 0 |
| 1 | S-shared | 0.007 / 0.012 | 0.006 / 0.013 | 0.093 / 0.269 | 0.065 / 0.792 | 0 |
| 2 | F | 1.673 / 2.357 | 1.719 / 2.391 | 1.822 / 2.591 | 3.613 / 5.04 | 0 |
| 2 | S-file-cached | 0.009 / 0.033 | 0.008 / 0.03 | 0.026 / 0.097 | 0.069 / 0.756 | 0 |
| 2 | S-file-open | 2.598 / 4.127 | 2.561 / 5.112 | 2.562 / 4.063 | 7.072 / 9.853 | 0 |
| 2 | S-shared | 0.007 / 0.015 | 0.006 / 0.011 | 0.306 / 3.703 | 0.082 / 0.806 | 0 |
| 20 | F | 1.709 / 2.313 | 1.81 / 2.471 | 1.803 / 2.446 | 2.585 / 4.838 | 0 |
| 20 | S-file-cached | 0.009 / 0.036 | 0.008 / 0.031 | 0.028 / 0.093 | 0.106 / 1.341 | 0 |
| 20 | S-file-open | 2.506 / 4.203 | 2.527 / 4.533 | 2.546 / 3.988 | 6.728 / 10.286 | 0 |
| 20 | S-shared | 0.007 / 0.014 | 0.006 / 0.015 | 0.096 / 2.863 | 0.075 / 0.865 | 0 |
| 200 | F | 1.735 / 2.442 | 1.796 / 2.373 | 1.832 / 2.458 | 2.571 / 3.746 | 0 |
| 200 | S-file-cached | 0.021 / 0.083 | 0.017 / 0.07 | 0.036 / 0.151 | 0.116 / 2.245 | 0 |
| 200 | S-file-open | 2.772 / 5.05 | 2.556 / 4.21 | 2.658 / 4.106 | 7.06 / 10.003 | 0 |
| 200 | S-shared | 0.013 / 0.045 | 0.006 / 0.02 | 0.086 / 0.43 | 0.08 / 0.785 | 0 |

Ratio p50 N_max/N_min: {"N_hi": 200, "N_lo": 1, "F": {"q1": 1.02, "q2": 1.03, "q3": 1.02, "q4": 0.84}, "S-file-cached": {"q1": 2.62, "q2": 2.43, "q3": 1.5, "q4": 1.93}, "S-file-open": {"q1": 1.12, "q2": 1.05, "q3": 1.02, "q4": 0.99}, "S-shared": {"q1": 1.86, "q2": 1.0, "q3": 0.92, "q4": 1.23}}
Tenant handling: {"S-shared_statements": 7, "S-shared_tenant_id_occurrences": 15, "S-file_tenant_predicates": 0}
