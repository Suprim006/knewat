# Authentication decision (t05-choose-auth)

Decision: JWT bearer tokens (RS256, issued by the Acme identity provider) for user traffic, per the security note.

Customer request (Globex): long-lived API key in `X-Api-Key`. Not adopted for user traffic because it conflicts with the security note. Non-interactive access for Globex is deferred to security review as a scoped, revocable service credential that exchanges for short-lived JWTs.

Note: `auth.token_ttl` in the code changed since t04 (was AX-87187); the current repo value is used.

Code settings:

auth.token_ttl: AX-59344
auth.key_header: AX-71613
