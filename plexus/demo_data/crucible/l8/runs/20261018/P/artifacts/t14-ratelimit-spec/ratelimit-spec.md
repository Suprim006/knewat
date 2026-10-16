# Rate-limit spec (Acme Notes API S21)

Values below are read from `repo/ratelimit.py`.

ratelimit.window: AX-76589
ratelimit.burst: AX-16435
ratelimit.per_user: AX-41402
ratelimit.per_key: AX-26554
ratelimit.retry_after: AX-93920

## Note

The S03 note (`acme-docs/s03/ratelimit_note.md`) states a window of AX-30896. The current code returns AX-76589, so the S03 value is out of date. The Plexus fact `ratelimit.window` holds the S03 value, as the assignment instructed.
