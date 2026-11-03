---
description: Run the local security gate — secrets, SAST, dependencies, and the SonarQube/Codacy security findings — before pushing.
---

Run before any push that touches code, dependencies, configuration, auth, or infrastructure.

## 1. Secrets

```bash
gitleaks detect --source . --config .gitleaks.toml --redact
```

Any hit is a stop-the-line event: remove the secret, rotate it, and check whether it reached a commit.

## 2. SAST

```bash
semgrep --config .semgrep/rules/ --error .
```

Plus `sonarqube_search_security_hotspots` for the project (`Rick1330_ibex-harness`) and
`codacy_search_repository_srm_items` (`gh` / `Rick1330` / `ibex-harness`) for SAST, secrets, SCA, IaC, and CI/CD
findings.

## 3. Dependencies

```bash
trivy fs --severity CRITICAL,HIGH --ignore-unfixed .
osv-scanner --recursive .
```

Fix, upgrade, or document each finding. Do not suppress a CRITICAL or HIGH without a written rationale.

## 4. Tenant isolation and auth

For changes that touch data access or authentication, confirm in the diff:

- every query filters `org_id`;
- no endpoint lacks an explicit auth/permission declaration;
- cross-tenant tests exist and pass;
- no secrets or raw memory content in logs.

## 5. Report

List each finding with severity, whether it was fixed, and the evidence. A finding you chose not to fix must have a
written reason and a follow-up issue.
