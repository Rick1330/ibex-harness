# Evidence Contract

**Status:** `specified`; existing outbox coverage is partial until the ledger proves otherwise.

## Event envelope

Every evidence event includes event ID, event type/schema version, org/principal/resource, run/request/trace IDs, policy epoch, operation/reservation IDs, source/artifact references, redaction classification, timestamps, outcome, degradation/fallback reason, and retention/legal-hold class.

## Durability

For events required before acknowledgement, the transaction writes canonical state and the outbox atomically. Relay is at-least-once; consumers deduplicate by event ID and projection version. Before applying any replayed event, the consumer checks the authoritative resource tombstone and skips events for deleted resources; a projection or cache cannot resurrect deleted state. Replay is supported from canonical state or retained outbox. ClickHouse and OTel are projections/exporters, not the only durable authority.

## Minimum events

Admission/deny, reservation/release/reconcile, provider attempt/usage, context manifest, memory operation, MCP/tool call, approval, deletion, model decision, artifact promotion, and operator action.

## Privacy

Raw prompts, memory bodies, secrets, tokens, embeddings, and unredacted PII do not enter ordinary logs, metrics, or evidence payloads. Large sensitive bodies use access-controlled redacted artifacts and stable references. Query/export paths enforce tenant scope and retention.
