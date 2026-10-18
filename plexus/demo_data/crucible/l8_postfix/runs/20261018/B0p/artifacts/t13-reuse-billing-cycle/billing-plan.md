# Billing plan (S21, task t13-reuse-billing-cycle)

## Reused from earlier sprints (as recorded)
- Bolt Billing API billing cycle, sprint S07: quarterly, invoiced on day 7
- API-key header, sprint S13: API key in X-Core-Key header

Sources: `history/logs/researcher.jsonl` (Bolt Billing API S07 billing_cycle, fact 74f296cb-6df6-5f59-86f6-3dc971410666) and `history/logs/planner.jsonl` (Acme Notes API S13 auth_method, fact e0bfc28b-0c15-5c06-82d1-c39499d7b337).

## Code settings (repo/billing.py)
billing.cycle: AX-15601
billing.currency: AX-84461
