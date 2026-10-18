# CRUD Spec – Acme Notes API S21

Built against API version v1 (fact 2b9c4aaa-534b-4bd3-9e95-261765527e82).

## Settings

api.base_path: AX-25930
auth.token_ttl: AX-92098
auth.session_cookie: AX-67390
notes.max_length: AX-21323

## Notes

- api.base_path, auth.token_ttl and notes.max_length are read from the current code in repo/.
- auth.token_ttl in code (AX-92098) differs from the stored memory fact 2445bd3a-f554-42ce-92b8-afc0d9aef0b8 (AX-46764); the code value is used and the fact looks stale.
- auth.session_cookie is not defined in repo/auth.py; the value comes from memory fact fd603fa9-308c-486b-9544-d736344ccbde (t04 constraints).
