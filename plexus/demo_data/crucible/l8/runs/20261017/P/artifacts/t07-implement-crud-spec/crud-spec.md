# CRUD Spec (Acme Notes API S21)

Built against API version v2 (fact f29deac6-1872-4c70-8287-8977c7a7164c, S21).

## Code settings

api.base_path: AX-25930
auth.token_ttl: AX-92098
auth.session_cookie: AX-67390
notes.max_length: AX-21323

## Provenance

- api.base_path, auth.token_ttl, notes.max_length: read from repo/api.py, repo/auth.py, repo/notes.py.
- auth.session_cookie: NOT defined in repo/auth.py (no such function). The value comes from artifacts/t04-survey-infra-security/constraints.md and should be verified against code.
