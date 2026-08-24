"""FastAPI dependency providers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.state import AppState


def get_embedder_state(request: Request) -> AppState:
    return request.app.state.embedder


SettingsDep = Annotated[Settings, Depends(get_settings)]
AppStateDep = Annotated[AppState, Depends(get_embedder_state)]
