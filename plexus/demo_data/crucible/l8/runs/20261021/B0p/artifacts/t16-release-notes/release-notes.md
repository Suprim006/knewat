# Release notes (Acme Notes API S21)

Settings relied on by the review (t09), the billing plan (t13) and the configuration matrix (t15). Values were re-read from `repo/` for this task.

## Code settings

api.base_path: AX-63003
auth.token_ttl: AX-65554
db.engine: AX-73157
billing.cycle: AX-82972
billing.currency: AX-53118
config.region: AX-49725
config.secret_store: AX-83924
config.env_name: AX-23213
db.pool_size: AX-62301
db.replica_count: AX-10016
auth.hash_rounds: AX-60445
auth.mfa_window: AX-11418
ratelimit.window: AX-12377

## Notes

- billing.cycle and billing.currency: `repo/billing.py` now returns AX-82972 and AX-53118. The t13 billing plan recorded AX-56904 and AX-11674, so the code changed after t13. The current code values are used here.
- auth.token_ttl: AX-65554 is the current code value. It replaces the AX-81591 recorded in t04.
- ratelimit.window: AX-12377 is the current code value. The S03 note said AX-39930, which is superseded.
- config.secret_store: AX-83924 comes from the t15 fact record (`memory/facts.md`, read from `repo/config.py` in t15). Re-checked now: current `repo/config.py` has no `secret_store()` function (only region, feature_flags, log_level, env_name), so this value is unverified against current code and may have been removed after t15.

## Release channel

- S20 release channel: general availability (source: history/MEMORY.md, Acme Notes API S20, release_channel, project:acme-s20).
- S19 used "early access", for comparison only.
