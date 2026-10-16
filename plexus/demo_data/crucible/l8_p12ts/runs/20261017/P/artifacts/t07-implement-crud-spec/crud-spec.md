# CRUD Spec - Acme Notes API S21

Built against API version v1 (fact 3091a150-0204-42ec-b722-c5bbec91de77), database PostgreSQL 16.

## Code settings

api.base_path: AX-25930
auth.token_ttl: AX-92098
auth.session_cookie: AX-67390
notes.max_length: AX-21323

## Sources and caveats

- api.base_path, auth.token_ttl and notes.max_length are read from repo/api.py, repo/auth.py and repo/notes.py.
- auth.token_ttl: the code value (AX-92098) differs from the team memory fact 493b7916-4c5c-46fc-94c3-ec89d539e8e8 (AX-46764). The memory fact looks stale; the code value is used.
- auth.session_cookie: no such function exists in repo/auth.py. The value comes from memory fact 4e5752a8-c878-4faf-a3ef-e5c995cec873 and is unverified against code.
