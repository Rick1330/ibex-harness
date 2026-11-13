# Runbook: Context assembly failures / timeouts (P2)

**Scope.** The context assembler (`services/context`, gRPC only) retrieves,
ranks, packs and formats directive + memories under a bounded deadline. It is
loopback-only and is not scraped directly; the proxy's fallbacks and the
context-assembly SLI are the observable surface.

## Symptoms

- Chat responses arrive but carry no injected memories (directive-only fallback).
- `ibex_proxy_context_assemble_seconds` stops advancing while assembled context
  is expected.
- The proxy logs context timeouts; latency p99 stays flat because the proxy
  stopped waiting.
- `IbexContextAssemblySLIAbsent` fires (ticket) while `assembly="enabled"`
  traffic continues.

## Detection

1. The SLI is recorded, not graded. The rules record
   `ibex:context_assemble:p95_5m` and memory-search `p95_5m`; the p95 ≤50 ms /
   p99 ≤100 ms targets are **unratified**, so the only alert is absence
   (`infra/monitoring/prometheus/rules/ibex-slo.yml`:293-353). Do not read a
   green rule as "within SLO".
2. Guard the population: absence only matters when
   `ibex_proxy_nonstreaming_requests_total{assembly="enabled"}` advances. An idle
   stack or an `assembly="disabled"` profile is expected to have no series.
3. Budgets. The assembler waits `min(timeout_ms, deadline_ms)`; defaults are
   45 ms and 40 ms, so a 40 ms deadline cancels slow branches while the timeout
   stays 45 ms (`services/context/app/config.py`:43-46,148-149). Per-dependency
   waits are `directive_timeout_ms`, `hot_timeout_ms`, `cold_timeout_ms`
   (`config.py`:67-79).
4. The proxy never blocks on assembly: on a miss or timeout it degrades to
   directive-only context. The user-visible symptom is thinner context, not a
   failed request.

## First response

1. Confirm the fallback is happening, not a silent success: check the proxy's
   context fallback counter and the assembler's own logs.
2. Check the memory client the assembler calls. It authenticates with a static
   PAT bound to one org (`services/context/app/clients/memory.py`:117); a memory
   outage or an expired PAT surfaces as an assembly timeout.
3. Check the gRPC listener. The assembler is loopback-only and refuses to widen;
   a bind or auth-token mismatch shows as connection refused/unauthorized in the
   proxy logs.

## Recovery

- **Memory or directive dependency down:** restore that dependency; assembly
  resumes without a proxy restart.
- **Deadline too tight for the workload:** widen `IBEX_CONTEXT_DEADLINE_MS`
  only with a measured justification. The 45/40 ms numbers are tuning for the
  declared target, not a guarantee; changing them changes the latency class.
- **Config/auth failure:** restart the assembler after fixing its token/env;
  then confirm `ibex_proxy_context_assemble_seconds_count` advances on a real
  `assembly="enabled"` request.

## Escalation

- Escalate latency questions to the owner of the ratified SLO; do not invent a
  burn threshold for an unratified target.
- Escalate repeated timeouts under normal load as a capacity/regression issue.

## Evidence to keep

- The proxy fallback counter and logs for the affected window.
- Whether `ibex_proxy_context_assemble_seconds_count` was absent, present but
  frozen, or advancing.
- Any config change to the deadline/timeout values, with the measurement behind it.
