"""FastAPI host for the memory substrate (probes only in m3.2.1 PR-A)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.http_metrics import HTTPMetricsMiddleware
from app.probes import probe_router

logger = logging.getLogger(__name__)


@dataclass
class MemoryAppState:
    ready: bool = True
    ready_error: str | None = None
    settings: Settings | None = field(default=None, repr=False)


def create_app(*, settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    state = MemoryAppState(settings=cfg)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
        logger.info("memory service starting port=%s", cfg.port)
        state.ready = True
        state.ready_error = None
        try:
            yield
        finally:
            state.ready = False
            logger.info("memory service shutdown complete")

    application = FastAPI(
        title="IBEX Memory",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.memory = state
    application.state.settings = cfg
    application.include_router(probe_router)
    application.add_middleware(HTTPMetricsMiddleware)
    return application


app = create_app()
