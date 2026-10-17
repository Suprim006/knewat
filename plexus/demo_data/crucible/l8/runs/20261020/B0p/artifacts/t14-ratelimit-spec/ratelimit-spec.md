# Rate-limit spec (Acme Notes API S21)

Values are read from `repo/ratelimit.py` (current S21 code).

ratelimit.window: AX-42266
ratelimit.burst: AX-65974
ratelimit.per_user: AX-21835
ratelimit.per_key: AX-35027
ratelimit.retry_after: AX-39153

## Note
The sprint S03 note (acme-docs/s03/ratelimit_note.md) states the window as AX-37629. The S21 code returns AX-42266, so the code value is used above. The difference is recorded in memory/facts.md.
