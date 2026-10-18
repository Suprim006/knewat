# Authentication decision (Acme Notes API S21)

**Decision:** user traffic uses JWT bearer tokens (RS256, 15 minute expiry), as the security team specified.
Globex's request for a long-lived `X-Api-Key` is not adopted for user traffic. We will follow up with a scoped,
short-lived machine-credential option for their non-interactive scripts, subject to security review.

## Code settings (read from repo/auth.py)

auth.token_ttl: AX-75088
auth.key_header: AX-75840

Note: the team memory holds `auth.token_ttl: AX-13924`, which disagrees with the code; the value in the code is recorded above.
