# Phase 5: Production Hardening

**Status:** Planned  
**Estimated duration:** 4–8 weeks  
**Depends on:** [Phase 4](../phase-4-multi-provider/README.md) exit

## Theme

Make IBEX Harness **operable at production SLOs**: full observability stack, resilience testing, security review, and CI strictness aligned with risk.

## Entry criteria

- Core product paths feature-complete for MVP (memory, context, multi-provider proxy)
- Staging environment definition in DEPLOYMENT.md understood

## Exit criteria

- OTel collectors + Grafana dashboards per MONITORING.md
- Runbooks exercised for top incidents
- Load tests meet PERFORMANCE.md proxy budgets
- `go-services` and `golangci-lint` promoted to required checks (if stable)
- Security checklist pass for MVP scope
- GDPR deletion flow designed or stubbed with fail-closed behavior

## Goals

See [goals.md](goals.md).
