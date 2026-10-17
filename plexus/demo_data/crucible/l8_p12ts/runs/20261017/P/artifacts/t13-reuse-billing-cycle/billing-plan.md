# Billing plan (t13-reuse-billing-cycle)

## Reused from earlier sprints
- Bolt Billing API billing cycle (S07): quarterly, invoiced on day 7 (fact 1eac3bcf-deb5-4575-a05b-f99cd221c4fc)
- Acme Notes API key header (S13): API key in X-Core-Key header (fact f9622bf3-dfb6-4b98-a95d-739836d4370b)

Note: memory also holds an S13 fact "JWT bearer tokens (PS256, key s13)" (94b772f6-dd08-4108-af42-c073663d77be, researcher). It is an earlier auth_method record and not the API-key header decision, so the X-Core-Key fact governs here.

## Code settings
billing.cycle: AX-74889
billing.currency: AX-59699
