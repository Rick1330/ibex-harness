# IBEX Harness — Governance

This document satisfies OpenSSF Baseline governance criteria (OSPS-GV-01.01, OSPS-GV-01.02, OSPS-GV-04.01) and records access controls that cannot be expressed in git alone.

**Last reviewed:** 2026-07-15

---

## 1) Project members with sensitive-resource access

| Name | GitHub | Role | Sensitive resources |
| --- | --- | --- | --- |
| Elshaday Mengesha | [@Rick1330](https://github.com/Rick1330) | Project lead / maintainer | GitHub repo admin, Actions secrets, Cloudflare deploy, branch protection, OpenSSF badge project owner |

**Sensitive resources** include: repository admin settings, GitHub Actions secrets, production deploy credentials (Cloudflare), branch protection configuration, and OpenSSF Best Practices project administration.

When additional maintainers join, this table must be updated in the same PR that grants access.

---

## 2) Roles and responsibilities

| Role | Responsibilities |
| --- | --- |
| **Project lead** | Roadmap, release approval, security incident response, branch protection, CI policy, OpenSSF badge maintenance |
| **Contributor** | Open PRs from forks or branches; no direct push to `main`; no access to production secrets |
| **Automation (`github-actions[bot]`)** | Version release PRs, SBOM/signing workflows, benchmark bot PRs — scoped tokens only (`GITHUB_TOKEN` or named secrets) |

All human changes merge through pull requests with required CI gates ([ADR-0003](../content/docs/adr/0003-branch-protection-and-merge-policy.mdx)).

---

## 3) Permission escalation review (OSPS-GV-04.01)

Before granting **admin**, **maintain**, or **Actions secrets** access to a new collaborator:

1. Open a tracking issue describing why elevated access is needed.
2. Project lead reviews the request (self-review documented in the issue for solo maintenance).
3. Grant the **minimum** GitHub role required (prefer **Write** over **Admin**).
4. Update the member table in this document in the same change window.
5. Revoke access promptly when the collaborator leaves the project.

**Org-level settings** (verified manually; re-check quarterly):

| Setting | Expected value | Status (2026-07-15) |
| --- | --- | --- |
| MFA for accounts with write/admin (OSPS-AC-01.01) | Enabled | **Verify in GitHub → Settings → Password and authentication** before marking Met on badge form; API tokens often cannot read `two_factor_authentication` |
| Default repository permission (OSPS-AC-02.01) | Lowest / explicit grants only | User-owned solo repo: only @Rick1330 has admin; no other collaborators with write |
| Private vulnerability reporting | Enabled | Repository Security → Private vulnerability reporting |
| DCO / sign-off | Enforced via CONTRIBUTING + CI | [CONTRIBUTING.md](../../CONTRIBUTING.md#developer-certificate-of-origin-dco) |

---

## 4) Public discussion and contribution

| Channel | Purpose |
| --- | --- |
| [GitHub Issues](https://github.com/Rick1330/ibex-harness/issues) | Bug reports, features, questions |
| [GitHub Discussions](https://github.com/Rick1330/ibex-harness/issues) | *(Issues used today; Discussions optional)* |
| Pull requests | Code review and design discussion |

Contributor requirements: [CONTRIBUTING.md](../../CONTRIBUTING.md).

---

## 5) Security assessment (OSPS-SA-03.01)

The project maintains a living security assessment:

- Threat model and controls: [SECURITY.md](./SECURITY.md)
- CI security gates: [ADR-0008](../content/docs/adr/0008-security-ci-gates.mdx)
- Cryptography policy: [ADR-0010](../content/docs/adr/0010-cryptography-policy.mdx)
- Phase 1 validated invariants: SECURITY.md Appendix A (`TestSecurity_SEC*` integration suite)

Formal threat-modeling workshops (OSPS-SA-03.02) are scheduled for Phase 5 production hardening; the documented threat model in SECURITY.md §3 is the current baseline.

---

## 6) Vulnerability disclosure and publication (OSPS-VM-04.01)

- **Private reporting:** [.github/SECURITY.md](../../.github/SECURITY.md) — GitHub Private vulnerability reporting
- **Public advisories:** Published via [GitHub Security Advisories](https://github.com/Rick1330/ibex-harness/security/advisories) when fixes are available
- **Response SLA:** Acknowledge within 5 business days (`.github/SECURITY.md`)

VEX feeds for non-affecting component vulnerabilities (OSPS-VM-04.02) are planned for Phase 5; not yet published.

---

## 7) Related documents

- [CONTRIBUTING.md](../../CONTRIBUTING.md) — PR workflow, DCO, testing policy
- [OPENSSF_BEST_PRACTICES.md](./OPENSSF_BEST_PRACTICES.md) — badge evidence map
- [RELEASING.md](./RELEASING.md) — release integrity and support policy
- [SECURITY.md](./SECURITY.md) — threat model and security controls
