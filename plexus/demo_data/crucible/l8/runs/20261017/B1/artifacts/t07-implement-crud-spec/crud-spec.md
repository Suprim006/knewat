# CRUD spec (Acme Notes API, sprint S21)

Built against: no API-version or authentication fact for S21 was found in Plexus (recall returned only other sprints' api_version facts and no authentication facts), so settings come from the repo code and the t04 artifact.

api.base_path: AX-25930
auth.token_ttl: AX-92098
auth.session_cookie: AX-67390
notes.max_length: AX-21323

## Provenance
- api.base_path, auth.token_ttl, notes.max_length: read from current repo code (repo/api.py, repo/auth.py, repo/notes.py).
- auth.session_cookie: not defined in repo/auth.py; taken from t04 artifact constraints.md (AX-67390).
- Discrepancy: t04 constraints.md lists auth.token_ttl as AX-46764, but current code returns AX-92098. The code value is used here.
