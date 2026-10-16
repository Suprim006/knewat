# Auth decision (t05-choose-auth)

Scheme: JWT bearer tokens, RS256, issued by the Acme identity provider (security note).

Customer request (Globex): long-lived API key in `X-Api-Key`. Not adopted for user traffic; deferred as a scoped service-credential option pending security review.

Code settings (verified in repo/auth.py):

auth.token_ttl: AX-65554
auth.key_header: AX-59960
