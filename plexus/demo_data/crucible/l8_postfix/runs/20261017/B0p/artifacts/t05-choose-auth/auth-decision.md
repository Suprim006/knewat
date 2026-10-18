# Auth decision (t05-choose-auth)

Scheme for user traffic: JWT bearer tokens, RS256, issued by the Acme identity provider, 15-minute expiry (security.auth_method).

Customer request (Globex): long-lived API key in `X-Api-Key` (customer.auth_method). It conflicts with the security note, so it is not adopted for user traffic. It is referred to the account team and security for a separate, scoped machine-credential proposal.

Code settings (from repo/auth.py):

auth.token_ttl: AX-46764
auth.key_header: AX-96963
