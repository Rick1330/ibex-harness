"""Backend factory — profile → EmbeddingBackend implementation.

Fail-closed contract:
  - gpu profile without IBEX_EMBEDDING_TEI_BASE_URL → BackendUnavailableError
  - gpu→stub fallback is explicitly prohibited (geometry lie)
  - hosted without IBEX_EMBEDDING_HOSTED_API_KEY → BackendUnavailableError
  - hosted→stub fallback is explicitly prohibited
  - cpu returns StubBackend (local MiniLM is a future milestone, not M3)

Public surface consumed by main.py lifespan and test_config.py fixtures.
"""

from __future__ import annotations

import logging

from app.backends.base import EmbeddingBackend
from app.backends.hosted import HostedAPIBackend
from app.backends.stub import StubBackend
from app.backends.tei import TEIBackend
from app.config import Settings
from app.errors import BackendUnavailableError
from app.hosted.client import HostedClient, HostedClientConfig
from app.hosted.providers import provider_defaults
from app.registry import BackendRegistry
from app.tei.client import TeiClient, TeiClientConfig
from app.validate import validate_geometry

logger = logging.getLogger(__name__)


def build_backend(settings: Settings) -> EmbeddingBackend:
    """Construct the EmbeddingBackend for the active deployment profile.

    Profile routing:
      cpu     → StubBackend (local MiniLM is deferred; not G4.M3)
      gpu     → TEIBackend; requires tei_base_url or raises immediately
      hosted  → HostedAPIBackend; requires hosted_api_key or raises immediately

    Raises BackendUnavailableError for gpu without URL or hosted without key.
    Never falls back gpu/hosted → stub: that silently produces wrong-geometry vectors.
    """
    profile = settings.profile
    if profile == "gpu":
        return _build_tei_backend(settings)
    if profile == "hosted":
        return _build_hosted_backend(settings)
    logger.info("backend profile=%s using stub", profile)
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


def _build_hosted_backend(settings: Settings) -> HostedAPIBackend:
    provider = settings.hosted_provider
    if provider == "voyage":
        raise BackendUnavailableError(
            "hosted provider 'voyage' is not implemented yet — "
            "use IBEX_EMBEDDING_HOSTED_PROVIDER=openai|cohere"
        )
    if settings.hosted_api_key is None or not settings.hosted_api_key.get_secret_value().strip():
        raise BackendUnavailableError(
            "hosted profile requires IBEX_EMBEDDING_HOSTED_API_KEY — "
            "refusing to fall back to stub (geometry contract)"
        )
    dim, model = settings.resolved_geometry()
    defaults = provider_defaults(provider)
    base_url = settings.hosted_base_url or defaults.base_url
    api_key = settings.hosted_api_key.get_secret_value().strip()
    client = HostedClient(
        base_url,
        api_key,
        config=HostedClientConfig(
            connect_timeout=settings.hosted_connect_timeout_seconds,
            read_timeout=settings.hosted_timeout_seconds,
            max_retries=settings.hosted_max_retries,
            provider=provider,  # type: ignore[arg-type]
            model_id=model,
            dimensions=dim,
        ),
    )
    logger.info(
        "hosted backend constructed provider=%s model_id=%s dimensions=%d",
        provider,
        model,
        dim,
    )
    return HostedAPIBackend(client, provider=provider, model_id=model, dimensions=dim)


# ------------------------------------------------------------------ #
# Registry + legacy load helper (used by tests and old entry points)  #
# ------------------------------------------------------------------ #

def build_registry() -> BackendRegistry:
    """Construct stub backends for all profiles (used in tests and legacy paths).

    Real GPU/hosted backends are not included here — use build_backend(settings).
    """
    backends: dict[str, StubBackend] = {
        profile: StubBackend.for_profile(profile)  # type: ignore[arg-type]
        for profile in ("cpu", "gpu", "hosted")
    }
    return BackendRegistry(backends)


def load_active_backend(settings: Settings | None = None) -> EmbeddingBackend:
    """Select, construct, and geometry-validate the active backend from settings.

    For gpu/hosted, constructs the real backend (not a stub).
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
