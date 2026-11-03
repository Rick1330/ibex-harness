# Context assembly load harness (3.5.C.6)

Python async gRPC load script for `ContextAssemblyService.AssembleContext`.

## Measurement profiles and boundaries

| Profile | Measures | Boundary | Gate status |
| --- | --- | --- | --- |
| Stub (`--profile stub`) | `AssembleContext` RPC latency and request error rate at the configured load | In-process gRPC server and memory stubs; excludes the live memory service, corpus retrieval, and proxy HTTP path | Scheduled/manual `context-benchmark.yml` gate enforces the existing stub p99 and error-rate checks and validates the stub artifact schema |
| Live 100K (`--profile live`) | RPC latency and request error rate against the configured context service with a seeded memory corpus | Exercises the live context and memory services; excludes the proxy HTTP path | Manual run, no CI gate; live results are outside the stub-only artifact schema |
| Proxy overhead (`BenchmarkProxyChatOverheadWithAssemble`) | Warm chat-handler overhead with assembly enabled in [`chat_overhead_bench_test.go`](../../services/proxy/internal/http/chat_overhead_bench_test.go) | Warm auth/directive caches, Redis rate limiting, immediate mock provider, and an always-successful fake assembler; excludes real context RPCs and corpus retrieval | Collected under the `proxy` suite; no dedicated context-assembly p99 gate |

Exit-audit criterion 4 remains **Partial**. The [index criterion](../../engineering/roadmap-archive/legacy-roadmap/phase-3-5-extraction-assembly/index.mdx#L101)
and [goals target](../../engineering/roadmap-archive/legacy-roadmap/phase-3-5-extraction-assembly/goals.mdx#L70)
specify different load conditions. This table selects neither numeric contract.

The `contextAssembly` registry entry and data contract exist. Its reserved
`/benchmarks/context-assembly` Overview is withheld from navigation and the sitemap
because the page route is not implemented.

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

Add `--json site/public/benchmarks/context-assembly-benchmark-data.json` to write
the profile, load settings, request counts, error rate, and latency percentiles
from the same run. Results with successful samples are written before enforcing
the existing error-rate and stub p99 gates; no successful samples still exits 2.

The weekly `context-benchmark.yml` workflow runs this stub invocation, validates
the JSON against `benchmarks/data-schema/context-assembly-benchmark-data.schema.json`
with `validate_published_context_assembly.py --strict`, and uploads it as
`context-assembly-benchmark-data`. The published schema accepts only `profile: "stub"`.

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
