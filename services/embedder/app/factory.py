"""Backend factory — profile → EmbeddingBackend implementation.

Fail-closed contract:
  - gpu profile without IBEX_EMBEDDING_TEI_BASE_URL → BackendUnavailableError
  - gpu→stub fallback is explicitly prohibited (geometry lie)
  - cpu and hosted return StubBackend until M3

Public surface consumed by main.py lifespan and test_config.py fixtures.
"""

from __future__ import annotations

import logging

from app.backends.base import EmbeddingBackend
from app.backends.stub import StubBackend
from app.backends.tei import TEIBackend
from app.config import Settings
from app.errors import BackendUnavailableError
from app.registry import BackendRegistry
from app.tei.client import TeiClient, TeiClientConfig
from app.validate import validate_geometry

logger = logging.getLogger(__name__)


def build_backend(settings: Settings) -> EmbeddingBackend:
    """Construct the EmbeddingBackend for the active deployment profile.

    Profile routing:
      cpu     → StubBackend (local MiniLM lands in M3)
      gpu     → TEIBackend; requires tei_base_url or raises immediately
      hosted  → StubBackend (hosted OpenAI/Cohere lands in M3)

    Raises BackendUnavailableError for gpu without URL.
    Never falls back gpu → stub: that silently produces wrong-geometry vectors.
    """
    profile = settings.profile
    if profile == "gpu":
        return _build_tei_backend(settings)
    logger.info("backend profile=%s using stub (M3 will replace)", profile)
    return StubBackend.for_profile(profile)  # type: ignore[arg-type]


def _build_tei_backend(settings: Settings) -> TEIBackend:
    if not settings.tei_base_url:
        raise BackendUnavailableError(
            "gpu profile requires IBEX_EMBEDDING_TEI_BASE_URL — "
            "refusing to fall back to stub (geometry contract)"
        )
    dim, model = settings.resolved_geometry()
    api_key = settings.tei_api_key.get_secret_value() if settings.tei_api_key else None
    client = TeiClient(
        settings.tei_base_url,
        config=TeiClientConfig(
            connect_timeout=settings.tei_connect_timeout_seconds,
            read_timeout=settings.tei_timeout_seconds,
            api_key=api_key,
            max_retries=settings.tei_max_retries,
        ),
    )
    logger.info(
        "TEI backend constructed model_id=%s dimensions=%d",
        model,
        dim,
    )
    return TEIBackend(client, model_id=model, dimensions=dim)


# ------------------------------------------------------------------ #
# Registry + legacy load helper (used by tests and old entry points)  #
# ------------------------------------------------------------------ #

def build_registry() -> BackendRegistry:
    """Construct stub backends for all profiles (used in tests and legacy paths).

    Real GPU backend is not included here — use build_backend(settings) for production.
    """
    backends: dict[str, StubBackend] = {
        profile: StubBackend.for_profile(profile)  # type: ignore[arg-type]
        for profile in ("cpu", "gpu", "hosted")
    }
    return BackendRegistry(backends)


def load_active_backend(settings: Settings | None = None) -> EmbeddingBackend:
    """Select, construct, and geometry-validate the active backend from settings.

    For the gpu profile, constructs a TEIBackend (not a stub).
    Geometry validation is run against resolved settings overrides.
    Used by tests and legacy main entry points.
    """
    cfg = settings or get_settings_lazy()
    backend = build_backend(cfg)
    want_dim, want_model = cfg.resolved_geometry()
    validate_geometry(backend, want_dim, want_model)
    return backend


def get_settings_lazy() -> Settings:
    """Lazy import to avoid circular deps at module load time."""
    from app.config import get_settings
    return get_settings()
