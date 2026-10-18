# Rate-limit spec (Acme Notes API, S21)

Values as returned by `repo/ratelimit.py`:

ratelimit.window: AX-42266
ratelimit.burst: AX-65974
ratelimit.per_user: AX-21835
ratelimit.per_key: AX-35027
ratelimit.retry_after: AX-39153

Note: the S03 note (acme-docs/s03/ratelimit_note.md) states the window as AX-37629; the current code returns AX-42266 for `ratelimit.window`. The team fact for the window holds the note's value and differs from the code.
