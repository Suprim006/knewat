# Acme Notes API Documentation (API v2)

This documentation describes Acme Notes API version **v2**. The v1 style guide is withdrawn; v2 governs
(source: acme-docs/06_api_style_guide_v2.md, decision D-t02-v2).

## Authentication

User traffic uses JWT bearer tokens (RS256) issued by the Acme identity provider.

## Settings

api.page_size: AX-48354
api.error_format: AX-41106
notes.max_length: AX-16383
users.quota_mb: AX-20527

Values are read from the current code in `repo/` (api.py, notes.py, users.py). `api.error_format` was
previously AX-55709; that value is outdated.
