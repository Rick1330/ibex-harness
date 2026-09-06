"""Shared fixtures for ContextAssembly gRPC server tests."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.assemble import ContextAssembler
from app.clients.directive import DirectivePayload
from app.clients.memory import MemoryHitPayload
from app.config import ContextSettings
from app.retrieval import ParallelRetriever

ORG = uuid4()
AGENT = uuid4()
MODEL = "gpt-4o-mini"


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
        "memory_api_token": "",
        "redis_url": "",
    }
    base.update(overrides)
    return ContextSettings.model_construct(**base)


class StubDirective:
    async def lookup(self, org_id, agent_id) -> DirectivePayload:
        return DirectivePayload(
            content="Be careful.",
            injection_mode="system_first",
            version_id=None,
        )


class StubMemory:
    """Optional per-path delays so cold can outlive deadline_ms but not timeout_ms."""

    def __init__(
        self,
        *,
        delay_s: float = 0.0,
        hot_delay_s: float | None = None,
        cold_delay_s: float | None = None,
    ) -> None:
        self._hot_delay_s = delay_s if hot_delay_s is None else hot_delay_s
        self._cold_delay_s = delay_s if cold_delay_s is None else cold_delay_s
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
        if self._hot_delay_s:
            await asyncio.sleep(self._hot_delay_s)
        return [self._hit]

    async def search_memories(self, *_args, **_kwargs):
        if self._cold_delay_s:
            await asyncio.sleep(self._cold_delay_s)
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


def assembler(
    *,
    delay_s: float = 0.0,
    settings_obj: ContextSettings | None = None,
    memory: StubMemory | None = None,
) -> ContextAssembler:
    cfg = settings_obj or settings()
    retriever = ParallelRetriever(
        settings=cfg,
        memory=memory or StubMemory(delay_s=delay_s),  # type: ignore[arg-type]
        directive=StubDirective(),
    )
    return ContextAssembler(settings=cfg, retriever=retriever)
