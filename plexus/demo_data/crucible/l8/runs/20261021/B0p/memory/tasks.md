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

| t13-reuse-billing-cycle | Reuse the billing cycle and key header from earlier sprints | 28 | t02-choose-api-version | todo |
| t14-ratelimit-spec | Write the rate-limit spec | 22 | t04-survey-infra-security | done |
| t15-config-matrix | Write the configuration matrix | 18 | t06-write-db-schema, t14-ratelimit-spec | done |
| t16-release-notes | Write the release notes | 8 | t09-review-spec, t13-reuse-billing-cycle, t15-config-matrix | done |
| t12-update-endpoints-for-v2 | Update endpoint design for API v2 | 40 | t03-design-endpoints | done |

Done: t01-gather-requirements — api_version v1; api.base_path=AX-63003, api.page_size=AX-51173, api.max_body=AX-93646, api.cors_origin=AX-94293, api.error_format=AX-40567 (artifacts/t01-gather-requirements/requirements.md).
Done: t02-choose-api-version — v1; api.base_path=AX-63003, api.error_format=AX-40567 (artifacts/t02-choose-api-version/decision.md).
Done: t03-design-endpoints — v1 endpoints drafted; api.base_path=AX-63003, api.page_size=AX-51173, api.max_body=AX-93646 (artifacts/t03-design-endpoints/openapi-draft.md).
Done: t04-survey-infra-security — PostgreSQL 16, JWT RS256 bearer; db.engine=AX-73157, db.pool_size=AX-62301, db.schema_name=AX-63172, db.replica_count=AX-10016, db.backup_window=AX-38796, auth.token_ttl=AX-81591, auth.hash_rounds=AX-60445, auth.session_cookie=AX-86065, auth.mfa_window=AX-11418, auth.key_header=AX-59960 (artifacts/t04-survey-infra-security/constraints.md).
Done: t14-ratelimit-spec — ratelimit.window=AX-12377 (code; S03 note said AX-39930), ratelimit.burst=AX-17064, ratelimit.per_user=AX-99296, ratelimit.per_key=AX-36680, ratelimit.retry_after=AX-86887 (artifacts/t14-ratelimit-spec/ratelimit-spec.md).
Done: t13-reuse-billing-cycle — reused S07 cycle "quarterly, invoiced on day 7" and S13 header X-Core-Key; billing.cycle=AX-56904, billing.currency=AX-11674 (artifacts/t13-reuse-billing-cycle/billing-plan.md).
Done: t05-choose-auth — JWT RS256 bearer for user traffic, Globex X-Api-Key deferred; auth.token_ttl=AX-65554 (changed from AX-81591), auth.key_header=AX-59960 (artifacts/t05-choose-auth/auth-decision.md).
Done: t07-implement-crud-spec — CRUD spec on v1; api.base_path=AX-63003, auth.token_ttl=AX-65554, auth.session_cookie=AX-86065, notes.max_length=AX-92475 (artifacts/t07-implement-crud-spec/crud-spec.md).
Done: t12-update-endpoints-for-v2 — endpoints updated for API v2; api.base_path=AX-63003, api.cors_origin=AX-94293 (artifacts/t12-update-endpoints-for-v2/openapi-v2.md).
Done: t15-config-matrix — config.region=AX-49725, config.secret_store=AX-83924, config.env_name=AX-23213, db.pool_size=AX-62301, db.replica_count=AX-10016, auth.hash_rounds=AX-60445, auth.mfa_window=AX-11418, ratelimit.window=AX-12377 (artifacts/t15-config-matrix/config-matrix.md).
Done: t08-write-test-plan — test plan for API v2; notes.max_length=AX-92475, notes.tag_limit=AX-18114, notes.archive_days=AX-25751, notes.share_mode=AX-70519, notes.title_max=AX-63550 (artifacts/t08-write-test-plan/test-plan.md).
Done: t09-review-spec — rejected the v1 CRUD spec (needs v2 rebase); api.base_path=AX-63003, auth.token_ttl=AX-65554, db.engine=AX-73157 (artifacts/t09-review-spec/review.md).
Done: t10-write-docs — API v2 docs; api.page_size=AX-51173, api.error_format=AX-40567, notes.max_length=AX-92475, users.quota_mb=AX-60176 (artifacts/t10-write-docs/docs.md).
Done: t16-release-notes — S20 channel general availability; api.base_path=AX-63003, auth.token_ttl=AX-65554, db.engine=AX-73157, billing.cycle=AX-82972 (current code, t13 said AX-56904), billing.currency=AX-53118 (current code, t13 said AX-11674), config.region=AX-49725, config.secret_store=AX-83924 (t15 fact; not in current repo/config.py), config.env_name=AX-23213, db.pool_size=AX-62301, db.replica_count=AX-10016, auth.hash_rounds=AX-60445, auth.mfa_window=AX-11418, ratelimit.window=AX-12377 (artifacts/t16-release-notes/release-notes.md).
Done: t11-package-release — release package on API v2; release.channel=AX-38240, release.version_tag=AX-84412, release.rollout_pct=AX-61963, release.freeze_day=AX-94005, release.changelog_path=AX-22467 (artifacts/t11-package-release/release.md).
Done: t06-write-db-schema — PostgreSQL 16 tables notes, tags, note_tags; db.engine=AX-73157, db.pool_size=AX-62301, db.schema_name=AX-63172 (artifacts/t06-write-db-schema/schema.md).
