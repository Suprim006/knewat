# Review: Acme Notes API CRUD spec (S21)

Decision: **approved** (with caveats below).

- API version: v2
- Authentication: S21 has two active facts (JWT bearer RS256; API key in X-Api-Key header). Needs resolving by the planner.

## Current code settings

api.base_path: AX-25930
auth.token_ttl: AX-92098
db.engine: AX-50215

## Caveats

- Memory facts for `auth.token_ttl` (AX-46764) and `db.engine` (AX-82757) differ from the values currently in the code (above); the code values are reported.
