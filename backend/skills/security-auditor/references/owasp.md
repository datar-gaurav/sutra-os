# OWASP Top 10 — Audit Checklist

## A01: Broken Access Control
Missing authorization checks, IDOR (insecure direct object reference), permissive CORS, force browsing to authenticated pages, JWT signature not verified, metadata manipulation (cookies, hidden fields).

## A02: Cryptographic Failures
Sensitive data transmitted in plaintext (HTTP), weak hashing (MD5, SHA1), weak crypto algorithms (DES, RC4), hardcoded keys, weak random number generation, missing encryption at rest.

## A03: Injection
SQL (string concatenation), NoSQL (Mongo `$where`), OS command (`os.system`, shell=True), LDAP, XPath, XXE, template injection (Jinja, Mustache rendering user input), header injection.

## A04: Insecure Design
Missing rate limiting, no anti-automation on auth endpoints, no business-logic constraints (e.g., negative quantities), missing fraud controls.

## A05: Security Misconfiguration
Default credentials, debug mode enabled in prod, verbose error messages exposing stack traces, unnecessary features enabled (admin panels, sample apps), missing security headers (CSP, HSTS, X-Frame-Options), open S3 buckets.

## A06: Vulnerable & Outdated Components
Dependencies with known CVEs, EOL/unmaintained packages, libraries not pinned, no Dependabot/Renovate equivalent.

## A07: Identification & Authentication Failures
Allows weak passwords, no MFA option, session IDs in URLs, session not invalidated on logout, predictable session tokens, no protection against credential stuffing.

## A08: Software & Data Integrity Failures
Unsigned updates, deserialization of untrusted input (`pickle.loads`, `yaml.load` w/o SafeLoader), CI/CD pipelines with insufficient access controls, dependency confusion attacks.

## A09: Security Logging & Monitoring Failures
Auth failures not logged, no alerting on suspicious patterns, logs stored in plaintext with sensitive data, no log retention, no centralized log aggregation.

## A10: Server-Side Request Forgery (SSRF)
User-controlled URLs fetched server-side, no URL allowlist, no filtering of internal IPs (169.254.169.254 — cloud metadata, 127.0.0.1, RFC1918 ranges).

## Secret patterns to grep for
```
AKIA[0-9A-Z]{16}              # AWS Access Key
ASIA[0-9A-Z]{16}              # AWS Temp Access Key
ghp_[A-Za-z0-9]{36}           # GitHub Personal Token
gho_[A-Za-z0-9]{36}           # GitHub OAuth Token
sk-[A-Za-z0-9]{48}            # OpenAI key
xoxb-[0-9-]+                  # Slack Bot Token
-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----
```
