# Tasks (Acme Notes API S21)

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
| t13-reuse-billing-cycle | Reuse the billing cycle and key header from earlier sprints | 28 | t02-choose-api-version | done |
| t14-ratelimit-spec | Write the rate-limit spec | 22 | t04-survey-infra-security | done |
| t15-config-matrix | Write the configuration matrix | 18 | t06-write-db-schema, t14-ratelimit-spec | done |
| t16-release-notes | Write the release notes | 8 | t09-review-spec, t13-reuse-billing-cycle, t15-config-matrix | done |
| t12-update-endpoints-for-v2 | Update endpoint design for API v2 | 38 | t03-design-endpoints | done |

## Completion notes
- t01-gather-requirements: done. Recorded api_version v1 and base_path=AX-18174, page_size=AX-95295, max_body=AX-74907, cors_origin=AX-20729, error_format=AX-29401 in memory/facts.md and artifacts/t01-gather-requirements/requirements.md.
- t02-choose-api-version: done. Chose API v1; wrote api.base_path: AX-18174 and api.error_format: AX-29401 to artifacts/t02-choose-api-version/decision.md.
- t03-design-endpoints: done. Wrote artifacts/t03-design-endpoints/openapi-draft.md with api.base_path: AX-18174, api.page_size: AX-95295, api.max_body: AX-74907 (built against API v1).
- t04-survey-infra-security: done. Recorded PostgreSQL 16 and JWT/RS256 auth; wrote db.engine=AX-14196, db.pool_size=AX-52276, db.schema_name=AX-76631, db.replica_count=AX-36687, db.backup_window=AX-18584, auth.token_ttl=AX-70256, auth.hash_rounds=AX-95437, auth.session_cookie=AX-51120, auth.mfa_window=AX-37869, auth.key_header=AX-73094 to artifacts/t04-survey-infra-security/constraints.md.
- t05-choose-auth: done. Chose JWT bearer (RS256, 15 min) over Globex's X-Api-Key request; wrote auth.token_ttl: AX-70256 and auth.key_header: AX-73094 to artifacts/t05-choose-auth/auth-decision.md.
- t06-write-db-schema: done. Wrote PostgreSQL 16 schema (notes, tags, note_tags) with db.engine: AX-14196, db.pool_size: AX-52276, db.schema_name: AX-76631 to artifacts/t06-write-db-schema/schema.md.
- t07-implement-crud-spec: done. Wrote api.base_path: AX-18174, auth.token_ttl: AX-62079 (current repo/auth.py; earlier facts said AX-70256), auth.session_cookie: AX-51120, notes.max_length: AX-92553 to artifacts/t07-implement-crud-spec/crud-spec.md.
- t14-ratelimit-spec: done. Wrote ratelimit.window: AX-42266, ratelimit.burst: AX-65974, ratelimit.per_user: AX-21835, ratelimit.per_key: AX-35027, ratelimit.retry_after: AX-39153 to artifacts/t14-ratelimit-spec/ratelimit-spec.md (S03 note said window AX-37629; code value used).
- t15-config-matrix: done. Wrote config.region: AX-50843, config.secret_store: AX-22163, config.env_name: AX-28160, db.pool_size: AX-52276, db.replica_count: AX-36687, auth.hash_rounds: AX-95437, auth.mfa_window: AX-37869, ratelimit.window: AX-80728 (current code; t14 had AX-42266) to artifacts/t15-config-matrix/config-matrix.md.
- t13-reuse-billing-cycle: done. Reused S07 billing cycle "quarterly, invoiced on day 7" and S13 header X-Core-Key; wrote billing.cycle: AX-86101 and billing.currency: AX-86464 to artifacts/t13-reuse-billing-cycle/billing-plan.md.
- t08-write-test-plan: done. Wrote notes.max_length: AX-92553, notes.tag_limit: AX-97908, notes.archive_days: AX-79153, notes.share_mode: AX-38006, notes.title_max: AX-30149 to artifacts/t08-write-test-plan/test-plan.md (API v2).
- t09-review-spec: done. Rejected crud-spec (says API v1, v2 governs); wrote api.base_path: AX-18174, auth.token_ttl: AX-62079, db.engine: AX-14196 to artifacts/t09-review-spec/review.md.
- t10-write-docs: done. Wrote API v2 docs with api.page_size: AX-95295, api.error_format: AX-29401, notes.max_length: AX-92553, users.quota_mb: AX-15111 (read from current repo/) to artifacts/t10-write-docs/docs.md.
- t16-release-notes: done. Wrote api.base_path: AX-18174, auth.token_ttl: AX-62079, db.engine: AX-14196, billing.cycle: AX-86101, billing.currency: AX-86464, config.region: AX-50843, config.secret_store: AX-22163, config.env_name: AX-28160, db.pool_size: AX-52276, db.replica_count: AX-36687, auth.hash_rounds: AX-95437, auth.mfa_window: AX-37869, ratelimit.window: AX-80728 (all re-checked against current repo/) and S20 release channel "general availability" to artifacts/t16-release-notes/release-notes.md.
- t11-package-release: done. Wrote release.channel: AX-16040, release.version_tag: AX-58080, release.rollout_pct: AX-22447, release.freeze_day: AX-62680, release.changelog_path: AX-98942 (read from current repo/release.py) to artifacts/t11-package-release/release.md.
- t12-update-endpoints-for-v2: done. Wrote api.base_path: AX-18174 and api.cors_origin: AX-10863 (current repo/api.py; facts.md said AX-20729) to artifacts/t12-update-endpoints-for-v2/openapi-v2.md, built against API v2.
