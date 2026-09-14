# Operator platform research archive

These audits informed the Phase 4 Track P / D / E redesign. **Published roadmap and engineering pages are the source of truth.** This folder is provenance only.

| File | Summary | Maps to |
|---|---|---|
| [01-operator-product-roadmap-redesign.md](01-operator-product-roadmap-redesign.md) | Track P before D; capability slices; provenance-debugger wedge | Tracks P/D/E, F4-001–014 |
| [02-trace-inspector-data-contract-gaps.md](02-trace-inspector-data-contract-gaps.md) | Join, payload, score, and assembly gaps blocking Trace Inspector | 4.P.2, 4.D.2, F4-003, F4-021–027 |
| [03-fullstack-cross-cutting-gaps-before-track-d.md](03-fullstack-cross-cutting-gaps-before-track-d.md) | Auth secrets/SSRF, budgeting, ranking, packer, readiness | F4-017–020, F4-028–031 |
| [04-world-class-cross-cutting-audit-before-track-d.md](04-world-class-cross-cutting-audit-before-track-d.md) | Fail-open policy, incomplete org deletion, Pub/Sub invalidation, deploy/restore | F4-015–016, F4-018, F4-032–034 |
| [05-trace-inspector-memory-assembly-panel.md](05-trace-inspector-memory-assembly-panel.md) | Three-layer progressive-disclosure Trace Inspector UX | 4.D.2, UI_UX §15, F4-009 |
| [06-composite-score-memory-assembly-panel.md](06-composite-score-memory-assembly-panel.md) | Composite weights, rank-vs-similarity, exclusion groups | 4.D.2, F4-009, F4-025 |

Committed UX grammar for 4.D.2: summary strip + candidate matrix + Explain tree; weights `0.40 / 0.25 / 0.20 / 0.10 / 0.05`; exclusion groups Included / Budget-excluded / Filtered / Failed.

Related published pages:

- [Phase 4 findings](../../../content/roadmap/phase-4-multi-provider/findings.mdx)
- [Phase 4 risks](../../../content/roadmap/phase-4-multi-provider/risks.mdx)
- [Operator platform architecture](../OPERATOR_PLATFORM_ARCHITECTURE.md)
