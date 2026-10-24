# Context and Memory Contract

**Status:** `specified` target contract.

## Typed classes

Working/session state and checkpoints, episodic observations, semantic facts, profiles/preferences, reviewed procedures, repository/project artifacts, tool/evidence records, and safety/negative records are separate classes. They have different owners, retention, retrieval, and promotion rules.

## Context compilation

1. Verify principal, purpose, resource scope, policy epoch, retention, and status.
2. Retrieve exact-key checkpoints/session state.
3. Hard-filter active authorized durable projections.
4. Rank/retrieve only within the filtered candidate set.
5. Pack with the authoritative tokenizer and explicit reservations.
6. Render directives outside untrusted data.
7. Escape and label memory, repository, MCP, and tool content as reference data.
8. Return rendered context **and** a typed `ContextEnvelope`.

`ContextEnvelope` includes ordered items, source IDs, type/trust labels, scope, provenance, redaction status, source version/commit, token counts, omissions/truncation, directive/policy versions, retrieval profile, cache state, and degradation reason.

A classifier, embedding score, cache hit, or memory body cannot widen visibility. The context service is a read/compile boundary, not a lifecycle or authorization authority.
