# Round 5 Provider Research Evidence

**Access date:** 2026-10-16. This file records implementation provenance for the local `provider-capability-manifest.v1` and `responses.v1` slice. Provider availability, account entitlement, pricing, and hosted/production readiness remain environment-dependent and are not claimed here.

## OpenAI Responses

The Responses API is `POST /v1/responses` and uses ordered typed input/output items rather than a Chat Completions message array. Relevant official sources:

- [https://developers.openai.com/api/reference/resources/responses/methods/create](https://developers.openai.com/api/reference/resources/responses/methods/create) — create-response request schema, model union, input/output/state fields.
- [https://developers.openai.com/api/docs/guides/conversation-state](https://developers.openai.com/api/docs/guides/conversation-state) — `previous_response_id`, Conversations, manual replay, and storage semantics.
- [https://developers.openai.com/api/docs/guides/reasoning](https://developers.openai.com/api/docs/guides/reasoning) — reasoning effort and preservation semantics.
- [https://developers.openai.com/api/docs/guides/function-calling](https://developers.openai.com/api/docs/guides/function-calling) — `function_call`, `function_call_output`, `call_id`, strict schemas, and tool choice.
- [https://developers.openai.com/api/docs/guides/structured-outputs](https://developers.openai.com/api/docs/guides/structured-outputs) — Responses JSON Schema syntax via `text.format`.
- [https://developers.openai.com/api/docs/guides/streaming-responses](https://developers.openai.com/api/docs/guides/streaming-responses) — semantic SSE events and terminal states.
- [https://developers.openai.com/api/reference/resources/responses/streaming-events/](https://developers.openai.com/api/reference/resources/responses/streaming-events/) — event union, sequence numbers, output-item lifecycle, failed/incomplete/error events.
- [https://developers.openai.com/api/docs/models](https://developers.openai.com/api/docs/models) — current model availability and capabilities; mutable and account-dependent.
- [https://developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing) — mutable pricing snapshot; not used as a budget authority.
- [https://github.com/openai/openai-java/blob/main/openai-java-core/src/main/kotlin/com/openai/models/responses/ResponseOutputItem.kt](https://github.com/openai/openai-java/blob/main/openai-java-core/src/main/kotlin/com/openai/models/responses/ResponseOutputItem.kt) — official SDK forward-compatible unknown item/raw JSON behavior.
- [https://github.com/openai/openai-java/blob/main/openai-java-core/src/main/kotlin/com/openai/models/responses/ResponseStreamEvent.kt](https://github.com/openai/openai-java/blob/main/openai-java-core/src/main/kotlin/com/openai/models/responses/ResponseStreamEvent.kt) — official SDK forward-compatible unknown event/raw JSON behavior.

Implementation conclusions: preserve exact raw discriminator and raw JSON for unknown items/events; retain order; do not execute unknown items; only treat finalized output items as semantically complete; keep `call_id`, `previous_response_id`, and server idempotency keys distinct; unsupported state/reasoning fields must be typed errors.

## Anthropic

The shipped IBEX adapter is Chat Completions-facing and calls native `POST /v1/messages`; it is text-only for the exposed surface. It does not implement an OpenAI Responses endpoint. Official sources:

- [https://platform.claude.com/docs/en/api/overview](https://platform.claude.com/docs/en/api/overview) — native API surface and model discovery.
- [https://platform.claude.com/docs/en/api/messages](https://platform.claude.com/docs/en/api/messages) — native messages, tools, vision, and thinking fields.
- [https://platform.claude.com/docs/en/models/overview](https://platform.claude.com/docs/en/models/overview) — current model capabilities and limits.
- [https://platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing) — pricing and long-context qualifications.
- [https://platform.claude.com/docs/en/build-with-claude/streaming](https://platform.claude.com/docs/en/build-with-claude/streaming) — SSE streaming behavior.
- [https://platform.claude.com/docs/en/build-with-claude/structured-outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) — native structured output support.
- [https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use) — strict tool schema support.
- [https://platform.claude.com/docs/en/build-with-claude/vision](https://platform.claude.com/docs/en/build-with-claude/vision) — image input.
- [https://platform.claude.com/docs/en/build-with-claude/thinking](https://platform.claude.com/docs/en/build-with-claude/thinking) — model-specific thinking behavior.
- [https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk](https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk) — Chat Completions compatibility, not Responses.
- [https://platform.claude.com/docs/en/api/models/list](https://platform.claude.com/docs/en/api/models/list) — account-specific model authority.

Implementation conclusions: do not advertise Anthropic tools, JSON/schema, vision, or reasoning through the current IBEX adapter unless the adapter is extended; manifest entries describe the shipped adapter, not vendor-native capabilities. No Anthropic Responses support is claimed.

## Model selection policy

The initial manifest is intentionally limited to models already allowlisted by the repository. It records only claims supported by provider documentation and adapter behavior. New flagship/current model IDs require a separate authenticated account-availability check, adapter allowlist change, capability evidence, and tests; they are not silently added merely because a provider catalog lists them. Pricing fields are informational provenance, not budget reservation or billing authority; GAP-006 remains open.
