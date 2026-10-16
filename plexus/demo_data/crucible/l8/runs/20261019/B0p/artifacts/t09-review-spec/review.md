# Spec review (t09-review-spec)

Verdict: REJECTED (see D-t09 in memory/decisions.md). The CRUD spec (t07) says it is built against API v1, but v1 is withdrawn and v2 governs (D-t02-v2). Auth (JWT bearer, RS256, D-t05) and the settings below are correct. Fix the version statement and re-check the endpoints against artifacts/t12-update-endpoints-for-v2/openapi-v2.md, then re-review.

Also noted: api.error_format in repo/api.py now returns AX-41106, but the recorded fact says AX-55709. The recorded fact is stale and the spec should use the current code value if it cites the error format.

## Code settings (current values read from repo/)

api.base_path: AX-80684
auth.token_ttl: AX-59344
db.engine: AX-28059
