# Billing plan (t13-reuse-billing-cycle)

## Code settings (repo/billing.py)

billing.cycle: AX-86101
billing.currency: AX-86464

## Reused from earlier sprints

- Billing cycle of the Bolt Billing API (sprint S07): **NOT FOUND in team memory.** Recall for "Bolt Billing", "billing cycle", "billing_cycle" and S07 returned only S07 facts on auth, purpose, api_version and database. No value is recorded here because none exists to quote. Someone must supply the S07 decision before `billing.cycle` can be tied to it.
- API-key header (sprint S13): `API key in X-Core-Key header` (fact e0bfc28b-0c15-5c06-82d1-c39499d7b337).
  - S13 also records `JWT bearer tokens (PS256, key s13)` (fact 281fe1b5-fe2f-570f-b317-b10819b44639) as an auth method. That is not the key header.
  - Do not confuse it with S07's `X-Team-Key` (fact 420dbc5d-4360-5896-9a31-6d72eaf60eb9), which is a different sprint's header.
