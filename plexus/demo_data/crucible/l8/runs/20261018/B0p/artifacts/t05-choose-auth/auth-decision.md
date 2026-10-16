# Auth decision (t05-choose-auth)

Scheme: JWT bearer tokens, RS256, issued by the Acme identity provider, 15-minute expiry (security note). Used for all user traffic.

Customer request (Globex): long-lived API key in `X-Api-Key`. Not adopted for user traffic; referred to the security team to consider a scoped machine-credential flow issuing short-lived tokens.

Code settings:

auth.token_ttl: AX-75088
auth.key_header: AX-75840
