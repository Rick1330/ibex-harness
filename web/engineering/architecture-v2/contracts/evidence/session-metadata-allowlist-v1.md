# Session Evidence Metadata Allowlist v1

**Status:** Proposed runtime binding from the evidence-hardening slice; the accepted evidence contract remains the shape in `web/engineering/architecture-v2/21-g0-owner-decision-record.md`. This artifact does not enable the relay or certify hosted/production operation.

The session producer may assign `metadata` only after `session/evidence.SanitizeRunInput` copies the values below and validates a tenant-scoped active PostgreSQL session fence. The sanitizer is positive-list: fields not listed here are never copied into a metadata-class row. If a listed value fails its structural check, the value is omitted and the entire row is classified `redacted`; missing tenant, agent, session, request, trace identity, producer proof, or matching fence withholds the row. Previously redacted or prohibited input cannot be upgraded to metadata.

| Field path | Certified value shape | Notes |
|---|---|---|
| `org_id`, `agent_id`, `session_id`, `checkpoint_id`, `directive.version_id`, `candidate.memory_id` | Non-zero UUID from server-owned session/request state | No client selector becomes authority. |
| `redaction_class` | `metadata` only after sanitization; `redacted` when any field is removed or downgraded | The producer proof is updated to the exact resulting class; incoming redacted/prohibited declarations are never upgraded. |
| `producer.redaction_class` | Exactly equals the sanitized row's `redaction_class` | The relay validates this equality before projection. |
| `producer.redaction_proof_version`, `producer.source` | Exact `session-metadata-allowlist/v1` version and `proxy.session.evidence` source | Versioned implementation provenance. |
| `producer.resource_type`, `tombstone_fence.resource_type` | `session` | Both refer to the authoritative lifecycle resource. |
| `producer.resource_id`, `tombstone_fence.resource_id` | Session UUID matching the row's `session_id` | Must be identical across both records. |
| `producer.resource_version`, `tombstone_fence.resource_version` | Positive integer from the active PostgreSQL session row | The soft-delete trigger advances the same-row version atomically. |
| `request_id` | 1–128 ASCII letters, digits, `.`, `_`, `:`, or `-` | Stable request correlation only. |
| `trace_id` | Non-zero 32-character W3C hexadecimal ID | Normalized to lower case. |
| `root_span_id`, `metrics_span_id`, `span.span_id`, `span.parent_span_id` | Non-zero 16-character W3C hexadecimal ID | Normalized to lower case. |
| `turn_id`, `candidate.rank`, `candidate.final_rank`, `candidate.token_estimate` | Non-negative integer | No message or memory text. |
| `candidate.delta_rank` | Signed integer rank movement | Negative values are valid when a candidate moves earlier in the final order; no message or memory text. |
| `status` | `ok` or `error` | An upstream free-form error body/code is never included. |
| `model_id` | 1–128 ASCII letters, digits, `.`, `_`, `:`, `+`, `/`, or `-` | Server-selected model identifier only; provider name and raw request fields are not included. |
| `completeness` | `complete`, `partial`, `sampled`, `late`, `redacted`, `expired`, `deleted`, or `simulated` | Unsafe/unrecognized values become `partial` and downgrade classification. |
| `capture_mode` | `metadata`, `redacted`, or `off` | Optional. |
| `sample_decision` | `included`, `sampled`, or `excluded` | Optional. |
| `started_at`, `ended_at`, `span.started_at`, `span.ended_at` | Timestamp values with non-negative interval | End-before-start is clamped and the row is downgraded. |
| `deploy_image_digest` | `sha256:` plus 64 hex characters | Optional deployment provenance. |
| `span.operation_kind` | `proxy.chat` or `context.assemble` | Attributes are not allowlisted. |
| `span.status` | `ok` or `error` | Free-form span error codes are removed. |
| `metrics.stage_durations_ms` | Non-negative integer durations, each at most 1,000,000,000 | Includes the typed assembly stage metrics and candidate count. |
| `token_usage.input_tokens`, `token_usage.output_tokens`, `token_usage.total_tokens` | Non-negative integer totals, each at most 1,000,000,000,000; total is at least input + output | Numeric provider usage only; no prompt, completion, or provider response body. |
| `candidate.scores`, `candidate.score_components` | Finite numeric values; component keys limited to `similarity`, `confidence`, `composite`, `recency`, `token_fit`, `coverage` | Arbitrary score keys are removed and downgrade the row. |
| `candidate.category` | One of `factual`, `preference`, `behavioral`, `episodic`, `procedural` | Mirrors the memory write taxonomy; arbitrary labels are removed and downgrade the row. |
| `candidate.score_schema` | 1–64 ASCII letters, digits, `.`, `_`, `/`, or `-` | Version label only. |
| `candidate.exclusion` | `included`, `none`, `budget`, `filter`, `deduplicated`, `filtered`, `low_confidence`, or `not_selected` | `included` is emitted by the context assembler when no exclusion applies and `filter` when a candidate is filtered; arbitrary explanation text is not allowed. |
| `directive.content_hash` | 64 hex characters, optionally prefixed by `sha256:` | No directive content is included. |

The following are explicitly **not metadata** and are removed or cause the row to be withheld/downgraded: message bodies, tool arguments/results, memory text, provider request/response bodies, arbitrary attributes, provider names, malformed model identifiers, category labels outside the enumerated taxonomy, session event bodies, upstream error strings, authorization material, bearer-token values, secrets, and unrecognized future fields. Numeric token counts are allowed; prompt/completion contents are not. A `redacted` row is persisted only as non-projectable evidence; the current relay must continue to reject it rather than infer safety.

## Producer/fence boundary

`packages/session.PostgresStore.LookupEvidenceFence` reads the active session row by `(org_id, session_id)` under the session RLS policy. The `sessions.deleted_at` soft-delete transition advances `evidence_fence_version` in the same PostgreSQL statement via migration `000041_session_evidence_fence`. Missing, deleted, or cross-tenant rows fail closed. There remains a cross-store time-of-check/time-of-use window between this lookup, the later evidence-outbox transaction, and any ClickHouse projection; this PR does not claim atomic delete-versus-projection fencing.
