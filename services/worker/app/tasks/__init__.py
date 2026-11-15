"""Celery task registration — import submodules so decorators run at startup."""

from app.tasks import billing_reconcile as _billing_reconcile  # noqa: F401
from app.tasks import capture_redaction as _capture_redaction  # noqa: F401
from app.tasks import extraction as _extraction  # noqa: F401
from app.tasks import lifecycle_erasure as _lifecycle_erasure  # noqa: F401
from app.tasks import maintenance as _maintenance  # noqa: F401
from app.tasks import org_deletion as _org_deletion  # noqa: F401
from app.tasks import stubs as _stubs  # noqa: F401
