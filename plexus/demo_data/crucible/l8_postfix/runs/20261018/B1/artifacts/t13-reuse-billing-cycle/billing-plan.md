# Billing plan (S21): reuse of earlier sprint decisions

## Code settings (from repo/billing.py)

billing.cycle: AX-15601
billing.currency: AX-84461

## Reused decisions

- Billing cycle of the Bolt Billing API (sprint S07): NOT FOUND in team memory. Recall returned no billing-cycle fact for S07 or for Bolt Billing API, so no value is stated. It needs to be supplied by whoever recorded it; I have not guessed.
- API-key header (sprint S13): "API key in X-Core-Key header" (fact e0bfc28b-0c15-5c06-82d1-c39499d7b337, Acme Notes API S13 auth_method).
  - Note: the S07 auth_method fact says X-Team-Key, but that is the S07 decision, not S13, so S13's X-Core-Key governs here.
