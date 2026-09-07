"""MCP protocol versions IBEX mcp-memory explicitly supports and tests.

Negotiation itself is performed by the pinned ``mcp`` SDK (1.x): on
``initialize``, a requested version in ``SUPPORTED_PROTOCOL_VERSIONS`` is
echoed back; otherwise the SDK returns ``LATEST_PROTOCOL_VERSION``.

E.1 conformance asserts both legacy (``2024-11-05``) and current/latest
(``2025-11-25``) paths. Session resumability / EventStore is intentionally
out of scope (``stateless_http=True``).
"""

from __future__ import annotations

# Explicit E.1 matrix — subset of the SDK's SUPPORTED_PROTOCOL_VERSIONS.
PROTOCOL_VERSION_LEGACY = "2024-11-05"
PROTOCOL_VERSION_LATEST = "2025-11-25"

SUPPORTED_PROTOCOL_VERSIONS: frozenset[str] = frozenset(
    {
        PROTOCOL_VERSION_LEGACY,
        PROTOCOL_VERSION_LATEST,
    }
)

# HTTP header used by Streamable HTTP after initialize (SDK).
MCP_PROTOCOL_VERSION_HEADER = "mcp-protocol-version"
