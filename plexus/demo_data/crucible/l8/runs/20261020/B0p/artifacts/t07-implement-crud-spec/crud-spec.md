# CRUD spec (Acme Notes API S21)

Built against API version v1 (style_guide.api_version = v1), PostgreSQL 16 schema (t06), JWT bearer auth, RS256, 15 min (t05-choose-auth).

## Code settings
api.base_path: AX-18174
auth.token_ttl: AX-62079
auth.session_cookie: AX-51120
notes.max_length: AX-92553

## Operations (under api.base_path)
- Create: `POST /notes` - body limited by notes.max_length; returns the created note.
- Read: `GET /notes/{id}`, `GET /notes` (paginated).
- Update: `PUT /notes/{id}`.
- Delete: `DELETE /notes/{id}`.
- All calls require `Authorization: Bearer <JWT>`.

## Notes on sources
- auth.token_ttl: memory/facts.md and the t05 decision recorded AX-70256, but the current repo/auth.py returns AX-62079 (code changed during the sprint). The current code value is used here; facts.md was updated to flag this.
- api.base_path, auth.session_cookie and notes.max_length agree between memory and repo (notes.max_length read from repo/notes.py).
