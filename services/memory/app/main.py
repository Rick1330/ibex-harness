"""FastAPI host for the memory substrate."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.auth.client import GRPCTokenValidator, TokenValidator
from app.clients.embedding import EmbeddingClient
from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory
from app.http_metrics import HTTPMetricsMiddleware
from app.idempotency.redis_store import RedisIdempotencyStore
from app.pii.service import PiiService
from app.probes import probe_router
from app.routers.memories import router as memories_router
from app.vectorstore.pgvector_store import PgVectorStore
from app.write.after_commit import AfterCommitHandler
from app.write.cache import MemoryCacheWriter
from app.write.factory import build_embedding_callable, build_write_orchestrator
from app.write.orchestrator import MemoryWriteOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class MemoryAppState:
    ready: bool = True
    ready_error: str | None = None
    settings: Settings | None = field(default=None, repr=False)
    engine: AsyncEngine | None = field(default=None, repr=False)
    session_factory: async_sessionmaker[AsyncSession] | None = field(default=None, repr=False)
    store: PgVectorStore | None = field(default=None, repr=False)
    validator: TokenValidator | None = field(default=None, repr=False)
    redis: Redis | None = field(default=None, repr=False)
    idempotency_store: RedisIdempotencyStore | None = field(default=None, repr=False)
    write_orchestrator: MemoryWriteOrchestrator | None = field(default=None, repr=False)
    embedding_client: EmbeddingClient | None = field(default=None, repr=False)
    pii: PiiService | None = field(default=None, repr=False)


def create_app(
    *,
    settings: Settings | None = None,
    validator: TokenValidator | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    state = MemoryAppState(settings=cfg)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        logger.info("memory service starting port=%s", cfg.port)
        auth = validator or GRPCTokenValidator(
            cfg.auth_grpc_addr,
            timeout_seconds=cfg.auth_timeout_ms / 1000.0,
        )
        state.validator = auth

        if not cfg.database_url:
            state.ready = False
            state.ready_error = "IBEX_MEMORY_DATABASE_URL not set"
            logger.error("memory not ready: %s", state.ready_error)
            yield
            await auth.aclose()
            return

        engine = create_engine(cfg)
        session_factory = create_session_factory(engine)
        store = PgVectorStore(session_factory, cfg)
        pii = PiiService(cfg)
        state.engine = engine
        state.session_factory = session_factory
        state.store = store
        state.pii = pii

        redis_client: Redis | None = None
        cache_writer: MemoryCacheWriter | None = None
        idempotency_store: RedisIdempotencyStore | None = None
        if cfg.redis_url:
            redis_client = Redis.from_url(
                cfg.redis_url,
                socket_connect_timeout=cfg.redis_timeout_seconds,
                socket_timeout=cfg.redis_timeout_seconds,
            )
            state.redis = redis_client
            cache_writer = MemoryCacheWriter(redis_client, cfg)
            idempotency_store = RedisIdempotencyStore(
                redis_client,
                ttl_seconds=cfg.idempotency_ttl_seconds,
                pending_ttl_seconds=cfg.idempotency_pending_ttl_seconds,
            )
            state.idempotency_store = idempotency_store

        embedding_holder: dict[str, EmbeddingClient | None] = {"client": None}
        embed_callable = _build_embed(cfg, embedding_holder)

        after_commit = AfterCommitHandler(
            cache=cache_writer,
            store=store,
        ).__call__

        state.write_orchestrator = build_write_orchestrator(
            cfg,
            session_factory=session_factory,
            store=store,
            pii=pii,
            embed=embed_callable,
            after_commit=after_commit,
        )

        if not await auth.ready():
            state.ready = False
            state.ready_error = "auth gRPC not reachable"
        elif not await _postgres_ready(engine):
            state.ready = False
            state.ready_error = "database not reachable"
        else:
            state.ready = True
            state.ready_error = None

        try:
            yield
        finally:
            state.ready = False
            client = embedding_holder.get("client")
            if client is not None:
                await client.aclose()
            if redis_client is not None:
                await redis_client.aclose()
            await auth.aclose()
            await engine.dispose()
            logger.info("memory service shutdown complete")

    application = FastAPI(
        title="IBEX Memory",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.memory = state
    application.state.settings = cfg
    application.include_router(probe_router)
    application.include_router(memories_router)
    application.add_middleware(HTTPMetricsMiddleware)
    return application


def _build_embed(
    cfg: Settings, holder: dict[str, EmbeddingClient | None]
) -> object:
    token = cfg.embedding_api_token.get_secret_value() if cfg.embedding_api_token else ""
    if not token:
        async def _noop_embed(_text: str) -> list[float]:
            msg = "embedding client not configured"
            raise RuntimeError(msg)

        return _noop_embed

    client = EmbeddingClient(cfg.embedding_base_url, token)
    holder["client"] = client
    return build_embedding_callable(client)


async def _postgres_ready(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except (OSError, SQLAlchemyError) as exc:
        logger.warning(
            "postgres readiness check failed error_class=%s",
            type(exc).__name__,
        )
        return False


app = create_app()
