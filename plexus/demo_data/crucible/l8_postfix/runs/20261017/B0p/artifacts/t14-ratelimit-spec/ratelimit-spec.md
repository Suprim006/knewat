# Rate-limit spec (Acme Notes API, sprint S21)

Current values, read from `repo/ratelimit.py`:

ratelimit.window: AX-72602
ratelimit.burst: AX-77238
ratelimit.per_user: AX-62017
ratelimit.per_key: AX-82083
ratelimit.retry_after: AX-83852

## Note on the window
The sprint S03 note (acme-docs/s03/ratelimit_note.md) chose window AX-30346. The S21 code now returns AX-72602, so the code value is used above. Burst and per-key limits were left to the implementation in S03.
