# Provider Contract

**Status:** `specified`; adapter support is profile- and provider-dependent.

## Identity

A public alias such as `fast`, `balanced`, or `coding` maps to an immutable provider deployment identity. The deployment identity includes provider, model revision, region, credential class, tokenizer family, capability manifest, price source, and effective policy.

## Capability manifest

Manifest fields include streaming, tools, structured output, reasoning fields, modalities, continuation, context limit, tokenizer, usage reporting, retry semantics, residency, cost freshness, and safety tier. Missing, stale, contradictory, or unsupported capability returns a stable `UNSUPPORTED_CAPABILITY` or `NO_ROUTE` error.

## Adapter obligations

Adapters normalize request/response semantics without silently dropping meaning. Conformance covers non-streaming, streaming termination, partial output, tool calls, structured output, usage, continuation, multimodal claims, timeouts, provider errors, retries, and fallback. Chat Completions and Responses are separate contracts; flattening Responses is not lossless.

## Fallback

Fallback is allowed only when the alternative is policy-compatible, capability-compatible, budget-compatible, residency-compatible, and idempotency-safe. Tool side effects and non-idempotent requests are not blindly retried.
