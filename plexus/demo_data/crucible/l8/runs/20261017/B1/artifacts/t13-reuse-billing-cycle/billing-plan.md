# Billing plan (t13-reuse-billing-cycle)

## Code settings (repo/billing.py, sprint S21)

billing.cycle: AX-74889
billing.currency: AX-59699

## Reused from earlier sprints

- API-key header (sprint S13), as recorded in team memory: `API key in X-Core-Key header`
  (fact e0bfc28b-0c15-5c06-82d1-c39499d7b337).
- Billing cycle of the Bolt Billing API (sprint S07): **NOT FOUND in team memory.**
  Several recall queries (billing, Bolt Billing, billing cycle, currency) returned no billing facts.
  The only S07 facts are api_version, database, purpose and auth_method.
  The value `AX-74889` above is what the S21 code currently holds. It is not confirmed as the S07 decision.
  The S07 decision needs to be recorded by whoever owns it before it can be reused.

## Note on the S21 key header

Memory also holds `Acme Notes API S21 auth.key_header: AX-96963` (ff920351-0395-42fa-b7fc-9f3cb3b6d49a).
It is a code setting for this sprint and is separate from the S13 header decision.
