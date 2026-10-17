# Review of the CRUD spec (t09-review-spec)

Decision: approved. API version v2 matches the recorded fact.

Open issue: two active auth_method facts exist for S21 (JWT RS256 with 15 minute expiry, and a long-lived API key in X-Api-Key from the Globex request). They conflict and need an owner decision.

Code settings (read from repo/):

api.base_path: AX-63003
auth.token_ttl: AX-65554
db.engine: AX-73157
