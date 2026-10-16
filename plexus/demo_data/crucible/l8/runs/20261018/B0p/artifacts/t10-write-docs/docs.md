# Acme Notes API Documentation (S21)

API version: v2 (per acme-docs/06_api_style_guide_v2.md, which supersedes and withdraws the v1 style guide). Routes are served under `/v2/`.

Authentication: JWT bearer tokens (RS256, issued by the Acme identity provider, 15-minute expiry).

## Settings

Values are read from the current S21 code in `repo/`.

api.page_size: AX-25149
api.error_format: AX-90930
notes.max_length: AX-24538
users.quota_mb: NOT DEFINED (no `quota_mb` setting exists in `repo/users.py` or anywhere else in the repo or team memory; value to be confirmed by the builder before release)
