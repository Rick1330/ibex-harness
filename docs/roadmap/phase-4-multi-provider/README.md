# Phase 4: Multi-Provider and Routing

**Status:** Planned  
**Estimated duration:** 4–6 weeks  
**Depends on:** [Phase 3](../phase-3-context-system/README.md) exit

## Theme

Generalize the proxy for **multiple LLM providers**, intelligent routing, and **production-grade rate limiting** in Redis.

## Entry criteria

- Single-provider path stable with context injection
- Redis available in all environments

## Exit criteria

- Provider adapter interface; at least two providers (e.g., OpenAI + Anthropic or Azure OpenAI)
- Model-based routing configuration per org
- Redis Lua rate limits (org/agent/global hierarchy)
- Streaming hardened under slow clients and provider errors
- Circuit breakers on provider and context dependencies

## Goals

See [goals.md](goals.md).
