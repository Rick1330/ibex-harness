"""Unit tests for the memory startup capability-login wrapper.

The check's behaviour is covered once in ``ibex_async_db``; this proves the
memory wrapper supplies the right expected login and label. The live behaviour
under the real capability login is covered by the memory integration suite.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.capability_login import (
    CAPABILITY_LOGIN,
    CapabilityLoginError,
    assert_capability_login,
)


@pytest.mark.asyncio
async def test_assert_capability_login_uses_the_runtime_login() -> None:
    with patch("app.capability_login._assert_capability_login", new=AsyncMock()) as shared:
        await assert_capability_login(MagicMock())  # type: ignore[arg-type]
    _, kwargs = shared.await_args
    assert kwargs == {"expected_login": CAPABILITY_LOGIN, "service_label": "memory"}
    assert CAPABILITY_LOGIN == "ibex_runtime"


def test_capability_login_error_is_the_shared_one() -> None:
    """Lifespan tests catch this class; it must be the shared exception type."""
    from ibex_async_db.capability_login import CapabilityLoginError as Shared

    assert CapabilityLoginError is Shared
