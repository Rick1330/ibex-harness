"""Operator drain coordinator — mirrors packages/shutdown intent for FastAPI SSE."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DrainState:
    """Tracks whether the API is draining and which SSE tasks are in flight."""

    draining: bool = False
    _sse_tasks: set[asyncio.Task[None]] = field(default_factory=set)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def begin_drain(self) -> None:
        self.draining = True
        logger.info("api drain began; rejecting new operator SSE connections")

    async def register_sse(self, task: asyncio.Task[None]) -> None:
        async with self._lock:
            if self.draining:
                task.cancel()
                raise RuntimeError("api is draining")
            self._sse_tasks.add(task)
            task.add_done_callback(self._sse_tasks.discard)

    async def wait_sse_drain(self, timeout_seconds: float) -> None:
        async with self._lock:
            pending = list(self._sse_tasks)
        if not pending:
            return
        logger.info("api waiting for %s SSE stream(s) to finish", len(pending))
        done, still = await asyncio.wait(pending, timeout=timeout_seconds)
        for task in still:
            task.cancel()
        if still:
            await asyncio.gather(*still, return_exceptions=True)
            logger.warning("api force-closed %s SSE stream(s) after drain timeout", len(still))
        _ = done
