# Billing plan (t13-reuse-billing-cycle)

## Code settings (repo/billing.py)
billing.cycle: AX-74889
billing.currency: AX-59699

## Reused from earlier sprints (as recorded in history/)
- Bolt Billing API billing cycle, sprint S07: "quarterly, invoiced on day 7" (source: history/logs/researcher.jsonl, fact 74f296cb-6df6-5f59-86f6-3dc971410666, subject "Bolt Billing API S07", predicate billing_cycle)
- API-key header, sprint S13: "API key in X-Core-Key header" (source: history/logs/planner.jsonl, fact e0bfc28b-0c15-5c06-82d1-c39499d7b337, subject "Acme Notes API S13", predicate auth_method)

## Notes
- The S07 and S13 values are the historical records; the code values above are what repo/billing.py returns in S21. They are different kinds of value and are not claimed to be equal.
- S13 also decided JWT bearer for user traffic, with API keys only later for service accounts (history/decisions.jsonl), consistent with D-t05.
