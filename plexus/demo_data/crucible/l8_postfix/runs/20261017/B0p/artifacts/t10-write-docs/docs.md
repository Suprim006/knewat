# Acme Notes API — User Documentation (API v2)

A small REST-only notes service for Acme Corp where teams create, tag and search notes.
This documentation describes API version v2 (the v1 style guide is withdrawn).
Requests are authenticated with JWT bearer tokens (RS256, issued by the Acme identity provider).

## Settings

Values are read from the current S21 code in `repo/`.

api.page_size: AX-73505
api.error_format: AX-78362
notes.max_length: AX-21323
users.quota_mb: AX-68909

## Sources

- api.page_size: repo/api.py page_size
- api.error_format: repo/api.py error_format
- notes.max_length: repo/notes.py max_length
- users.quota_mb: repo/users.py quota_mb (read directly from code; not previously in memory/facts.md)
- API version v2: acme-docs/06_api_style_guide_v2.md (via memory/facts.md style_guide.api_version)
