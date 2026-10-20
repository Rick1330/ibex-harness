# mcp-runtime

Shared ASGI runtime primitives for the IBEX MCP memory and operator services:

- golden-signal HTTP metrics (with route collapsing for `/mcp`)
- fail-closed bearer authentication middleware
- org-scoped calendar-minute rate limiting (Redis Lua, fail-open only in development)

The package is intentionally transport-agnostic and contains no service-specific
configuration or audit event schemas; services inject those through callbacks.
