"""Shared test fixtures for the MCP operator gateway (no database required)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from authclient.permissions import (
    BILLING_READ,
    OPERATOR_METADATA_READ,
    OPERATOR_REDACTED_READ,
    TRACE_READ,
)
from fastapi.testclient import TestClient
from mcp_gateway import GatewayPrincipal, NotFoundError, ToolAuditEvent, ToolContext

from app.auth import StaticTokenValidator
from app.config import Settings
from app.main import CreateAppDeps, create_app
from app.ratelimit import OperatorRateLimiter, RateLimitOutcome
from app.tools import build_registry

ORG = UUID("11111111-1111-1111-1111-111111111111")
ORG_B = UUID("22222222-2222-2222-2222-222222222222")
AGENT = UUID("33333333-3333-3333-3333-333333333333")
SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
RUN_ID = UUID("55555555-5555-5555-5555-555555555555")
TOKEN_A = "tok-org-a"
TOKEN_B = "tok-org-b"
TOKEN_NO_SCOPE = "tok-none"
TOKEN_OPERATOR_ONLY = "tok-operator"
TOKEN_READ_ALL = "tok-read-all"

ALL_SCOPES = OPERATOR_METADATA_READ | TRACE_READ | OPERATOR_REDACTED_READ | BILLING_READ
ISO = "2026-10-19T00:00:00+00:00"

SESSION_PAYLOAD: dict[str, Any] = {
    "session_id": str(SESSION_ID),
    "status": "active",
    "model": "gpt-4o-mini",
    "provider": "openai",
    "agent_id": str(AGENT),
    "turn_count": 3,
    "total_input_tokens": 120,
    "total_output_tokens": 80,
    "created_at": ISO,
    "updated_at": ISO,
    "completed_at": None,
    "secret_content": "must be redacted",
}

RUN_PAYLOAD: dict[str, Any] = {
    "run_id": str(RUN_ID),
    "trace_id": str(SESSION_ID),
    "request_id": "req-1",
    "status": "ok",
    "error_code": None,
    "completeness": "complete",
    "capture_mode": "sampled",
    "sample_decision": "keep",
    "schema_version": "1",
    "agent_id": str(AGENT),
    "session_id": str(SESSION_ID),
    "started_at": ISO,
    "ended_at": ISO,
}

DEFAULT_RESULTS: dict[str, dict[str, Any]] = {
    "session.get": SESSION_PAYLOAD,
    "run.get": RUN_PAYLOAD,
    "evidence.query": {"runs": [RUN_PAYLOAD], "count": 1, "truncated": False},
    "budget.get": {
        "periods": [
            {
                "period_id": str(SESSION_ID),
                "period_start": ISO,
                "period_end": ISO,
                "cap_cents": 5000,
                "spent_cents_cached": 120,
                "enforcement_mode": "alert_only",
            }
        ],
        "count": 1,
        "truncated": False,
    },
}


class CapturingAuditSink:
    name = "capturing"

    def __init__(self) -> None:
        self.events: list[ToolAuditEvent] = []
        self.closed = False

    async def write(self, event: ToolAuditEvent) -> None:
        self.events.append(event)

    async def aclose(self) -> None:
        self.closed = True


class StaticRateLimiter(OperatorRateLimiter):
    def __init__(self, *, allowed: bool = True, limit: int = 120) -> None:
        self.allowed = allowed
        self.limit = limit

    async def check(self, org_id: UUID) -> RateLimitOutcome:
        del org_id
        return RateLimitOutcome(
            allowed=self.allowed,
            limit=self.limit,
            remaining=0 if not self.allowed else self.limit,
            reset_unix=0,
        )


def stub_executor(
    results: Mapping[str, Mapping[str, Any]] | None = None,
) -> Any:
    table = dict(DEFAULT_RESULTS if results is None else results)

    async def executor(ctx: ToolContext, args: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = table.get(ctx.spec.name)
        if payload is None:
            raise NotFoundError(f"{ctx.spec.name} not found")
        return payload

    return executor


def static_validator(*, available: bool = True) -> StaticTokenValidator:
    return StaticTokenValidator(
        {
            TOKEN_A: GatewayPrincipal(org_id=ORG, permissions=ALL_SCOPES, agent_id=AGENT),
            TOKEN_B: GatewayPrincipal(org_id=ORG_B, permissions=ALL_SCOPES, agent_id=AGENT),
            TOKEN_NO_SCOPE: GatewayPrincipal(org_id=ORG, permissions=0, agent_id=AGENT),
            TOKEN_OPERATOR_ONLY: GatewayPrincipal(
                org_id=ORG, permissions=OPERATOR_METADATA_READ, agent_id=AGENT
            ),
            TOKEN_READ_ALL: GatewayPrincipal(
                org_id=ORG,
                permissions=OPERATOR_METADATA_READ | TRACE_READ | OPERATOR_REDACTED_READ,
                agent_id=AGENT,
            ),
        },
        available=available,
    )


def make_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "enabled": True,
        "env": "development",
        "database_url": "postgresql+asyncpg://ibex_app:ibex_app@127.0.0.1:5432/ibex",
        "resource_url": "http://testserver/mcp",
        "auth_server_url": "http://auth.test",
        "auth_grpc_addr": "127.0.0.1:1",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def disabled_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "enabled": False,
        "env": "development",
        "resource_url": "http://testserver/mcp",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_app(
    *,
    settings: Settings | None = None,
    executor: Any | None = None,
    validator: Any | None = None,
    rate_limiter: OperatorRateLimiter | None = None,
    sink: CapturingAuditSink | None = None,
) -> tuple[TestClient, CapturingAuditSink]:
    cfg = settings or make_settings()
    capture = sink or CapturingAuditSink()
    application = create_app(
        settings=cfg,
        deps=CreateAppDeps(
            validator=validator or static_validator(),
            rate_limiter=rate_limiter,
            audit_sink=capture,
            executor=executor if executor is not None else stub_executor(),
        ),
    )
    return TestClient(application), capture


def registry_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in build_registry().specs())
