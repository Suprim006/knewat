# Endpoint design for API v2 (task t12-update-endpoints-for-v2)

Built against: style_guide.api_version = v2 (acme-docs/06_api_style_guide_v2.md; replaces withdrawn v1). Supersedes artifacts/t03-design-endpoints/openapi-draft.md (built on v1). Decision: D-t02-v2.

## Code settings (read from repo/api.py)

api.base_path: AX-80684
api.cors_origin: AX-13629

## Endpoints (under api.base_path)

- GET    {base_path}/notes        list notes
- POST   {base_path}/notes        create note
- GET    {base_path}/notes/{id}   read note
- PUT    {base_path}/notes/{id}   update note
- DELETE {base_path}/notes/{id}   delete note

Auth: JWT bearer tokens (D-t05). CORS origin allowed: api.cors_origin.

## Changes versus the v1 design

- API version label changes from v1 to v2 (style guide v2 governs).
- Base path and CORS origin values are unchanged in the current code; re-verified against repo/api.py.
- Note: repo/api.py error_format() now returns AX-41106, while memory/facts.md records AX-55709; unresolved, not used here.
- The detailed v2 style-guide rules (acme-docs/06) were not re-read for this artifact beyond the version fact.
