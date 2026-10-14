# Security note: authentication

From the Acme security team.

- Authentication: JWT bearer tokens, signed with RS256, issued by the Acme identity provider.
- Tokens expire after 15 minutes. Services must verify the signature and expiry on every request.
- Static shared secrets in request headers are not allowed for user-facing traffic.
