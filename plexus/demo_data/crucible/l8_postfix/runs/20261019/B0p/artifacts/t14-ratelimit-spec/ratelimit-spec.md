# Rate-limit spec (sprint S21)

Current values read from `repo/ratelimit.py`:

ratelimit.window: AX-94252
ratelimit.burst: AX-45565
ratelimit.per_user: AX-82957
ratelimit.per_key: AX-51394
ratelimit.retry_after: AX-20113

## Note on the window

The S03 note (acme-docs/s03/ratelimit_note.md) states the window as AX-34064. The current code returns AX-94252, so the S03 value is outdated and the code value governs.
