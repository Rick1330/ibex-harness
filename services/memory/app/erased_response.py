"""The content-free marker a forgotten memory's idempotent response becomes.

Forget erases the memory row and the idempotent create response that stored its
body. The ledger row itself is kept — replaying the original key must not
re-create the forgotten resource — so it holds this marker instead of the
response, and the replay path answers with a non-success error rather than
serving a 201 whose body no longer matches the contract.
"""

from __future__ import annotations

import json

ERASED_MARKER_TEXT = '{"erased": true}'
ERASED_MARKER_BODY = ERASED_MARKER_TEXT.encode("utf-8")


def is_erased_marker(payload: bytes | None) -> bool:
    """Return True when ``payload`` is exactly the erased-create marker."""
    if not payload:
        return False
    try:
        return json.loads(payload) == {"erased": True}
    except (TypeError, ValueError):
        return False
