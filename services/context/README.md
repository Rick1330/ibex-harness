# IBEX Context (library)

Phase **3.5 Track C** context-assembly building blocks.

## Milestone 3.5.C.1 — Token budget calculator

- Generate-and-diff capability catalog: [`app/data/model_capabilities.v1.json`](app/data/model_capabilities.v1.json)
- [`app/budget.py`](app/budget.py) — `BudgetCalculator` / `TokenBudget`
- Labeled character/rune estimates ([`app/estimate.py`](app/estimate.py)) — **not** exact tiktoken/HF counts ([follow-up #690](https://github.com/Rick1330/ibex-harness/issues/690))

## Milestone 3.5.C.2 — Parallel retrieval

- [`app/retrieval.py`](app/retrieval.py) — three-branch fail-open orchestrator (directive Redis + hot/cold HTTP)
- [`app/clients/`](app/clients/) — `MemoryHttpClient`, `RedisDirectiveLookup`
- [`app/config.py`](app/config.py) — `IBEX_CONTEXT_TIMEOUT` (default 45ms) and per-branch budgets

History is **not** a fourth I/O branch: use `AssembleContextRequest.recent_messages` and
`BudgetCalculator` for `history_tokens`. Cold search embeds server-side in memory service.

gRPC `ContextAssemblyService` remains **out of scope** (milestone **3.5.C.6** / ADR-0067).

### Regenerate the catalog JSON (Go source of truth)

```bash
# from repo root
go run ./packages/provider/scripts/export_capabilities \
  -o services/context/app/data/model_capabilities.v1.json

# fail-closed freshness check (CI)
go run ./packages/provider/scripts/export_capabilities \
  -check services/context/app/data/model_capabilities.v1.json
```

### Tests

```bash
cd services/context
bash ../../infra/scripts/context-uv-sync.sh
.venv/bin/pytest -q
```
