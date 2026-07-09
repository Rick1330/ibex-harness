---
name: Security report
about: Report a security vulnerability (do not include secrets)
title: "[security]: "
labels: security
---

## Important

- **Do not** paste API keys, tokens, passwords, JWTs, or customer data in this issue.
- Review [web/engineering/SECURITY.md](../../web/engineering/SECURITY.md) for our security model and reporting expectations.

If you have a sensitive report, use your organization's private security channel. If none exists yet, describe impact here without exploit details and ask maintainers for a secure contact path.

## Summary

High-level description of the concern (no step-by-step exploit required in public issues).

## Severity (your assessment)

- [ ] Critical (tenant isolation, auth bypass, secret leakage)
- [ ] High
- [ ] Medium
- [ ] Low

## Affected area

- [ ] authentication / authorization
- [ ] tenant isolation (PostgreSQL / Redis / ClickHouse)
- [ ] LLM proxy / context injection
- [ ] dashboard / client
- [ ] CI / supply chain
- [ ] other:

## Impact

Who or what could be affected?

## Suggested mitigation (optional)
