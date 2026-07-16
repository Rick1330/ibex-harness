# IBEX Harness — Security Assurance Case

This document assembles a lightweight **assurance case** for OpenSSF Silver (`assurance_case`): what we claim about security, why we believe it, and where evidence lives. It does not replace [SECURITY.md](./SECURITY.md); it maps claims to artifacts.

**Last reviewed:** 2026-07-15  
**Reviewer:** project lead (@Rick1330)

---

## 1) Claims

| ID | Claim |
| --- | --- |
| C1 | Org-scoped tenant isolation holds for API, DB (RLS), and Redis key namespaces |
| C2 | Authentication failures and ambiguous tenant scope fail closed |
| C3 | Secrets and tokens are not logged and are not committed to VCS |
| C4 | Supply-chain risks are continuously scanned; critical findings block merge or release |
| C5 | Cryptography uses approved algorithms only (Argon2id, TLS ≥ 1.2 externally) |

---

## 2) Trust boundaries

```text
Internet clients
  → Public site (ibexharness.com / Cloudflare Pages) [static docs]
  → Proxy HTTP API (bearer tokens)
       → Auth gRPC (token + agent validation)
       → Postgres (RLS / org_id)
       → Redis (org-scoped keys)
       → Upstream LLM providers (HTTPS)
```

Untrusted: all client input, memory content used as prompt data, dependency packages, CI PRs from forks.  
Trusted for Phase 1 ops: maintainers with MFA, GitHub Actions OIDC for release signing, Cloudflare account holding Pages.

---

## 3) Arguments and evidence

| Claim | Argument | Evidence |
| --- | --- | --- |
| C1 | Dual enforcement: app-layer org_id + SQL RLS; Redis keys namespaced by org_id; cross-org returns 403 | [SECURITY.md §5.1–5.3](./SECURITY.md#5-multi-tenancy-isolation-defense-in-depth) (RLS + Redis `{org_id}:…` namespaces); `TestSecurity_SEC*`; [ADR-0016](../content/docs/adr/0016-rls-tenant-isolation.mdx) |
| C2 | Explicit fail-closed for auth/isolation; quality degrades separately | [SECURITY.md §15](./SECURITY.md#15-fail-closed-vs-fail-open-rules); apierror envelope |
| C3 | Logging policy + gitleaks in CI; package logger forbids secrets | [SECURITY.md §6](./SECURITY.md#6-data-protection-encryption-secrets-key-management); `.gitleaks.toml`; [ADR-0008](../content/docs/adr/0008-security-ci-gates.mdx) |
| C4 | Continuous SCA/SAST; CRITICAL findings block merge; no release with open CRITICAL without waiver | [DEPENDENCIES.md §9.0.1](./DEPENDENCIES.md#901-sca-remediation-thresholds-osps-vm-05010503) (OSV/Trivy/govulncheck gates + pre-release rule); ci.yml security jobs |
| C5 | Approved crypto only: Argon2id hashing; TLS ≥ 1.2 (policy prefers 1.3 externally); no MD5/SHA-1 for security | [SECURITY.md §6.1](./SECURITY.md#61-encryption-in-transit) + [§6.4](./SECURITY.md#64-cryptographic-standards-approved-algorithms) (TLS / Argon2id); [ADR-0010](../content/docs/adr/0010-cryptography-policy.mdx) |

---

## 4) Design principles (security)

1. **Deny by default** — missing org context or tokens → deny  
2. **Defense in depth** — handler, service, store, RLS  
3. **Least privilege** — tokens as bitmaps; CI jobs with minimal `permissions`  
4. **Memory as untrusted data** — never treat retrieved memory as instructions  
5. **Observable denials** — audit cross-tenant attempts; stable error codes  

Mapped loosely to OWASP/CWE themes: broken access control (C1), crypto failures (C5), security misconfiguration / supply chain (C4), injection via memory (principles §4).

---

## 5) Residual risks and timeline

| Risk | Status |
| --- | --- |
| Solo maintainer bus factor | Accepted for pre-1.0; see [GOVERNANCE.md](./GOVERNANCE.md) access continuity |
| Proxy↔auth gRPC may use plaintext on private networks | Documented; mTLS planned for multi-tenant SaaS |
| Formal pen-test / Phase 5 workshop | Scheduled for production hardening roadmap |

---

## 6) Related documents

- [SECURITY.md](./SECURITY.md) — full threat model and checklists  
- [GOVERNANCE.md](./GOVERNANCE.md) — CVD and access review  
- [OPENSSF_BEST_PRACTICES.md](./OPENSSF_BEST_PRACTICES.md) — badge evidence map  
