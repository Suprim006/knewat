# Release notes (Acme Notes API, sprint S21)

Built against API v2 (style guide), PostgreSQL 16. Values below were re-read from the current code in `repo/`.

## Release channel
- Sprint S20 release channel: general availability (source: history/logs/planner.jsonl, fact e507c7cc-74bf-53e4-b40b-40037024086b, "Acme Notes API S20" release_channel)

## Code settings
api.base_path: AX-25930
auth.token_ttl: AX-92098
db.engine: AX-50215
billing.cycle: AX-74889
billing.currency: AX-59699
config.region: AX-49629
config.secret_store: AX-49941
config.env_name: AX-28152
db.pool_size: AX-82535
db.replica_count: AX-86955
auth.hash_rounds: AX-15064
auth.mfa_window: AX-33950
ratelimit.window: AX-72602

## Notes
- Stale in memory/facts.md, current code wins: auth.token_ttl (facts AX-46764), db.engine (facts AX-82757), auth.hash_rounds (facts AX-13975), config.secret_store (facts AX-85001; the t15 matrix also listed AX-85001, but repo/config.py now returns AX-49941).
- ratelimit.window: the S03 note value AX-30346 is superseded by the code value.
