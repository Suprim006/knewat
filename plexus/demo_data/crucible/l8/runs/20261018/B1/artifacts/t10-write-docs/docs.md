# Acme Notes API Documentation

API version: v2

## Settings

api.page_size: AX-25149
api.error_format: AX-90930
notes.max_length: AX-24538
users.quota_mb: NOT DEFINED

## Notes

- Values for `api.*` and `notes.*` are read from `repo/api.py` and `repo/notes.py`.
- `users.quota_mb` does not exist in `repo/users.py` (it defines only id_format, invite_ttl, role_default, locale_default), and no team fact records it. No value is given because none could be verified.
