# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Sutra, **please do not open a public issue.**

Instead, report it privately by emailing **security@sutra-os.dev** with:

1. A description of the vulnerability
2. Steps to reproduce (if applicable)
3. The potential impact
4. Any suggested fix (optional)

We will acknowledge your report within **48 hours** and aim to provide a fix or mitigation plan within **7 days** for critical issues.

## Scope

The following are in scope:

- Authentication and authorization bypass
- Injection vulnerabilities (SQL, command, template)
- Sensitive data exposure (API keys, credentials)
- Privilege escalation between user roles
- Vulnerabilities in agent tool execution (sandbox escape, unintended system access)

## Out of Scope

- Denial-of-service via LLM token usage (rate-limit your own API keys)
- Social engineering
- Vulnerabilities in third-party dependencies (report upstream; we'll update)

## Disclosure

We follow coordinated disclosure. We ask that you give us a reasonable window to address the issue before any public disclosure. We're happy to credit reporters in release notes unless you prefer to remain anonymous.
