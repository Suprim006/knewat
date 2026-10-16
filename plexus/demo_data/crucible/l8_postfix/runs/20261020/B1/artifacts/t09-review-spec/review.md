# Review of the CRUD spec (t09-review-spec)

Decision: approved. API version is v2 and auth is JWT bearer tokens (RS256).

Values read from the current code in `repo/`:

api.base_path: AX-18174
auth.token_ttl: AX-62079
db.engine: AX-14196

Note: shared memory records `auth.token_ttl` as AX-70256, but the code returns AX-62079. The code value is reported above, and the stored fact looks stale.
