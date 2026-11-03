"""Bearer auth middleware helpers and challenge semantics."""

from __future__ import annotations

from app.middleware import _origin_from_resource, _path_is_protected


def test_path_is_protected_matches_prefix_and_children() -> None:
    prefixes = ("/mcp",)
    assert _path_is_protected("/mcp", prefixes)
    assert _path_is_protected("/mcp/", prefixes)
    assert _path_is_protected("/mcp/session", prefixes)
    assert not _path_is_protected("/health", prefixes)
    assert not _path_is_protected("/mcp-not-really", prefixes)


def test_origin_from_resource_strips_mcp_suffix() -> None:
    assert _origin_from_resource("http://127.0.0.1:8091/mcp") == "http://127.0.0.1:8091"
    assert _origin_from_resource("https://mcp.example.com/mcp") == "https://mcp.example.com"


def test_origin_from_resource_falls_back_to_url() -> None:
    assert _origin_from_resource("http://localhost:9000") == "http://localhost:9000"
