# Async Intelligence and DecisionService

**Status:** `design-intent` / proposed; no DecisionService runtime is shipped by this baseline.

## Permitted role

Optional local models such as GLiNER2.5-Decide may classify memory candidates, intent, priority, retrieval profile, review risk, or routing hints after deterministic authorization and bounded feature construction. They may abstain, quarantine, or recommend review.

They must not authenticate, authorize, widen scope, approve tools, decide deletion/legal hold, grant budget, set residency, promote policy, or perform irreversible effects. Confidence is not permission or evidence of why a result is true.

## Contract and registry

A future pure side-effect-free DecisionService uses protobuf/gRPC and returns decision/labels, raw scores, calibrated probabilities where supported, abstention/reason, model version/digest, preprocessing and ontology hashes, calibration version, evidence ID, latency, and fallback reason. Postgres owns approval/rollout/last-known-good; immutable artifacts are signed and stored separately.

## Rollout

Benchmark alternatives → pinned replay → shadow with no side effects → sticky low-risk canary → gated promotion → rollback/re-evaluation. Benchmark cold/warm p50/p95/p99, RSS, CPU, queue, concurrency, quality, calibration, abstention, adversarial behavior, and tenant isolation. Vendor results are not IBEX evidence. Keep transformer inference off the Go hot path by default.

## Worker contract

Every job has tenant scope, operation ID, idempotency key, bounded queue, timeout, retry/DLQ, cancellation, evidence link, and deterministic projection effects. Worker/model output is a candidate or recommendation until a deterministic executor or authorized operator applies it.
