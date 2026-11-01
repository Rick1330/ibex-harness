# GitHub Copilot instructions — IBEX Harness

Read `AGENTS.md` and `engineering/agent-playbook.md` before suggesting changes. `AGENTS.md` is authoritative; this file
is a short entry point.

## Product shape

IBEX is a self-hosted memory and context layer for multi-tenant AI agents. The Console is the operations plane for the
agent → session → memory → evidence lifecycle and is built with Nuxt 4 + Vue 3 + Nitro (ADR-0088, ADR-0089).

## Non-negotiables

- Keep explicit `org_id` filtering in every data path, even with PostgreSQL RLS. Cross-tenant reads return 404.
- Never emit secrets, tokens, memory content, prompts, or personal data in logs, tests, or examples.
- No placeholder logic, stubbed success handlers, or speculative dependencies.
- Do not weaken lint, tests, coverage, or CI gates.
- Every commit needs `Signed-off-by` (`git commit -s`).
- Surface status is defined in `services/console/shared/operator/surfaces.ts`; do not restate it.

## Validation

Suggest the narrowest relevant commands from `engineering/agent-playbook.md` §6, for example:

```bash
make check
pnpm --filter @ibex/console test && pnpm --filter @ibex/console typecheck && pnpm --filter @ibex/console lint
pnpm site:build && pnpm site:check
```

Use `engineering/DEVELOPMENT_GUIDE.md` §4.4 for real service startup commands. Do not invent `make dev-*` targets.
