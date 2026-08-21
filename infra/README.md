# infra/

Deployment, local development infrastructure, migrations, and (planned) observability / cloud IaC.

Inventories and phase timing: [`services/README.md`](../services/README.md),
[`web/content/roadmap/`](../web/content/roadmap/). Layout conventions:
[`web/engineering/FILE_STRUCTURE.md`](../web/engineering/FILE_STRUCTURE.md).

This tree is a **planning baseline**. Adding compose profiles (e.g. TEI, vLLM), Helm charts, or
monitoring stacks should land with evidence and, for boundary changes, an ADR.

---

## Available now

| Path | Role |
| --- | --- |
| `compose/dev/` | Local dependencies — [compose/dev/README.md](compose/dev/README.md) (Postgres + pgvector, Redis Stack, ClickHouse, MinIO) |
| `compose/test/` | Minimal Postgres + Redis for Go integration tests (`make compose-test-up`, port 5433) |
| `migrations/` | Postgres (`golang-migrate`) and ClickHouse migrations |
| `scripts/` | Operational / repo-guard helpers used by `Makefile` |
| `testing/` | Shared testing helpers (as present) |
| `tools/` | Small infra tooling (as present) |

---

## Planned / situational (roadmap-aligned)

| Concern | Preferred timing | Notes |
| --- | --- | --- |
| TEI (or equivalent) embedding sidecar | Phase **2.5** | Often an external image (`text-embeddings-inference`) next to `services/embedder/` — may be compose profile, not a new IBEX service |
| Self-hosted LLM reference manifests (vLLM / OpenAI-compatible) | Phase **2.5** | Reference only; applying GPU pools is environmental |
| Tokenizer model asset caching | Phase **2.5** | Bundle or bake `tokenizer.json` for air-gapped deploys |
| Helm / raw k8s charts for proxy, auth, Python services | Phase **4+** (earlier if needed) | Prefer Helm over unchecked raw manifests |
| Terraform modules / envs | Later | Cloud SaaS / enterprise self-host |
| Prometheus / Grafana / Loki / Tempo stack | **Deferred beyond Phase 5** as org-wide hardening | Per-phase metrics still required on each service; full stack is future scope |
| Chaos / load environments | Future hardening | Phase exit gates already demand targeted load/isolation tests |

---

## Changing this inventory

Infra layout may grow or shrink as deploy reality changes. Prefer:

1. Evidence (what broke locally or in CI without the change)
2. Reasoning (why not extend an existing compose/migration path)
3. ADR when introducing a new class of dependency (new datastore, new GPU runtime contract, new multi-cluster topology)
4. Updates to this README and any roadmap milestones that assume the old layout
