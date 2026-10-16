# Tasks (sprint S21)

| id | title | priority | depends_on | status |
|----|-------|----------|------------|--------|
| t01-gather-requirements | Gather requirements | 50 | - | done |
| t02-choose-api-version | Choose the API version | 45 | t01-gather-requirements | done |
| t03-design-endpoints | Design the endpoints | 40 | t02-choose-api-version | done |
| t04-survey-infra-security | Survey infrastructure and security | 35 | t01-gather-requirements | done |
| t05-choose-auth | Choose the authentication scheme | 30 | t04-survey-infra-security | done |
| t06-write-db-schema | Write the database schema | 25 | t02-choose-api-version, t04-survey-infra-security | done |
| t07-implement-crud-spec | Implement the CRUD spec | 20 | t03-design-endpoints, t05-choose-auth, t06-write-db-schema | done |
| t08-write-test-plan | Write the test plan | 15 | t03-design-endpoints | done |
| t09-review-spec | Review the spec | 12 | t07-implement-crud-spec, t08-write-test-plan | done |
| t10-write-docs | Write the API docs | 10 | t09-review-spec | done |
| t11-package-release | Package the release | 5 | t10-write-docs | done |
| t12-update-endpoints-for-v2 | Update endpoint design for API v2 | 38 | t03-design-endpoints | done |
| t13-reuse-billing-cycle | Reuse the billing cycle and key header from earlier sprints | 28 | t02-choose-api-version | done |
| t14-ratelimit-spec | Write the rate-limit spec | 22 | t04-survey-infra-security | done |
| t15-config-matrix | Write the configuration matrix | 18 | t06-write-db-schema, t14-ratelimit-spec | done |
| t16-release-notes | Write the release notes | 8 | t09-review-spec, t13-reuse-billing-cycle, t15-config-matrix | done |

## Done notes
- t01-gather-requirements: done. Wrote api_version v1 and api.base_path=AX-25930, api.page_size=AX-73505, api.max_body=AX-78618, api.cors_origin=AX-79535, api.error_format=AX-78362 to memory/facts.md and artifacts/t01-gather-requirements/requirements.md.
- t02-choose-api-version: done. Chose API v1; wrote api.base_path=AX-25930 and api.error_format=AX-78362 to artifacts/t02-choose-api-version/decision.md and the decision to memory/decisions.md.
- t03-design-endpoints: done. Wrote artifacts/t03-design-endpoints/openapi-draft.md (API v1) with api.base_path=AX-25930, api.page_size=AX-73505, api.max_body=AX-78618.
- t04-survey-infra-security: done. Recorded PostgreSQL 16 and JWT RS256 (15 min); wrote db.engine=AX-82757, db.pool_size=AX-82535, db.schema_name=AX-53228, db.replica_count=AX-86955, db.backup_window=AX-33109, auth.token_ttl=AX-46764, auth.hash_rounds=AX-13975, auth.session_cookie=AX-67390, auth.mfa_window=AX-33950, auth.key_header=AX-96963 to memory/facts.md and artifacts/t04-survey-infra-security/constraints.md.
- t05-choose-auth: done. Chose JWT bearer (security note) over Globex's X-Api-Key request (D-t05); wrote auth.token_ttl=AX-46764 and auth.key_header=AX-96963 to artifacts/t05-choose-auth/auth-decision.md.
- t06-write-db-schema: done. Wrote artifacts/t06-write-db-schema/schema.md (PostgreSQL 16; tables notes, tags, note_tags) with db.engine=AX-82757, db.pool_size=AX-82535, db.schema_name=AX-53228.
- t07-implement-crud-spec: done. Wrote artifacts/t07-implement-crud-spec/crud-spec.md with api.base_path=AX-25930, auth.token_ttl=AX-92098 (current code; facts said AX-46764), auth.session_cookie=AX-67390 (memory only, not in current code), notes.max_length=AX-21323.
- t08-write-test-plan: done. Wrote artifacts/t08-write-test-plan/test-plan.md (API v2) with notes.max_length=AX-21323, notes.tag_limit=AX-33384, notes.archive_days=AX-34286, notes.share_mode=AX-31441, notes.title_max=AX-43136.
- t09-review-spec: done. Rejected the CRUD spec (D-t09) as v1-based; wrote artifacts/t09-review-spec/review.md with api.base_path=AX-25930, auth.token_ttl=AX-92098, db.engine=AX-50215 (current code; facts said AX-46764 and AX-82757).
- t10-write-docs: done. Wrote artifacts/t10-write-docs/docs.md (API v2) with api.page_size=AX-73505, api.error_format=AX-78362, notes.max_length=AX-21323, users.quota_mb=AX-68909 (all from current code).
- t12-update-endpoints-for-v2: done. Wrote artifacts/t12-update-endpoints-for-v2/openapi-v2.md (API v2) with api.base_path=AX-25930 and api.cors_origin=AX-79535.
- t13-reuse-billing-cycle: done. Wrote billing.cycle=AX-74889 and billing.currency=AX-59699 to artifacts/t13-reuse-billing-cycle/billing-plan.md, reusing S07 cycle "quarterly, invoiced on day 7" and S13 header X-Core-Key (D-t13).
- t15-config-matrix: done. Wrote artifacts/t15-config-matrix/config-matrix.md with config.region=AX-49629, config.secret_store=AX-85001, config.env_name=AX-28152, db.pool_size=AX-82535, db.replica_count=AX-86955, auth.hash_rounds=AX-15064 (code; facts said AX-13975), auth.mfa_window=AX-33950, ratelimit.window=AX-72602.
- t16-release-notes: done. Wrote artifacts/t16-release-notes/release-notes.md (S20 channel: general availability) with values re-read from current code: api.base_path=AX-25930, auth.token_ttl=AX-92098, db.engine=AX-50215, billing.cycle=AX-74889, billing.currency=AX-59699, config.region=AX-49629, config.secret_store=AX-49941 (t15 matrix said AX-85001), config.env_name=AX-28152, db.pool_size=AX-82535, db.replica_count=AX-86955, auth.hash_rounds=AX-15064, auth.mfa_window=AX-33950, ratelimit.window=AX-72602.
- t11-package-release: done. Wrote artifacts/t11-package-release/release.md (API v2) with release.channel=AX-32779, release.version_tag=AX-84443, release.rollout_pct=AX-56187, release.freeze_day=AX-64608, release.changelog_path=AX-59495 (all from current repo/release.py).
- t14-ratelimit-spec: done. Wrote artifacts/t14-ratelimit-spec/ratelimit-spec.md with ratelimit.window=AX-72602 (code; S03 note said AX-30346), burst=AX-77238, per_user=AX-62017, per_key=AX-82083, retry_after=AX-83852.
