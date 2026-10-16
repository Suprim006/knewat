# Review of the CRUD spec (t09-review-spec)

Decision: approved for API version v2. Authentication has an open conflict. S21 has two active auth_method facts: JWT bearer tokens (RS256, 15 minutes) and an API key in X-Api-Key (Globex request). The planner needs to settle which one applies.

Code settings (read from repo/):

api.base_path: AX-80684
auth.token_ttl: AX-59344
db.engine: AX-28059
