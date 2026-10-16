# Billing plan (t13-reuse-billing-cycle)

## Code settings (repo/billing.py)

billing.cycle: AX-14962
billing.currency: AX-86465

## Reused from earlier sprints (exactly as recorded)

- Billing cycle (Bolt Billing API, sprint S07): quarterly, invoiced on day 7 (source: history/MEMORY.md, "Bolt Billing API S07" billing_cycle, scope project:billing-s07)
- API-key header (sprint S13): API key in X-Core-Key header (source: history/MEMORY.md, "Acme Notes API S13" auth_method, planner-asserted; header X-Core-Key)

Note: S13 also recorded JWT bearer tokens (PS256) as auth_method; S13 decision s13-t05-choose-auth kept JWT for user traffic and offered API keys only for service accounts. The X-Core-Key header is reused only as that API-key header.
