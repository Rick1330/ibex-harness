"""Celery task registration — import submodules so decorators run at startup."""

from app.tasks import maintenance as _maintenance  # noqa: F401
from app.tasks import stubs as _stubs  # noqa: F401
