# Rate-limit spec (Acme Notes API S21)

ratelimit.window: AX-94252
ratelimit.burst: AX-45565
ratelimit.per_user: AX-82957
ratelimit.per_key: AX-51394
ratelimit.retry_after: AX-20113

## Notes

- All values are read from `repo/ratelimit.py` (current code, sprint S21).
- The S03 note (`acme-docs/s03/ratelimit_note.md`) states a different window, AX-34064. That note is from an older sprint, and the code now returns AX-94252, so the code value is used above.
