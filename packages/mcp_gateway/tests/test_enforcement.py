"""Enforcement pipeline tests (order, fail-closed taxonomy, tenant binding)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import pytest
from authclient.permissions import OPERATOR_METADATA_READ, TRACE_READ
from support import SAMPLE_OUTPUT_SCHEMA, SampleArgs

from mcp_gateway.audit import InMemoryAuditEmitter
from mcp_gateway.enforcement import EnforcerOptions, GatewayEnforcer, RateLimitOutcome
from mcp_gateway.errors import (
    BackendUnavailableError,
    InvalidParamsError,
    PermissionDeniedError,
    PolicyUnavailableError,
    RateLimitedError,
    RateLimitUnavailableError,
    ToolNotFoundError,
)
from mcp_gateway.policy import PolicyDecision, PolicyResult
from mcp_gateway.principal import GatewayPrincipal
from mcp_gateway.registry import ToolRegistry, ToolSpec
from mcp_gateway.scopes import Scope


def _spec(name: str = "sample.get", timeout_ms: int = 1000) -> ToolSpec:
    return ToolSpec(
        name=name,
        version="v1",
        scope=Scope.OPERATOR_READ,
        description="Sample read tool",
        args_model=SampleArgs,
        output_schema=SAMPLE_OUTPUT_SCHEMA,
        timeout_ms=timeout_ms,
        row_limit=50,
    )


def _registry(*specs: ToolSpec) -> ToolRegistry:
    return ToolRegistry(specs or (_spec(),))


def _principal(permissions: int = OPERATOR_METADATA_READ) -> GatewayPrincipal:
    return GatewayPrincipal(org_id=uuid4(), permissions=permissions, agent_id=uuid4())


async def _ok_executor(ctx, args: Mapping[str, Any]) -> Mapping[str, Any]:
    return {"resource_id": args["resource_id"], "status": "ok"}


def _enforcer(executor=_ok_executor, *, registry=None, audit=None, **kwargs) -> GatewayEnforcer:
    return GatewayEnforcer(
        registry or _registry(),
        executor,
        options=EnforcerOptions(
            audit=audit if audit is not None else InMemoryAuditEmitter(),
            **kwargs,
        ),
    )


async def test_success_returns_sanitized_result_and_allows_audit() -> None:
    audit = InMemoryAuditEmitter()
    enforcer = _enforcer(audit=audit)
    result = await enforcer.invoke(_principal(), "sample.get", {"resource_id": "r1"})
    assert result == {"resource_id": "r1", "status": "ok"}
    event = audit.events[-1]
    assert event.success is True
    assert event.decision == "allow"
    assert event.scope_ok is True
    assert event.descriptor_hash.startswith("sha256:")
    assert event.tool_version == "v1"


async def test_unknown_tool_fails_closed_with_audit() -> None:
    audit = InMemoryAuditEmitter()
    principal = _principal()
    enforcer = _enforcer(audit=audit)
    with pytest.raises(ToolNotFoundError) as exc:
        await enforcer.invoke(principal, "nope", {})
    assert exc.value.code == "tool_not_found"
    event = audit.events[-1]
    assert event.tool_name == ""
    assert event.decision == "deny"
    assert event.error_code == "tool_not_found"


async def test_missing_scope_is_denied_and_executor_not_called() -> None:
    calls = {"n": 0}

    async def executor(ctx, args):
        calls["n"] += 1
        return {}

    audit = InMemoryAuditEmitter()
    principal = _principal(permissions=TRACE_READ)
    enforcer = _enforcer(executor, audit=audit)
    with pytest.raises(PermissionDeniedError):
        await enforcer.invoke(principal, "sample.get", {"resource_id": "r1"})
    assert calls["n"] == 0
    event = audit.events[-1]
    assert event.decision == "deny"
    assert event.scope_ok is False
    assert event.error_code == "permission_denied"


async def test_caller_supplied_identity_is_rejected_as_unknown_arg() -> None:
    calls = {"n": 0}

    async def executor(ctx, args):
        calls["n"] += 1
        return {"resource_id": "r1", "status": "ok"}

    args = {"resource_id": "r1", "org_id": str(uuid4()), "agent_id": str(uuid4())}
    principal = _principal()
    enforcer = _enforcer(executor)
    with pytest.raises(InvalidParamsError):
        await enforcer.invoke(principal, "sample.get", args)
    assert calls["n"] == 0


async def test_missing_required_arg_is_invalid_params() -> None:
    audit = InMemoryAuditEmitter()
    principal = _principal()
    enforcer = _enforcer(audit=audit)
    with pytest.raises(InvalidParamsError):
        await enforcer.invoke(principal, "sample.get", {})
    assert audit.events[-1].error_code == "invalid_params"


async def test_rate_limited_denies_before_read() -> None:
    calls = {"n": 0}

    async def executor(ctx, args):
        calls["n"] += 1
        return {}

    class _Limiter:
        async def check(self, org_id):
            return RateLimitOutcome(allowed=False, limit=10, remaining=0, reset_unix=0)

    audit = InMemoryAuditEmitter()
    principal = _principal()
    enforcer = _enforcer(executor, audit=audit, rate_limiter=_Limiter())
    with pytest.raises(RateLimitedError):
        await enforcer.invoke(principal, "sample.get", {"resource_id": "r1"})
    assert calls["n"] == 0
    assert audit.events[-1].error_code == "rate_limited"


async def test_rate_limit_authority_unavailable_fails_closed() -> None:
    class _Limiter:
        async def check(self, org_id):
            raise RateLimitUnavailableError()

    audit = InMemoryAuditEmitter()
    principal = _principal()
    enforcer = _enforcer(audit=audit, rate_limiter=_Limiter())
    with pytest.raises(RateLimitUnavailableError):
        await enforcer.invoke(principal, "sample.get", {"resource_id": "r1"})
    assert audit.events[-1].error_code == "rate_limit_unavailable"


async def test_rate_limiter_sees_principal_org() -> None:
    seen = {}

    class _Limiter:
        async def check(self, org_id):
            seen["org"] = org_id
            return RateLimitOutcome(allowed=True, limit=10, remaining=9, reset_unix=0)

    principal = _principal()
    await _enforcer(rate_limiter=_Limiter()).invoke(principal, "sample.get", {"resource_id": "r1"})
    assert seen["org"] == principal.org_id


async def test_backend_timeout_fails_closed() -> None:
    async def slow(ctx, args):
        await asyncio.sleep(1.0)
        return {"resource_id": "r1", "status": "ok"}

    audit = InMemoryAuditEmitter()
    principal = _principal()
    enforcer = _enforcer(slow, registry=_registry(_spec(timeout_ms=10)), audit=audit)
    with pytest.raises(BackendUnavailableError):
        await enforcer.invoke(principal, "sample.get", {"resource_id": "r1"})
    assert audit.events[-1].error_code == "backend_unavailable"


async def test_backend_error_propagates_as_gateway_error() -> None:
    async def fail(ctx, args):
        raise BackendUnavailableError("db down")

    audit = InMemoryAuditEmitter()
    principal = _principal()
    enforcer = _enforcer(fail, audit=audit)
    with pytest.raises(BackendUnavailableError):
        await enforcer.invoke(principal, "sample.get", {"resource_id": "r1"})
    assert audit.events[-1].error_code == "backend_unavailable"


async def test_policy_unavailable_denies_never_allows() -> None:
    class _Broken:
        async def evaluate(self, principal, spec):
            raise RuntimeError("policy store down")

    audit = InMemoryAuditEmitter()
    principal = _principal()
    enforcer = _enforcer(audit=audit, policy=_Broken())
    with pytest.raises(PolicyUnavailableError):
        await enforcer.invoke(principal, "sample.get", {"resource_id": "r1"})
    event = audit.events[-1]
    assert event.decision == "deny"
    assert event.error_code == "policy_unavailable"


async def test_policy_deny_maps_to_permission_denied() -> None:
    class _Deny:
        async def evaluate(self, principal, spec):
            return PolicyResult(PolicyDecision.DENY, "policy says no")

    principal = _principal()
    enforcer = _enforcer(policy=_Deny())
    with pytest.raises(PermissionDeniedError):
        await enforcer.invoke(principal, "sample.get", {"resource_id": "r1"})


async def test_output_redaction_drops_unlisted_and_sensitive_keys() -> None:
    async def leaky(ctx, args):
        return {
            "resource_id": "r1",
            "status": "ok",
            "content": "secret transcript",
            "detail": {"id": "d1", "content": "raw"},
        }

    result = await _enforcer(leaky).invoke(_principal(), "sample.get", {"resource_id": "r1"})
    assert result == {"resource_id": "r1", "status": "ok", "detail": {"id": "d1"}}


async def test_executor_receives_tenant_bound_context() -> None:
    captured: dict[str, Any] = {}

    async def executor(ctx, args):
        captured["org"] = ctx.org_id
        captured["timeout"] = ctx.timeout_seconds
        return {"resource_id": "r1", "status": "ok"}

    principal = _principal()
    await _enforcer(executor).invoke(principal, "sample.get", {"resource_id": "r1"})
    assert captured["org"] == principal.org_id
    assert captured["timeout"] == 1.0
