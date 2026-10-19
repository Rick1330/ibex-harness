"""MCP protocol versions this service explicitly supports and tests."""

from __future__ import annotations

PROTOCOL_VERSION_LEGACY = "2024-11-05"
PROTOCOL_VERSION_LATEST = "2025-11-25"

SUPPORTED_PROTOCOL_VERSIONS: frozenset[str] = frozenset(
    {
        PROTOCOL_VERSION_LEGACY,
        PROTOCOL_VERSION_LATEST,
    }
)

MCP_PROTOCOL_VERSION_HEADER = "mcp-protocol-version"
