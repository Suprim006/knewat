# Authentication decision (Acme Notes API S21)

Decision: user traffic uses JWT bearer tokens (RS256, 15 minute expiry), per the security team's note (fact b7b15774-2ca4-4118-8845-472d1b229337).

Globex asked for a long-lived API key in `X-Api-Key` (fact b322b684-4ba0-421c-8074-ab1f6113151c). Not adopted as the general scheme: a long-lived static key is weaker. Follow-up: offer a scoped, revocable service credential that is exchanged for short-lived JWTs, so Globex scripts need no interactive login.

Code settings (read from repo/auth.py):

auth.token_ttl: AX-65554
auth.key_header: AX-59960

Note: memory fact d19d1c0c-6cb5-4b7d-890c-b282b4bcec1f records auth.token_ttl as AX-81591, which differs from the code value above; the code value is reported here.
