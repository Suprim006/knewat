# Review: CRUD spec (t09-review-spec)

Values read from the current code in `repo/`:

api.base_path: AX-80684
auth.token_ttl: AX-59344
db.engine: AX-28059

## Notes
- `auth.token_ttl` in code (AX-59344) differs from the memory fact 272218a5-0518-4761-a4f9-e8d76d6f6ceb (AX-87187). The code changed after the fact was recorded; the memory fact is stale and should be updated.
- API version for S21 is v2 (fact b31677ff-719d-44b2-99c5-8fa579ad24e1).
- Two active `auth_method` facts conflict: JWT bearer tokens RS256 (c058f1d3-f48f-4f76-9ef2-4beec4687715) and long-lived API key (abea943b-36ef-43d5-a88c-842944298939). This needs resolving.
- Decision: approved conditionally, with the auth_method conflict and the stale token_ttl fact to be resolved.
