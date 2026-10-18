# Spec review (t09-review-spec)

Verdict: REJECTED. The CRUD spec (t07) needs revision before docs (t10).

## Code settings (read from repo/ as it is now)

api.base_path: AX-25930
auth.token_ttl: AX-92098
db.engine: AX-50215

## Findings

- The CRUD spec says it is built against API v1. The governing fact is style_guide.api_version = v2 (D-t02-v2; the v1 guide is withdrawn). The test plan (t08) is already v2. The spec must be aligned to v2 using artifacts/t12-update-endpoints-for-v2/openapi-v2.md.
- auth.token_ttl: the spec's AX-92098 matches the current repo/auth.py. `memory/facts.md` still lists AX-46764, which is stale.
- db.engine: current repo/db.py gives AX-50215. `memory/facts.md` and the t06 schema list AX-82757, which is stale. The spec does not state db.engine, but it relies on the t06 schema.
- api.base_path: AX-25930 matches both the code and the facts.
- The spec lists auth.session_cookie = AX-67390 as unverified. It is not in the current repo/auth.py, so it should be dropped.
- auth.key_header: the code has AX-47833 and the facts have AX-96963. The spec caveat is correct.
