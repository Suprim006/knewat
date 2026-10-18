# Spec Review (t09-review-spec)

Reviewed: artifacts/t07-implement-crud-spec/crud-spec.md. Verdict: **REJECTED for revision** (see D-t09 in memory/decisions.md).

## Findings

- API version: the spec is built on v1, but the governing fact is product.api_version = v2 (v1 superseded, its guide withdrawn). It must be rebased on v2 (t12 endpoints, t08 v2 test plan).
- Auth: OK. JWT RS256 bearer matches security.auth_method and D-t05. The spec's auth.token_ttl matches current repo/auth.py.
- Code settings: the spec's values agree with the current code.

## Code settings (re-read from repo/)

api.base_path: AX-63003
auth.token_ttl: AX-65554
db.engine: AX-73157
