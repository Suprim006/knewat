# Review of the CRUD spec (t09-review-spec)

Decision: approved. API version v2 and JWT bearer auth (RS256, 15 minute expiry) are consistent with the spec.

Open issue: memory also holds an active, conflicting auth fact from planner (long-lived API key in X-Api-Key header, Globex request). It needs an owner decision.

Code settings (read from repo/):

api.base_path: AX-18174
auth.token_ttl: AX-62079
db.engine: AX-14196
