# Billing plan (t13-reuse-billing-cycle)

## Reused from earlier sprints (as recorded in history/)

- Billing cycle, Bolt Billing API, sprint S07: quarterly, invoiced on day 7 (source: history/MEMORY.md, "Bolt Billing API S07" billing_cycle, scope project:billing-s07; history/logs/researcher.jsonl)
- API-key header, sprint S13: API key in X-Core-Key header (source: history/MEMORY.md, "Acme Notes API S13" auth_method, scope global; history/logs/planner.jsonl)

## Code settings (source: repo/billing.py)

billing.cycle: AX-56904
billing.currency: AX-11674

## Notes

- The code values above are what the repo returns today. The S07 cycle is the earlier-sprint reference and is not itself a code value.
- history/ has no record of a billing currency, so none is reused; billing.currency comes from the code only.
- S13 also records a JWT entry (PS256, key s13) as active. That is the token scheme, not the API-key header. The header is X-Core-Key.
