"""Application runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from app.backend import EmbeddingBackend


@dataclass(slots=True)
class AppState:
    backend: EmbeddingBackend | None = None
    ready: bool = False
    ready_error: str | None = None
