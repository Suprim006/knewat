# Spec review (Acme Notes API S21)

Verdict: REJECTED until the crud-spec header is corrected from API v1 to API v2 (style_guide.api_version = v2 governs; the v1 guide is withdrawn). The code settings, auth scheme (JWT bearer, RS256, 15 min) and PostgreSQL 16 schema are consistent with the team facts.

## Code settings (current repo)
api.base_path: AX-18174
auth.token_ttl: AX-62079
db.engine: AX-14196

## Notes
- auth.token_ttl: current repo/auth.py returns AX-62079; the earlier AX-70256 is superseded.
- The crud-spec (t07) states "Built against API version v1", which contradicts the adopt-v2 decision in memory/decisions.md.
