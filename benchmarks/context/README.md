# Context assembly load harness (3.5.C.6)

Python async gRPC load script for `ContextAssemblyService.AssembleContext`.

## Stub profile (default)

In-process server + memory stubs. Asserts **p99 < 50ms** at the configured RPS.

Launches are **open-loop**: RPCs are scheduled on a monotonic interval so in-flight
concurrency rises when individual calls exceed the inter-arrival gap (true 500 RPS
issuance, not serial await-per-call).

```bash
# from repo root
bash infra/scripts/context-proto-gen.sh
PYTHONPATH=packages/proto/gen/python:services/context \
  services/context/.venv/bin/python benchmarks/context/assemble_load.py \
  --profile stub --rps 500 --duration 10
```

## Live 100K corpus

1. Seed memories with `benchmarks/memory` HNSW tooling (`MEMORY_BENCH_SIZES=100000`).
2. Run memory HTTP + context gRPC (`python -m app` in `services/context` with
   `IBEX_CONTEXT_MEMORY_BASE_URL` / token / redis configured).
3. Measure:

```bash
PYTHONPATH=packages/proto/gen/python:services/context \
  services/context/.venv/bin/python benchmarks/context/assemble_load.py \
  --profile live --addr 127.0.0.1:9092 --rps 500 --duration 120
```

Live profile prints percentiles and does **not** exit non-zero on p99 failure —
document measured p99 in the PR if the success signal is missed.
