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

## Completion notes

- t01-gather-requirements: done. Wrote api_version v1, api.base_path=AX-80684, api.page_size=AX-48354, api.max_body=AX-44971, api.cors_origin=AX-13629, api.error_format=AX-55709 to memory/facts.md and artifacts/t01-gather-requirements/requirements.md.
- t02-choose-api-version: done. Chose API v1; wrote api.base_path=AX-80684 and api.error_format=AX-55709 to artifacts/t02-choose-api-version/decision.md and decision D-t02 in memory/decisions.md.
- t03-design-endpoints: done. Wrote artifacts/t03-design-endpoints/openapi-draft.md with api.base_path=AX-80684, api.page_size=AX-48354, api.max_body=AX-44971.
- t04-survey-infra-security: done. Wrote PostgreSQL 16 and JWT/RS256 auth plus db.engine=AX-28059, db.pool_size=AX-10726, db.schema_name=AX-81475, db.replica_count=AX-48545, db.backup_window=AX-67698, auth.token_ttl=AX-87187, auth.hash_rounds=AX-52301, auth.session_cookie=AX-25766, auth.mfa_window=AX-37780, auth.key_header=AX-71613 to memory/facts.md and artifacts/t04-survey-infra-security/constraints.md.
- t05-choose-auth: done. Chose JWT bearer for user traffic (decision D-t05, customer X-Api-Key request deferred); wrote auth.token_ttl=AX-59344 (code changed from AX-87187) and auth.key_header=AX-71613 to artifacts/t05-choose-auth/auth-decision.md.
| t13-reuse-billing-cycle | Reuse the billing cycle and key header from earlier sprints | 28 | t02-choose-api-version | done |

- t13-reuse-billing-cycle: done. Wrote billing.cycle=AX-14962 and billing.currency=AX-86465 plus reused S07 billing cycle "quarterly, invoiced on day 7" and S13 key header X-Core-Key to artifacts/t13-reuse-billing-cycle/billing-plan.md (decision D-t13).
- t07-implement-crud-spec: done. Wrote api.base_path=AX-80684, auth.token_ttl=AX-59344, auth.session_cookie=AX-25766, notes.max_length=AX-16383 to artifacts/t07-implement-crud-spec/crud-spec.md.
- t06-write-db-schema: done. Wrote PostgreSQL 16 schema (notes, tags, note_tags) with db.engine=AX-28059, db.pool_size=AX-10726, db.schema_name=AX-81475 to artifacts/t06-write-db-schema/schema.md.
| t14-ratelimit-spec | Write the rate-limit spec | 22 | t04-survey-infra-security | done |

- t14-ratelimit-spec: done. Wrote ratelimit.window=AX-94252 (S03 note said AX-34064, outdated), ratelimit.burst=AX-45565, ratelimit.per_user=AX-82957, ratelimit.per_key=AX-51394, ratelimit.retry_after=AX-20113 to artifacts/t14-ratelimit-spec/ratelimit-spec.md.

| t15-config-matrix | Write the configuration matrix | 18 | t06-write-db-schema, t14-ratelimit-spec | done |
| t16-release-notes | Write the release notes | 8 | t09-review-spec, t13-reuse-billing-cycle, t15-config-matrix | done |

- t16-release-notes: done. Wrote api.base_path=AX-80684, auth.token_ttl=AX-59344, db.engine=AX-28059, billing.cycle=AX-42079 (code changed from AX-14962), billing.currency=AX-87484 (code changed from AX-86465), config.region=AX-49787, config.secret_store=AX-24118, config.env_name=AX-89720, db.pool_size=AX-10726, db.replica_count=AX-48545, auth.hash_rounds=AX-52301, auth.mfa_window=AX-50544, ratelimit.window=AX-94252 and S20 release channel "general availability" to artifacts/t16-release-notes/release-notes.md.

- t15-config-matrix: done. Wrote config.region=AX-49787, config.secret_store=AX-24118, config.env_name=AX-89720, db.pool_size=AX-10726, db.replica_count=AX-48545, auth.hash_rounds=AX-52301, auth.mfa_window=AX-50544 (code changed from AX-37780), ratelimit.window=AX-94252 to artifacts/t15-config-matrix/config-matrix.md.
| t12-update-endpoints-for-v2 | Update endpoint design for API v2 | 38 | t03-design-endpoints | done |

- t08-write-test-plan: done. Wrote notes.max_length=AX-16383, notes.tag_limit=AX-60457, notes.archive_days=AX-94273, notes.share_mode=AX-43223, notes.title_max=AX-40109 (API v2) to artifacts/t08-write-test-plan/test-plan.md.

- t09-review-spec: done. Rejected the t07 CRUD spec (built on withdrawn v1; D-t09); wrote api.base_path=AX-80684, auth.token_ttl=AX-59344, db.engine=AX-28059 to artifacts/t09-review-spec/review.md.
- t12-update-endpoints-for-v2: done. Wrote api.base_path=AX-80684 and api.cors_origin=AX-13629 (API v2) to artifacts/t12-update-endpoints-for-v2/openapi-v2.md.
- t11-package-release: done. Wrote release.channel=AX-38101, release.version_tag=AX-27821, release.rollout_pct=AX-74797, release.freeze_day=AX-71540, release.changelog_path=AX-19127 to artifacts/t11-package-release/release.md.
- t10-write-docs: done. Wrote API v2 docs with api.page_size=AX-48354, api.error_format=AX-41106, notes.max_length=AX-16383, users.quota_mb=AX-20527 to artifacts/t10-write-docs/docs.md.
