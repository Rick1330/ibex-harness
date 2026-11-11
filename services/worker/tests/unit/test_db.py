"""Unit tests for the worker database helpers.

Engine construction is covered first. The rest fakes the async session so the
pinned-scope contract -- statement order, bound parameters, rollback on failure,
non-reflection of caller input -- is asserted without a DSN. No database is
opened: the live behaviour under a ``NOINHERIT`` login is covered by
tests/integration/test_worker_tenant_pinning_postgres.py.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Self

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db import (
    _bind_org,
    _pin_role,
    app_org_scope,
    app_probe_scope,
    create_engine,
    create_session_factory,
    session_as_app,
    session_as_app_org,
    session_as_purge_org,
    session_unpinned,
)

_ORG_ID = "11111111-1111-1111-1111-111111111111"
# Mirrors app.db._SET_ORG_SQL: the org id is a bind parameter, never literal SQL.
_ORG_GUC = "SELECT set_config('app.current_org_id', :org_id, true)"


def test_create_engine_requires_database_url() -> None:
    settings = Settings(database_url=None)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_engine(settings)


def test_create_engine_masks_bound_parameters() -> None:
    """A DBAPIError's text must never carry the statement's parameters."""
    settings = Settings(database_url="postgresql://u:p@localhost/ibex?sslmode=disable")
    engine = create_engine(settings)
    assert engine.sync_engine.hide_parameters is True


def test_create_session_factory() -> None:
    settings = Settings(database_url="postgresql://u:p@localhost/ibex?sslmode=disable")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    assert factory is not None


class _BodyError(RuntimeError):
    """Stands in for a failure raised inside a scoped body."""


class _FakeTransaction:
    """Double for ``AsyncSession.begin()``: an async context manager.

    A real ``AsyncSessionTransaction`` commits on a clean exit and rolls back on
    an error. Only the exit reason is recorded here; ``_transaction`` also calls
    ``session.rollback()`` explicitly, and that call is what the rollback
    assertions watch.
    """

    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> None:
        self._session.events.append("begin")

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self._session.events.append("abort" if exc_type is not None else "commit")
        return False


class _FakeSession:
    """Async session double: records statements, params, and lifecycle events.

    ``fail_on`` fails the first statement whose text contains it, which is how
    the tests put a failure inside ``SET LOCAL ROLE`` or the org binding without
    inventing a database.
    """

    def __init__(self, *, fail_on: str | None = None, error: Exception | None = None) -> None:
        self.statements: list[str] = []
        self.params: list[Any] = []
        self.events: list[str] = []
        self._fail_on = fail_on
        self._error = error or SQLAlchemyError("simulated failure")

    async def __aenter__(self) -> Self:
        self.events.append("session_open")
        return self

    async def __aexit__(self, *exc: object) -> bool:
        self.events.append("session_close")
        return False

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    async def execute(self, statement: Any, params: Any = None) -> None:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params)
        self.events.append(f"execute: {sql}")
        if self._fail_on is not None and self._fail_on in sql:
            raise self._error

    async def rollback(self) -> None:
        self.events.append("rollback")


def _factory(session: _FakeSession) -> Callable[[], _FakeSession]:
    """Factory double: ``async_sessionmaker()`` returns the session CM."""
    return lambda: session


def _assert_rolled_back(session: _FakeSession) -> None:
    assert "rollback" in session.events, "the scope must roll back, not leave the txn open"
    assert "commit" not in session.events, "a failed scope must never commit"


# ---------------------------------------------------------------------------
# _pin_role: the allowlist is the only source of role SQL.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pin_role_rejects_a_role_outside_the_allowlist() -> None:
    session = _FakeSession()
    with pytest.raises(ValueError) as err:
        await _pin_role(session, "ibex_root")  # type: ignore[arg-type]
    message = str(err.value)
    # The message names what is allowed; it does not echo the rejected value, so
    # a future caller that forwards unvalidated input cannot reflect it here.
    assert "ibex_app" in message
    assert "ibex_purge" in message
    assert "ibex_root" not in message
    assert session.statements == []


@pytest.mark.asyncio
async def test_pin_role_never_interpolates_the_caller_string() -> None:
    session = _FakeSession()
    with pytest.raises(ValueError):
        await _pin_role(session, "ibex_app; SET ROLE ibex_purge")
    assert session.statements == []


@pytest.mark.asyncio
async def test_pin_role_issues_the_allowlisted_constant() -> None:
    session = _FakeSession()
    await _pin_role(session, "ibex_app")
    assert session.statements == ["SET LOCAL ROLE ibex_app"]
    assert session.params == [None]  # a role name cannot be a bind parameter


# ---------------------------------------------------------------------------
# _bind_org: the org id is a bound parameter.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bind_org_passes_the_org_id_as_a_bound_parameter() -> None:
    session = _FakeSession()
    await _bind_org(session, _ORG_ID)
    assert session.statements == [_ORG_GUC]
    assert ":org_id" in session.statements[0]
    assert _ORG_ID not in session.statements[0], "the org id must not be interpolated"
    assert session.params == [{"org_id": _ORG_ID}]

    hostile = "x'; SET ROLE ibex_purge; --"
    await _bind_org(session, hostile)
    assert hostile not in session.statements[1]
    assert session.params[1] == {"org_id": hostile}


# ---------------------------------------------------------------------------
# session_unpinned: no role statement at all.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_unpinned_issues_no_role_statement() -> None:
    session = _FakeSession()
    async with session_unpinned(_factory(session)) as scoped:
        assert scoped is session
        assert session.statements == [], "an unpinned scope must not assign a role"
    assert not any(sql.startswith("SET LOCAL ROLE") for sql in session.statements)
    assert not any("app.is_service_account" in sql for sql in session.statements)
    assert "commit" in session.events
    assert "rollback" not in session.events


@pytest.mark.asyncio
async def test_session_unpinned_rolls_back_when_the_body_raises() -> None:
    session = _FakeSession()
    with pytest.raises(_BodyError):
        async with session_unpinned(_factory(session)):
            raise _BodyError("body failed")
    _assert_rolled_back(session)
    assert session.events[-1] == "session_close"


# ---------------------------------------------------------------------------
# session_as_app: the identity pin with no tenant GUC.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_as_app_pins_the_role_without_an_org_guc() -> None:
    """A capability probe and the no-RLS dead-letter insert bind no tenant."""
    session = _FakeSession()
    async with session_as_app(_factory(session)) as scoped:
        assert scoped is session
        assert session.statements == ["SET LOCAL ROLE ibex_app"]
        assert session.params == [None]
        assert not any("app.current_org_id" in sql for sql in session.statements)
    assert "commit" in session.events
    assert "rollback" not in session.events


@pytest.mark.asyncio
async def test_session_as_app_rolls_back_when_the_body_raises() -> None:
    """A body error rolls the transaction back instead of committing the pin."""
    session = _FakeSession()
    scope = session_as_app(_factory(session))
    with pytest.raises(_BodyError):
        async with scope:
            raise _BodyError("body failed")
    _assert_rolled_back(session)
    assert session.events[-1] == "session_close"


# ---------------------------------------------------------------------------
# Scope factories: the pinned helpers the idempotency ledger is built with.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_org_scope_pins_app_and_binds_the_org() -> None:
    """The scope factory pins ``ibex_app`` and binds the org GUC."""
    session = _FakeSession()
    async with app_org_scope(_factory(session))(_ORG_ID) as scoped:
        assert scoped is session
        assert session.statements == ["SET LOCAL ROLE ibex_app", _ORG_GUC]
        assert session.params[1] == {"org_id": _ORG_ID}


@pytest.mark.asyncio
async def test_app_probe_scope_pins_app_without_an_org_guc() -> None:
    """The probe scope pins ``ibex_app`` and binds no org GUC."""
    session = _FakeSession()
    async with app_probe_scope(_factory(session))() as scoped:
        assert scoped is session
        assert session.statements == ["SET LOCAL ROLE ibex_app"]
        assert not any("set_config" in sql for sql in session.statements)


# ---------------------------------------------------------------------------
# Pinned scopes: pin the role, bind the org, roll back on any failure.
# ---------------------------------------------------------------------------

_PINNED_SCOPES = [
    pytest.param(session_as_app_org, "ibex_app", id="app"),
    pytest.param(session_as_purge_org, "ibex_purge", id="purge"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("scope", "role"), _PINNED_SCOPES)
async def test_pinned_scope_pins_the_role_then_binds_the_org(scope: Any, role: str) -> None:
    session = _FakeSession()
    async with scope(_factory(session), _ORG_ID) as scoped:
        assert scoped is session
        assert session.statements == [f"SET LOCAL ROLE {role}", _ORG_GUC]
        assert session.params[0] is None
        assert session.params[1] == {"org_id": _ORG_ID}
    assert "commit" in session.events
    assert "rollback" not in session.events


@pytest.mark.asyncio
@pytest.mark.parametrize(("scope", "role"), _PINNED_SCOPES)
async def test_pinned_scope_never_sets_the_service_account_bypass(scope: Any, role: str) -> None:
    del role
    session = _FakeSession()
    async with scope(_factory(session), _ORG_ID):
        pass
    assert all("app.is_service_account" not in sql for sql in session.statements)


@pytest.mark.asyncio
@pytest.mark.parametrize(("scope", "role"), _PINNED_SCOPES)
async def test_pinned_scope_rolls_back_when_the_role_switch_fails(scope: Any, role: str) -> None:
    session = _FakeSession(fail_on="SET LOCAL ROLE")
    with pytest.raises(SQLAlchemyError, match="simulated failure"):
        async with scope(_factory(session), _ORG_ID):
            pytest.fail("the body must not run after a failed pin")
    # The pin is what failed; the GUC is never bound under the login role.
    assert session.statements == [f"SET LOCAL ROLE {role}"]
    assert not any("set_config" in sql for sql in session.statements)
    _assert_rolled_back(session)


@pytest.mark.asyncio
@pytest.mark.parametrize(("scope", "role"), _PINNED_SCOPES)
async def test_pinned_scope_rolls_back_when_the_org_binding_fails(scope: Any, role: str) -> None:
    session = _FakeSession(fail_on="set_config")
    with pytest.raises(SQLAlchemyError, match="simulated failure"):
        async with scope(_factory(session), _ORG_ID):
            pytest.fail("the body must not run without an org binding")
    # The role was pinned; the binding is what failed.
    assert session.statements == [f"SET LOCAL ROLE {role}", _ORG_GUC]
    _assert_rolled_back(session)
    del role


@pytest.mark.asyncio
@pytest.mark.parametrize(("scope", "role"), _PINNED_SCOPES)
async def test_pinned_scope_rolls_back_when_the_body_raises(scope: Any, role: str) -> None:
    del role
    session = _FakeSession()
    with pytest.raises(_BodyError):
        async with scope(_factory(session), _ORG_ID):
            raise _BodyError("body failed")
    _assert_rolled_back(session)
    assert session.events[-1] == "session_close"
