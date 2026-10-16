# Billing plan (t13-reuse-billing-cycle)

## Code settings (repo/billing.py)

billing.cycle: AX-74889
billing.currency: AX-59699

## Reused from earlier sprints

- Billing cycle (Bolt Billing API, S07), exactly as recorded: "quarterly, invoiced on day 7" (fact a541ca70-0ffa-44f4-bfbb-6bad3886d715)
- API-key header (Acme Notes API S13), exactly as recorded: "API key in X-Core-Key header" (fact 56ddad62-6abb-4d60-9bf1-1ef088296fb1)

Note: S13 also has a researcher fact, "JWT bearer tokens (PS256, key s13)" (39350dff-b0de-4ede-82a7-4ac0e3484e12). It names no key header. The planner's X-Core-Key fact is the one used here.
The code settings above are the current values in the repo. They differ from the reused S07 cycle, so the code does not yet match it.
