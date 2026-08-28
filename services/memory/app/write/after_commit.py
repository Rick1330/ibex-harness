"""After-commit cache update + vector index upsert (best-effort)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.exc import DBAPIError

from app.vectorstore.base import UpsertRequest, VectorStore
from app.write.cache import MemoryCacheWriter
from app.write.metrics import WRITE_CACHE_ERRORS
from app.write.models import WriteOutcome, WriteOutcomeKind

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AfterCommitHandler:
    cache: MemoryCacheWriter | None
    store: VectorStore | None
    embedding_model: str = "bge-m3"

    async def __call__(self, outcome: WriteOutcome) -> None:
        if outcome.kind != WriteOutcomeKind.CREATED:
            return
        try:
            if self.cache is not None:
                await self.cache.write_created(outcome)
        except Exception:
            WRITE_CACHE_ERRORS.labels(op="cache_write").inc()
            logger.warning(
                "cache write failed org_id=%s memory_id=%s",
                outcome.memory.org_id,
                outcome.memory.id,
                exc_info=True,
            )
        if self.store is None or outcome.embedding is None:
            return
        try:
            await self.store.upsert(
                UpsertRequest(
                    memory_id=outcome.memory.id,
                    org_id=outcome.memory.org_id,
                    embedding=list(outcome.embedding),
                    embedding_model=outcome.embedding_model or self.embedding_model,
                )
            )
        except (LookupError, OSError, DBAPIError):
            WRITE_CACHE_ERRORS.labels(op="vector_upsert").inc()
            logger.warning(
                "vector upsert failed org_id=%s memory_id=%s",
                outcome.memory.org_id,
                outcome.memory.id,
            )
