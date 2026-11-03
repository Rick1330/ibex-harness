---
title: How to spend a token budget without losing the plot
date: "2026-10-14"
author: Elshaday Mengesha
authorUrl: "https://github.com/Rick1330"
coverIndex: 3
coverTone: 3
coverLabel: Context budgets
tags:
  - context
  - retrieval
  - architecture
readingTime: 10 min read
excerpt: >
  Context assembly is a bounded selection problem. The interesting engineering
  is not retrieving more memories; it is deciding what to leave out before a
  model ever sees the request.
---

“Retrieve the top ten memories and concatenate them” is not context assembly. It is a way to discover your model’s context limit in production.

A real assembly pipeline has to divide a finite token budget among the response, the directive, recent conversation, tool schemas, formatting overhead, and retrieved memory. It has to do that under a deadline, while retrieval branches fail independently, and it has to leave a clear record of what was excluded and why.

At IBEX Harness, context assembly is a Python gRPC service between the proxy and the provider. The pipeline is implemented and locally tested. The service is provisional because caller authentication at its gRPC boundary and parts of the deadline contract remain open. That distinction is part of the design, not a footnote.

## The budget is subtraction, not guesswork

The usable memory budget is what remains after every other obligation is paid:

```text
usable_budget =
  context_window
  − response_reserve
  − safety_buffer
  − directive_tokens
  − messages_tokens
  − tool_schema_tokens
  − formatter_overhead_tokens
```

Each term has a policy behind it.

The response reserve is bounded at a minimum of 500 tokens, a maximum of 4,096, and by default 15% of the context window, never exceeding the model’s maximum output. The safety buffer is a fraction of the context window from the tokenizer policy. Formatter overhead is estimated before packing, not after, so the packer’s guarantee still means something once tags and section joins are applied.

If the result falls below zero, it is clamped to zero. If the usable budget is below 256 tokens, the assembly is marked constrained. That flag matters: a technically valid request with almost no room for memory is not the same as a healthy one.

Token counts are conservative estimates, not exact tokenizer output. The capability catalog records the estimate kind and tokenizer family so incompatible assumptions fail instead of being silently averaged together.

## Retrieval branches run in parallel, then stop waiting

The service retrieves three things concurrently:

| Branch | Source | Default timeout |
| --- | --- | --- |
| Directive | Redis-backed directive lookup | `5ms` |
| Hot memory | Per-agent recent/high-value memory cache | `15ms` |
| Cold memory | Semantic search in the memory service | `45ms` |

Recent messages are not a fourth branch. They arrive in the request and are counted directly. The session checkpoint table stores message hashes, not message text, so the context service cannot silently read conversation history from it.

The outer retrieval wall is the smaller of the configured client timeout and server deadline: by default `min(45ms, 40ms)`. A slow branch is cancelled; a branch that has already completed is kept. Each branch records `success`, `timeout`, or `error`, and can degrade independently.

This is the difference between a deadline and a timeout. A timeout says “this call must finish.” A deadline says “the request has this much total time, and every child operation shares it.” The second is the only useful contract when three retrievals and a packer are competing for the same milliseconds.

## There are two scores, and they are not the same

A common source of bad benchmarking is comparing numbers that look similar but measure different stages.

The memory service ranks hydrated candidates with a five-part composite:

| Component | Weight |
| --- | --- |
| Relevance | 0.40 |
| Recency | 0.25 |
| Usefulness | 0.20 |
| Confidence | 0.10 |
| Access frequency | 0.05 |

Before that weighted sum, a scoring-time relevance floor drops candidates whose relevance component is too low. The default floor is `0.15`. It must stay below `0.5` because full-text hits use a fixed relevance sentinel of `0.5` when they have no cosine score.

That is separate from the retrieval-time ANN cutoff. The production vector path uses `min_similarity` around `0.70` before hydration. One threshold decides which candidates are worth loading; the other decides which loaded candidates are worth ranking. Conflating them produces nonsense conclusions about recall.

The context packer has a different problem. It consumes `similarity`, `confidence`, and `rank` from the memory HTTP response. Until the memory service exposes its full numeric composite on that wire, the packer uses a clearly labeled interim score:

```text
interim = 0.85 × similarity + 0.15 × confidence
```

The field is named `composite_score` internally for formatter and proto alignment, but it is not the memory-service composite. Per-request weight fields are a forward contract and do not override the formula yet. Naming that honestly is better than presenting an interim heuristic as the final ranking model.

## Packing is a knapsack, not a sort

Once candidates are scored, the packer solves a 0/1 knapsack under the usable token budget. Each candidate has a value and a token cost. The packer can take it or leave it.

The implementation is deliberately pragmatic:

1. Sort by descending interim score, then by memory ID for deterministic ties.
2. Discretize the budget into 16-token buckets.
3. Run a vectorized dynamic program while the table stays under a cell ceiling.
4. Fall back to score-descending greedy packing for very large candidate sets.
5. Repair the result so exact per-memory estimates never exceed the budget.
6. Refill and locally improve after repair instead of accepting floor-bucket waste.
7. Emit packed memories in deterministic order.

The result records whether the DP or greedy path ran, how many candidates were evaluated, how many were excluded for budget, and whether the budget was reached. An empty candidate set is not a truncation. A non-positive budget with candidates present is.

That distinction is operationally useful. “No memories matched” and “memories matched but there was no room” call for different fixes. A dashboard that collapses both into “0 results” hides the actual failure.

## Formatting is a security boundary

The formatter has to turn selected memories into text without letting a memory become markup or instructions.

It applies a fixed order: directive, history, memories, tools. Memory blocks use a per-assembly nonce in the opening tag and an explicit safety sentence telling the model to treat the block as data. Attribute values and bodies are escaped so a memory cannot forge a closing tag or inject an element boundary. The formatter serializes; it never parses memory markup or executes instructions found inside it.

This is why “just put the memories in the system prompt” is not sufficient. Prompt injection is not only a model-alignment problem. It is a serialization problem, and serialization boundaries belong in code.

## Degradation is a feature with a budget

The proxy may continue without assembled context when context is disabled, no client is present, memory is skipped, retrieval fails, or the deadline is exceeded. The fallback is directive-only or history-only context, with metadata recording that assembly was attempted and degraded.

That behavior is intentional. A context outage should not become an inference outage. But degradation is quality loss, not an authorization change. A failed retrieval must never widen visibility, invent a memory, or substitute an unscoped result.

The failure record is part of the product. If the system silently drops memory and returns a confident answer, nobody can tell whether the agent was forgetful or the retrieval branch timed out.

## What the evidence supports

The local pipeline has tests for budget calculation, parallel retrieval, branch timeouts, scoring floors, packing determinism, formatter escaping, and degradation paths. The design is concrete enough to inspect and criticize.

It does not yet support:

- Caller authentication at the context gRPC boundary. Non-loopback use currently trusts caller-supplied organization and agent IDs.
- Exact tokenizer parity with every model.
- A hosted p99 or end-to-end assembly SLO.
- The full five-component memory composite on the context wire.
- A fully reconciled deadline contract between proxy and service.

Those are the reasons the public status is **provisional**, not a reason to describe the pipeline as a sketch. The code exists; the acceptance boundary does not.

## The takeaway

Context assembly is where retrieval quality, latency, security, and token economics meet. You cannot optimize it by retrieving more. You optimize it by making the budget explicit, the deadlines shared, the scores named honestly, the packing deterministic, and the failure modes visible.

The best context window is not the fullest one. It is the one where every token has a reason to be there.

## Read next

- [Assembly pipeline](/docs/context/overview) — service surface, deadlines, and degradation.
- [Ranking and packing](/docs/context/ranking-and-packing) — budget math, two scores, and the knapsack.
- [The memory write path](/blog/memory-write-path) — how the candidate memories are produced.
- [Status and evidence](/docs/architecture/status-and-evidence) — what is implemented, provisional, and open.
