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

## Milestone 3.5.C.4 — Packer v2 (bounded DP knapsack)

- [`app/packer.py`](app/packer.py) — `ContextPacker` / `ScoredMemory` / `PackedMemories` (numpy DP + greedy fallback)
- [`app/scoring.py`](app/scoring.py) — **interim** packer score from `similarity`/`confidence` only (not memory-service `composite_score`; see [ADR-0069](/docs/adr/0069-context-packer-dp-knapsack))
- [`app/pipeline.py`](app/pipeline.py) — `pack_retrieval(RetrievalResult, TokenBudget, packer=...)` thin glue (no gRPC)

Pack under `TokenBudget.usable_budget`. Path indicator `PackedMemories.path` is `"dp"` or `"greedy"`.
CI asserts packing p99 &lt; 5ms at n=70.

## Milestone 3.5.C.5 — Context formatter

- [`app/formatter.py`](app/formatter.py) — `ContextFormatter` / `FormatRequest` / `FormattedContext` / `CATEGORY_ORDER` ([ADR-0070](/docs/adr/0070-context-formatter-ordering-nonce))
- Locked order: directive → history (`role: content`) → memories by category → optional tool schemas
- Memories wrapped as `<ibex_memory nonce="...">` via `html.escape` serialization + `secrets.token_urlsafe` (`IBEX_CONTEXT_FORMATTER_NONCE_BYTES`, default 16, max 64); bodies/attrs escaped so content cannot forge delimiters (serialize-only — no XML parser)

## Milestone 3.5.C.6 — gRPC service + degradation

- [`app/assemble.py`](app/assemble.py) — `ContextAssembler` (retrieve → budget → score → pack → format; L0–L2)
- [`app/server.py`](app/server.py) — `grpc.aio` `AssembleContext`; `SearchMemories` / `RecordMemoryFeedback` → `UNIMPLEMENTED`
- [`app/config.py`](app/config.py) — `IBEX_CONTEXT_DEADLINE_MS` (default 40), `IBEX_CONTEXT_GRPC_ADDR`
- Load: [`benchmarks/context/assemble_load.py`](../../benchmarks/context/assemble_load.py) ([ADR-0071](/docs/adr/0071-context-grpc-degradation-deadline))

```bash
# stubs for local pb2 (gitignored)
bash infra/scripts/context-proto-gen.sh
cd services/context && bash ../../infra/scripts/context-uv-sync.sh
PYTHONPATH=../../packages/proto/gen/python .venv/bin/python -m app
```

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
