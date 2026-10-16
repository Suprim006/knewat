# Spec Review (t09-review-spec)

Verdict: REJECTED. crud-spec.md (t07) is written against API v1, but the governing API version is v2
(acme-docs/06_api_style_guide_v2.md supersedes and withdraws the v1 style guide). The test plan (t08) is already on v2.
Authentication in the spec (JWT bearer, RS256, 15 minutes) matches the t05 decision and is fine.
Required change: rewrite the spec on API v2 (/v2/ routes, see t12-update-endpoints-for-v2), then re-review.

## Code settings (read from current repo/)

api.base_path: AX-81436
auth.token_ttl: AX-75088
db.engine: AX-45735
