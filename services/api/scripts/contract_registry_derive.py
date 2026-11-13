"""Contract ID derivation and key parsing for all three registry surfaces.

One rule per surface, applied mechanically (the full grammar is in the module
docstring of ``check_contract_registry.py``)::

    <surface>.<resource>.<action>.v1        REST
    grpc.<package-leaf>.<rpc-kebab>.v1      gRPC
    mcp.<server-leaf>.<tool-kebab>.v1       MCP

``is_valid_contract_id`` reuses the document extractor's grammar rather than a
second definition, so a derived ID and a documented ID cannot disagree.

Standard library only; no I/O.
"""

from __future__ import annotations

import re
from typing import Final

from contract_ids import documented_contract_ids
from contract_registry_model import (
    ACTION_VERBS,
    MCP_KEY_SEPARATOR,
    MCP_SERVER_PREFIX,
    METHOD_ACTIONS,
)

SURFACE_PREFIXES: Final = {"operator": "/v1/operator/", "management": "/v1/"}
PROTO_VERSION_SEGMENT: Final = "v1"


def _surface(path: str) -> str:
    for surface, prefix in SURFACE_PREFIXES.items():
        if path.startswith(prefix):
            return surface
    return "platform"


def _path_segments(path: str, surface: str) -> list[str]:
    remainder = path.removeprefix(SURFACE_PREFIXES.get(surface, "/"))
    return [segment for segment in remainder.split("/") if segment]


def _has_leading_scope(segments: list[str]) -> bool:
    if len(segments) < 2:
        return False
    if segments[0].startswith("{"):
        return False
    return segments[1].startswith("{")


def _scope_and_statics(segments: list[str]) -> tuple[str, list[str]]:
    statics = [segment for segment in segments if not segment.startswith("{")]
    if not _has_leading_scope(segments):
        return "", statics
    return statics.pop(0), statics


def _pop_trailing_action(statics: list[str], scope: str) -> str:
    if not statics:
        return ""
    if statics[-1] not in ACTION_VERBS:
        return ""
    if len(statics) == 1 and not scope:
        return ""
    return statics.pop()


def _resource_name(statics: list[str], scope: str, surface: str) -> str:
    joined = "-".join(statics)
    if joined:
        return joined
    if scope:
        return scope
    return surface


def _action_for(method: str, path: str) -> str:
    if method == "GET":
        return "get" if path.endswith("}") else "read"
    return METHOD_ACTIONS[method]


def derive_contract_id(method: str, path: str) -> str:
    """Derive the one contract ID for a mounted route (see the CLI module docstring)."""
    surface = _surface(path)
    segments = _path_segments(path, surface)
    scope, statics = _scope_and_statics(segments)
    action = _pop_trailing_action(statics, scope)
    resource = _resource_name(statics, scope, surface)
    if not action:
        action = _action_for(method, path)
    return f"{surface}.{resource}.{action}.v1"


def _kebab(name: str) -> str:
    """``BeginTotpEnrollment`` -> ``begin-totp-enrollment`` (acronym-safe)."""
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", name)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", spaced)
    return spaced.lower()


def _package_leaf(package: str) -> str:
    """The package segment that names the surface: ``ibex.auth.v1`` -> ``auth``."""
    segments = [segment for segment in package.split(".") if segment]
    if len(segments) > 1 and segments[-1] == PROTO_VERSION_SEGMENT:
        segments.pop()
    return segments[-1] if segments else ""


def grpc_contract_id(method_key: str) -> str:
    """Derive the contract ID for a fully-qualified rpc name, or ``""`` when malformed."""
    segments = method_key.split(".")
    if len(segments) < 3:
        return ""
    leaf = _package_leaf(".".join(segments[:-2]))
    if not leaf:
        return ""
    return f"grpc.{leaf}.{_kebab(segments[-1])}.v1"


def mcp_contract_id(server: str, tool: str) -> str:
    """Derive the contract ID for a published MCP tool, or ``""`` when malformed."""
    leaf = server.removeprefix(MCP_SERVER_PREFIX) or server
    tool_leaf = tool.replace(".", "-").replace("_", "-").lower()
    if not leaf or not tool_leaf:
        return ""
    return f"mcp.{leaf}.{tool_leaf}.v1"


def is_valid_contract_id(candidate: str) -> bool:
    """True when the ID matches the documented grammar (the document extractor's rule)."""
    return bool(candidate) and documented_contract_ids(candidate) == {candidate}


def grpc_method_parts(key: str) -> tuple[str, str] | None:
    """Split a ``grpc_methods`` key into ``(service, rpc)``, or ``None`` when malformed."""
    segments = key.split(".")
    if len(segments) < 3:
        return None
    return ".".join(segments[:-1]), segments[-1]


def mcp_tool_parts(key: str) -> tuple[str, str] | None:
    """Split a ``mcp_tools`` key into ``(server, tool)``, or ``None`` when malformed."""
    server, separator, tool = key.partition(MCP_KEY_SEPARATOR)
    if not separator or MCP_KEY_SEPARATOR in tool:
        return None
    if not server or not tool:
        return None
    return server, tool
