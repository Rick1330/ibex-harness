"""Shared builders for the deprecation record unit tests (W5.4).

The subject modules live beside this one: ``test_deprecations.py`` covers the
committed record, the record envelope, and the per-entry field rules;
``test_deprecations_paths.py`` the proxy path selector and the duplicate rules; and
``test_deprecations_cross.py`` the REST registry and MCP descriptor cross-checks.

Every synthetic-workspace test runs in ``tmp_path``: this module writes one record,
one REST registry, both MCP descriptors, and the evidence file there, so each
failure mode is isolated and none of them touch PostgreSQL, the app, or the tree.

The script imports its sibling rule modules by bare name, the way it does when run
directly, so the scripts directory is put on ``sys.path`` before the modules are
imported below.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Imported after the path is set up, not at the top of the module, because the
# script modules resolve each other by bare name.
cli = importlib.import_module("check_deprecations")
model = importlib.import_module("deprecations_model")

REST_CONTRACT = "management.agents.read.v1"
EVIDENCE = "engineering/architecture-v2/16-compatibility-and-versioning.md"
GRPC_METHOD = "ibex.memory.v1.MemoryService.GetMemory"
GRPC_CONTRACT = "grpc.memory.get-memory.v1"
MCP_TOOLS = {
    "operator": {"budget.get": "beta"},
    "memory": {"get_memory_lineage": "beta"},
}
MCP_TOOL = "budget.get"
MCP_SERVER = "operator"

NOTICE = date(2026, 1, 1)
TODAY = date(2026, 1, 15)


def sunset(days: int) -> str:
    return (NOTICE + timedelta(days=days)).isoformat()


@dataclass(frozen=True)
class WorkspaceSpec:
    """Overrides for the synthetic registry workspace."""

    rest_stability: str = "stable"
    grpc_stability: str | None = None
    tools: dict[str, dict[str, str]] = field(
        default_factory=lambda: {server: dict(tools) for server, tools in MCP_TOOLS.items()}
    )


def entry(**overrides: Any) -> dict[str, Any]:
    """A valid announced REST deprecation with a 180-day window from its announcement."""
    entry: dict[str, Any] = {
        "id": "dep.agents.read",
        "surface": "rest",
        "contract_id": REST_CONTRACT,
        "successor": "management.agents.v2",
        "stability": "stable",
        "notice_date": NOTICE.isoformat(),
        "announced_on": NOTICE.isoformat(),
        "sunset_date": sunset(180),
        "status": "announced",
        "headers_implemented": True,
        "evidence": EVIDENCE,
    }
    entry.update(overrides)
    return {key: value for key, value in entry.items() if value is not None}


def grpc_entry(**overrides: Any) -> dict[str, Any]:
    """A valid announced gRPC deprecation: no standard header exists, so headers stay false."""
    base: dict[str, Any] = {
        "surface": "grpc",
        "contract_id": GRPC_CONTRACT,
        "headers_implemented": False,
    }
    base.update(overrides)
    return entry(**base)


def mcp_entry(**overrides: Any) -> dict[str, Any]:
    """A valid announced MCP deprecation, defaulting to the beta class of the fixture tool."""
    base: dict[str, Any] = {
        "surface": "mcp",
        "contract_id": None,
        "tool": MCP_TOOL,
        "server": MCP_SERVER,
        "stability": "beta",
        "headers_implemented": False,
    }
    base.update(overrides)
    return entry(**base)


def proxy_entry(**overrides: Any) -> dict[str, Any]:
    """A valid announced proxy deprecation keyed by one exact route path."""
    base: dict[str, Any] = {
        "surface": "proxy",
        "contract_id": None,
        "path": "/v1/chat/completions",
    }
    base.update(overrides)
    return entry(**base)


def entry_stability(entries: list[dict[str, Any]]) -> str:
    """Default the registry row to the recorded class, so a window test needs no spec."""
    if not entries:
        return "stable"
    return str(entries[0].get("stability", "stable"))


def workspace(
    tmp_path: Path,
    entries: list[dict[str, Any]],
    spec: WorkspaceSpec | None = None,
) -> object:
    options = spec or WorkspaceSpec(
        rest_stability=entry_stability(entries), grpc_stability=entry_stability(entries)
    )
    write_registries(tmp_path, options)
    evidence = tmp_path / EVIDENCE
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("", encoding="utf-8")
    record = tmp_path / "deprecations.json"
    record.write_text(
        json.dumps({"schema": cli.SCHEMA, "entries": entries}, indent=2) + "\n",
        encoding="utf-8",
    )
    return cli.DeprecationPaths(
        record=record,
        rest_registry=tmp_path / "rest-route-registry.json",
        mcp_root=tmp_path / "services",
        root=tmp_path,
    )


def write_registries(tmp_path: Path, spec: WorkspaceSpec) -> None:
    rest_row = {
        "key": "GET /v1/agents",
        "contract_id": REST_CONTRACT,
        "owner": "api",
        "stability": spec.rest_stability,
        "status": "shipped",
        "evidence": "services/api/app/routers/agents.py",
    }
    registry = {
        "schema": "ibex.contract-registry.v2",
        "routes": [rest_row],
        "grpc_methods": [
            {
                "key": GRPC_METHOD,
                "contract_id": GRPC_CONTRACT,
                "owner": "api",
                "stability": spec.grpc_stability or "stable",
                "status": "shipped",
                "evidence": "packages/proto/proto/ibex/memory/v1/memory.proto",
            }
        ],
    }
    (tmp_path / "rest-route-registry.json").write_text(
        json.dumps(registry, indent=2) + "\n", encoding="utf-8"
    )
    for server, tools in spec.tools.items():
        server_dir = tmp_path / "services" / f"mcp-{server}"
        server_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "tools": [{"name": name, "stability": stability} for name, stability in tools.items()]
        }
        (server_dir / "mcp_tools.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )


def append_route(tmp_path: Path, stability: str) -> None:
    """Append a second row for the same contract, as a contradictory registry would."""
    path = tmp_path / "rest-route-registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["routes"].append(
        {
            "key": "GET /v1/agents",
            "contract_id": REST_CONTRACT,
            "owner": "api",
            "stability": stability,
            "status": "shipped",
            "evidence": "services/api/app/routers/agents.py",
        }
    )
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def argv(paths: Any) -> list[str]:
    return [
        "--check",
        "--record",
        str(paths.record),
        "--rest-registry",
        str(paths.rest_registry),
        "--mcp-root",
        str(paths.mcp_root),
        "--root",
        str(paths.root),
    ]


def checked(
    tmp_path: Path,
    entries: list[dict[str, Any]],
    *,
    today: date = TODAY,
) -> list[str]:
    return cli.check(workspace(tmp_path, entries), today=today)


def current_entry(days: int) -> dict[str, Any]:
    """An announced entry whose window starts today, so the CLI test never ages out."""
    notice = datetime.now(UTC).date()
    return entry(
        notice_date=notice.isoformat(),
        announced_on=notice.isoformat(),
        sunset_date=(notice + timedelta(days=days)).isoformat(),
    )
