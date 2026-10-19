"""Policy seam tests (bitmap authorize, deny by default)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from authclient.permissions import OPERATOR_METADATA_READ
from support import SAMPLE_OUTPUT_SCHEMA, SampleArgs

from mcp_gateway.policy import BitmapPolicyEvaluator, PolicyDecision
from mcp_gateway.principal import GatewayPrincipal
from mcp_gateway.registry import ToolSpec
from mcp_gateway.scopes import Scope


def _spec() -> ToolSpec:
    return ToolSpec(
        name="sample.get",
        version="v1",
        scope=Scope.OPERATOR_READ,
        description="Sample read tool",
        args_model=SampleArgs,
        output_schema=SAMPLE_OUTPUT_SCHEMA,
        timeout_ms=1000,
        row_limit=50,
    )


@dataclass(frozen=True, slots=True)
class _Stub:
    role: str


async def test_bitmap_allows_when_bit_present() -> None:
    principal = GatewayPrincipal(org_id=uuid4(), permissions=OPERATOR_METADATA_READ)
    result = await BitmapPolicyEvaluator().evaluate(principal, _spec())
    assert result.decision is PolicyDecision.ALLOW
    assert result.scope_satisfied is True


async def test_bitmap_denies_when_bit_absent() -> None:
    principal = GatewayPrincipal(org_id=uuid4(), permissions=0)
    result = await BitmapPolicyEvaluator().evaluate(principal, _spec())
    assert result.decision is PolicyDecision.DENY
    assert result.scope_satisfied is False


async def test_non_read_only_spec_is_denied() -> None:
    principal = GatewayPrincipal(org_id=uuid4(), permissions=OPERATOR_METADATA_READ)
    stub = _Stub(role="write")
    result = await BitmapPolicyEvaluator().evaluate(principal, stub)  # type: ignore[arg-type]
    assert result.decision is PolicyDecision.DENY
