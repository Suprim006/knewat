# Decisions (Acme Notes API S21)

## t02-choose-api-version
Build against API version v1 with base path AX-81436 and error format AX-90930.
Relies on facts: style_guide.api_version = v1, api.base_path = AX-81436, api.error_format = AX-90930 (all consistent with repo/api.py; no conflicting facts).

## t02-choose-api-version (adopt-v2, supersedes the v1 decision above)
Adopt API version v2. The researcher's updated fact governs over the earlier v1 value because acme-docs/06_api_style_guide_v2.md supersedes and withdraws the v1 style guide (acme-docs/02_api_style_guide_v1.md). Endpoint design done on v1 (t03) must be revisited: see t12-update-endpoints-for-v2.
Relies on facts: style_guide.api_version = v2 (source: acme-docs/06_api_style_guide_v2.md).

## t13-reuse-billing-cycle
Reuse the Bolt Billing API billing cycle from S07 (quarterly, invoiced on day 7) and the API-key header from S13 (X-Core-Key). Found in history/logs/researcher.jsonl (Bolt Billing API S07 billing_cycle) and history/logs/planner.jsonl (Acme Notes API S13 auth_method). Code settings written beside them: billing.cycle = AX-15601, billing.currency = AX-84461 (repo/billing.py).
Note: the S13 header is a historical record; it is not adopted for user traffic, which t05-choose-auth decided uses JWT bearer tokens.

## t05-choose-auth
Use the security team's scheme (JWT bearer tokens, RS256, 15-minute expiry) for all user traffic. The customer's request (long-lived API key in X-Api-Key) is not adopted for user traffic: long-lived keys conflict with the security note. Globex's non-interactive back-office need is deferred: escalate to the security team to consider a separate, scoped machine-credential flow (e.g. client-credentials issuing short-lived JWTs) rather than a static key. Code settings: auth.token_ttl = AX-75088, auth.key_header = AX-75840 (current repo/auth.py; the code value governs over the older fact AX-13924).
Relies on facts: security.auth_method = JWT bearer tokens, RS256, 15 minutes (acme-docs/04_security_note.md); customer.auth_method = long-lived API key in X-Api-Key (acme-docs/05_customer_request.md); auth.token_ttl = AX-75088; auth.key_header = AX-75840.

## t09-review-spec
REJECT artifacts/t07-implement-crud-spec/crud-spec.md: it is written on API v1, but the governing version is v2 (acme-docs/06_api_style_guide_v2.md supersedes the withdrawn v1 guide). Its JWT bearer auth matches t05 and is fine. Required change: rewrite the spec on v2 (/v2/ routes, see t12-update-endpoints-for-v2), then re-review. Details in artifacts/t09-review-spec/review.md.
Relies on facts: style_guide.api_version = v2 (supersedes v1); security.auth_method = JWT bearer tokens, RS256, 15 minutes; api.base_path = AX-81436; auth.token_ttl = AX-75088; db.engine = AX-45735 (all re-read from repo/ in t09).
