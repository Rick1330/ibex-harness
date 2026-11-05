"""Shared fixtures for ContextAssembly gRPC server tests."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from uuid import uuid4

from pydantic import SecretStr

from app.assemble import ContextAssembler
from app.clients.directive import DirectivePayload
from app.clients.memory import MemoryHitPayload
from app.config import ContextSettings
from app.retrieval import ParallelRetriever

ORG = uuid4()
AGENT = uuid4()
MODEL = "gpt-4o-mini"
# 32+ chars from [A-Za-z0-9_-]; the real token comes from the environment.
SERVICE_TOKEN = "context-test-service-token-0123456789abcdef"


def org_id_text(*, org_id: object = None) -> str:
    """Canonical selector text for the test org (override for tenant B)."""
    return str(ORG if org_id is None else org_id)


def agent_id_text(*, agent_id: object = None) -> str:
    """Canonical selector text for the test agent (override for tenant B)."""
    return str(AGENT if agent_id is None else agent_id)


def settings(**overrides: object) -> ContextSettings:
    base: dict[str, object] = {
        "timeout_ms": 45.0,
        "deadline_ms": 40.0,
        "directive_timeout_ms": 5.0,
        "hot_timeout_ms": 15.0,
        "cold_timeout_ms": 45.0,
        "formatter_nonce_bytes": 16,
        "packer_dp_cell_ceiling": 70 * 6251,
        "packer_max_consecutive_skips": 5,
        "grpc_addr": "127.0.0.1:0",
        "memory_base_url": "",
        "memory_api_token": SecretStr(""),
        "grpc_service_token": SecretStr(SERVICE_TOKEN),
        "redis_url": "",
    }
    base.update(overrides)
    return ContextSettings.model_construct(**base)


class StubDirective:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    async def lookup(self, org_id, agent_id) -> DirectivePayload:
        self.calls.append((org_id, agent_id))
        return DirectivePayload(
            content="Be careful.",
            injection_mode="system_first",
            version_id=None,
        )


@dataclass(frozen=True, slots=True)
class StubHits:
    """Per-path hit overrides; ``None`` keeps the default hit for that path."""

    hot: list[MemoryHitPayload] | None = None
    cold: list[MemoryHitPayload] | None = None


class StubMemory:
    """Optional per-path delays so cold can outlive deadline_ms but not timeout_ms."""

    def __init__(
        self,
        *,
        delay_s: float = 0.0,
        hot_delay_s: float | None = None,
        cold_delay_s: float | None = None,
        hits: StubHits | None = None,
    ) -> None:
        self._hot_delay_s = delay_s if hot_delay_s is None else hot_delay_s
        self._cold_delay_s = delay_s if cold_delay_s is None else cold_delay_s
        self.hot_calls = 0
        self.cold_calls = 0
        overrides = hits or StubHits()
        self._hot_hits = overrides.hot
        self._cold_hits = overrides.cold
        self._hit = MemoryHitPayload(
            memory_id=str(uuid4()),
            org_id=str(ORG),
            agent_id=str(AGENT),
            content="prefers dark mode",
            category="preference",
            confidence=0.9,
            similarity=0.8,
            rank=1,
            source="hot_cache",
        )

    async def get_hot_memories(self, *_args, **_kwargs):
        self.hot_calls += 1
        if self._hot_delay_s:
            await asyncio.sleep(self._hot_delay_s)
        return list(self._hot_hits) if self._hot_hits is not None else [self._hit]

    async def search_memories(self, *_args, **_kwargs):
        self.cold_calls += 1
        if self._cold_delay_s:
            await asyncio.sleep(self._cold_delay_s)
        if self._cold_hits is not None:
            return list(self._cold_hits)
        return [
            MemoryHitPayload(
                memory_id=str(uuid4()),
                org_id=str(ORG),
                agent_id=str(AGENT),
                content="cold fact",
                category="factual",
                confidence=0.8,
                similarity=0.7,
                rank=1,
                source="vector",
            )
        ]


def foreign_hit(*, org_id: object = None, agent_id: object = None) -> MemoryHitPayload:
    """A memory hit that belongs to a tenant other than ORG/AGENT."""
    return MemoryHitPayload(
        memory_id=str(uuid4()),
        org_id=str(org_id or uuid4()),
        agent_id=str(agent_id or uuid4()),
        content="foreign tenant secret",
        category="factual",
        confidence=0.9,
        similarity=0.9,
        rank=1,
        source="vector",
    )


def assembler(
    *,
    delay_s: float = 0.0,
    settings_obj: ContextSettings | None = None,
    memory: StubMemory | None = None,
    directive: StubDirective | None = None,
) -> ContextAssembler:
    cfg = settings_obj or settings()
    retriever = ParallelRetriever(
        settings=cfg,
        memory=memory or StubMemory(delay_s=delay_s),  # type: ignore[arg-type]
        directive=directive or StubDirective(),
    )
    return ContextAssembler(settings=cfg, retriever=retriever)


def principal_class():  # type: ignore[no-untyped-def]
    """The ``ibex.auth.v1.PrincipalContext`` message class."""
    from ibex.auth.v1 import principal_context_pb2

    return principal_context_pb2.PrincipalContext


def principal_message(**overrides: object) -> object:
    """Build a fresh, valid ``PrincipalContext`` for ORG/AGENT (ADR-0096)."""
    issued_at = overrides.pop("issued_at", None)
    expires_at = overrides.pop("expires_at", None)
    fields: dict[str, object] = {
        "org_id": str(ORG),
        "agent_id": str(AGENT),
        "principal_id": "proxy-caller",
        "authority": "AuthService",
    }
    fields.update(overrides)
    message = principal_class()(**fields)
    _set_timestamp(
        message.issued_at,
        time.time() if issued_at is None else float(issued_at),  # type: ignore[arg-type]
    )
    if expires_at is not None:
        _set_timestamp(message.expires_at, float(expires_at))  # type: ignore[arg-type]
    return message


def _set_timestamp(message: object, seconds: float) -> None:
    """Set a proto Timestamp from fractional epoch seconds (protobuf ints only)."""
    message.FromNanoseconds(int(seconds * 1_000_000_000))  # type: ignore[attr-defined]
