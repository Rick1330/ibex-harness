# Compatibility and Versioning

**Status:** `specified` policy.

## Supported-surface discipline

Declare support separately for OpenAI-compatible Chat Completions, a lossless Responses subset, native Anthropic Messages, MCP Streamable HTTP, optional stdio, provider adapters, SDKs, and framework integrations. Hosted Claude Code, Codex, Cursor, or Copilot paths that bypass IBEX are not governed by IBEX and must be documented as such.

For each client/framework record version, transport, configuration, identity mapping, tested features, known limitations, diagnostics, and last verification. Repository integration is not support evidence.

## Version axes

Contract major, protobuf package/service, REST `/v1`, MCP protocol/tool schema, provider adapter, model deployment, tokenizer, event schema, database migration, SDK/CLI, and feature flag are independent version axes. Record all relevant versions in evidence.

## Change policy

Every breaking change requires ADR, migration, deprecation notice, support window, compatibility fixtures, rollback/roll-forward plan, and current-state update. Additive changes still require examples, generated artifacts, and tests.
