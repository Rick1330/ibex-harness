"""Auth domain errors for the management API (re-exported from authclient)."""

from __future__ import annotations

from authclient.errors import AuthFailedError, AuthUnavailableError, OrgSuspendedError

__all__ = ["AuthFailedError", "AuthUnavailableError", "OrgSuspendedError"]
