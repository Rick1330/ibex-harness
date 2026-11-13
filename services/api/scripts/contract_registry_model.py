"""The registry file's shape: constants, paths, shared dataclasses, and JSON loading.

``check_contract_registry.py`` is the CLI; the rules that validate one surface
live in the sibling ``contract_registry_*`` modules. This module holds what all
of them share: the schema constants and closed vocabularies, the input paths,
the row and route key types, the two message primitives every failure uses
(``display_path`` and ``root_label``), and the JSON readers.

Standard library only; no network access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[3]

SCHEMA: Final = "ibex.contract-registry.v2"
REQUIRED_FIELDS: Final = ("key", "contract_id", "owner", "stability", "status", "evidence")
GRPC_METHOD_FIELDS: Final = ("key", "contract_id", "owner", "stability", "status", "evidence")
MCP_TOOL_FIELDS: Final = ("key", "contract_id", "server", "owner", "status", "evidence")
STABILITIES: Final = frozenset({"stable", "beta", "internal"})
STATUSES: Final = frozenset({"shipped", "deprecated", "unregistered"})
METHODS: Final = frozenset({"GET", "POST", "PATCH", "PUT", "DELETE"})
METHOD_ACTIONS: Final = {
    "POST": "create",
    "PATCH": "update",
    "PUT": "replace",
    "DELETE": "delete",
}
ACTION_VERBS: Final = frozenset(
    {
        "activate",
        "archive",
        "clear",
        "health",
        "login",
        "logout",
        "me",
        "pause",
        "ping",
        "query",
        "refresh",
        "resolved",
        "stream",
        "summary",
        "suspend",
        "versions",
    }
)
SCAFFOLD_OWNER: Final = "UNASSIGNED"
SCAFFOLD_STABILITY: Final = "internal"
DEFAULT_EVIDENCE: Final = "services/api/app/main.py"
MCP_SERVER_PREFIX: Final = "ibex-mcp-"
MCP_KEY_SEPARATOR: Final = "/"


@dataclass(frozen=True)
class RegistryPaths:
    """Inputs of the check; all overridable so tests never touch the tree."""

    inventory: Path = REPO_ROOT / "services/api/scripts/route_inventory.json"
    registry: Path = REPO_ROOT / "engineering/architecture-v2/contracts/rest-route-registry.json"
    doc: Path = REPO_ROOT / "engineering/architecture-v2/03-contract-registry.md"
    proto_root: Path = REPO_ROOT / "packages/proto/proto"
    mcp_records: tuple[tuple[str, Path], ...] = (
        ("ibex-mcp-memory", REPO_ROOT / "services/mcp-memory/mcp_tools.json"),
        ("ibex-mcp-operator", REPO_ROOT / "services/mcp-operator/mcp_tools.json"),
    )
    root: Path = REPO_ROOT


DEFAULT_PATHS: Final = RegistryPaths()


@dataclass(frozen=True)
class RouteKey:
    """A registry key that has been split into a method and a mounted path."""

    key: str
    method: str
    path: str

    @classmethod
    def parse(cls, key: str) -> RouteKey | None:
        method, _, path = key.partition(" ")
        if method not in METHODS:
            return None
        if not path.startswith("/"):
            return None
        return cls(key=key, method=method, path=path)


@dataclass(frozen=True)
class CheckContext:
    """Inputs every validation helper shares, resolved once per ``check`` run."""

    doc_ids: frozenset[str]
    doc_label: str
    root: Path
    services: dict[str, Path]
    rpcs: dict[str, Path]
    mcp_surfaces: dict[str, tuple[Path, frozenset[str]]]


def route_key(method: str, path: str) -> str:
    return f"{method} {path}"


def non_empty_str(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(value)


def display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def root_label(root: Path) -> str:
    """Name the resolution root for failure messages without printing a bare dot."""
    relative = display_path(root)
    return "the repository root" if relative in {".", ""} else relative


def read_json(path: Path, kind: str) -> tuple[object | None, list[str]]:
    if not path.exists():
        return None, [f"missing-{kind}: {path} does not exist"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as error:
        return None, [f"invalid-{kind}: {path}: {error}"]


def load_registry(path: Path) -> tuple[dict[str, object], list[str]]:
    payload, failures = read_json(path, "registry")
    if failures:
        return {}, failures
    if not isinstance(payload, dict):
        return {}, [f"invalid-registry: {path} must be a JSON object"]
    return payload, []


def schema_failures(registry: dict[str, object]) -> list[str]:
    if registry.get("schema") != SCHEMA:
        return [f"unknown-enum: registry schema is {registry.get('schema')!r}; expected {SCHEMA!r}"]
    return []
