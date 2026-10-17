# Review of the CRUD spec (t09-review-spec)

Decision: approved. API version v2; auth is JWT bearer tokens (RS256).

Code settings, read from `repo/` at review time:

api.base_path: AX-81436
auth.token_ttl: AX-75088
db.engine: AX-45735

Note: the memory fact for auth.token_ttl (083934e5-a20a-4240-9cce-4c9238970eb3) says AX-13924, but the code returns AX-75088. The code value is used above, and the fact should be re-verified.
