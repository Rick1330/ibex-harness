# IBEX Context (library)

Phase **3.5 Track C** context-assembly building blocks.

## Milestone 3.5.C.1 — Token budget calculator

This package currently ships:

- Generate-and-diff capability catalog: [`data/model_capabilities.v1.json`](data/model_capabilities.v1.json)
- [`app/budget.py`](app/budget.py) — `BudgetCalculator` / `TokenBudget`
- Labeled character/rune estimates ([`app/estimate.py`](app/estimate.py)) — **not** exact tiktoken/HF counts ([follow-up #690](https://github.com/Rick1330/ibex-harness/issues/690))

gRPC `ContextAssemblyService` is **out of scope** here (see milestone **3.5.C.6** / ADR-0067).

### Regenerate the catalog JSON (Go source of truth)

```bash
# from repo root
go run ./packages/provider/scripts/export_capabilities \
  -o services/context/data/model_capabilities.v1.json

# fail-closed freshness check (CI)
go run ./packages/provider/scripts/export_capabilities \
  -check services/context/data/model_capabilities.v1.json
```

### Tests

```bash
cd services/context
uv sync --extra dev
.venv/bin/pytest -q
```
