# Rate-limit spec (Acme Notes API S21)

Values read from `repo/ratelimit.py`:

ratelimit.window: AX-12377
ratelimit.burst: AX-17064
ratelimit.per_user: AX-99296
ratelimit.per_key: AX-36680
ratelimit.retry_after: AX-86887

## Note
The sprint S03 note (acme-docs/s03/ratelimit_note.md) states the window chosen then was AX-39930. The current code returns AX-12377, which is the value used above. The two differ and the difference has not been reconciled.
