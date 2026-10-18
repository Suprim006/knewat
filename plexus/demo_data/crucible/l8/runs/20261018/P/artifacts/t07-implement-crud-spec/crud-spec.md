# Acme Notes API S21 - CRUD spec

Built against API version v30 (latest recalled api_version fact, S15; no S21 version fact was found).
Auth basis: latest recalled auth_method is JWT bearer tokens (PS256, key s03), from S03.

## Code settings (read from repo/)

api.base_path: AX-81436
auth.token_ttl: AX-75088
auth.session_cookie: AX-98773
notes.max_length: AX-24538

## Operations

- Create: POST {base_path}/notes
- Read: GET {base_path}/notes/{id}
- Update: PUT {base_path}/notes/{id}
- Delete: DELETE {base_path}/notes/{id}
