"""The forget response must tell the caller whether erasure actually happened.

Why this file exists: ``POST /v1/memories/{id}/forget`` returned the new revision
and ``tombstoned: true`` and nothing else, so a caller could not tell a memory
that was erased everywhere from one whose object-store archive, ClickHouse
evidence and ``session_events`` row still existed. The response now carries
``erasure: {state, stores}``, computed from the receipts the consumer wrote and
the outbox row the forget wrote.

Two properties are asserted here, and the second matters as much as the first:

* the erasure block is **additive** — ``data`` keeps exactly the fields it had;
* the erasure block never over-claims. A fresh forget reports ``pending``, and
  ``complete`` appears only when every store's receipt says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.routers.memories import ForgetMemoryContext, forget_memory
from app.routers.memory_forget_support import read_forget_erasure
from app.schemas.memories import ForgetMemoryRequest
from tests.integration import lifecycle_erasure_support
from tests.integration.conftest import seed_org_agent_memory

pytestmark = pytest.mark.integration

_execute_sql = lifecycle_erasure_support.execute_sql


@dataclass(frozen=True, slots=True)
class _Revision:
    """The ``(org, memory, revision)`` a receipt and an outbox row are keyed by."""

    org_id: UUID
    memory_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class _ErasureCase:
    """One set of receipts and the outbox state the forget response must mirror."""

    receipts: dict[str, str]
    outbox_state: str
    expected_state: str
    expected_stores: dict[str, str]


async def _forget(
    factory: async_sessionmaker[AsyncSession], *, org_id: UUID, agent_id: UUID, memory_id: UUID
):
    """Invoke the real handler with an authenticated, server-derived scope."""
    ctx = ForgetMemoryContext(
        token=SimpleNamespace(org_id=org_id, agent_id=agent_id),
        session_factory=factory,
        cache_writer=None,
    )
    return await forget_memory(memory_id, ForgetMemoryRequest(expected_revision=1), ctx)


def _revision_params(revision: _Revision) -> dict[str, object]:
    """The three key columns every receipt and outbox statement binds."""
    return {
        "org": revision.org_id,
        "memory": revision.memory_id,
        "revision": revision.revision,
    }


async def _seed_receipts(
    factory: async_sessionmaker[AsyncSession],
    revision: _Revision,
    statuses: dict[str, str],
) -> None:
    """Write the receipts a consumer run would have written, as the tenant."""
    for store, status in statuses.items():
        await _execute_sql(
            factory,
            revision.org_id,
            """
            INSERT INTO ibex_core.erasure_store_receipts
                (org_id, memory_id, revision, store, status, verified_absent_at,
                 idempotency_key)
            VALUES (:org, :memory, :revision, :store, :status,
                    CASE WHEN :status = 'verified' THEN NOW() ELSE NULL END,
                    :key)
            ON CONFLICT (org_id, memory_id, revision, store) DO UPDATE
               SET status = EXCLUDED.status,
                   verified_absent_at = EXCLUDED.verified_absent_at
            """,
            {
                **_revision_params(revision),
                "store": store,
                "status": status,
                "key": f"erase:{revision.org_id}:{revision.memory_id}:"
                f"{revision.revision}:{store}",
            },
        )


async def _set_outbox_state(
    factory: async_sessionmaker[AsyncSession],
    revision: _Revision,
    state: str,
) -> None:
    """Move the outbox row a forget wrote to the state a consumer would leave."""
    await _execute_sql(
        factory,
        revision.org_id,
        """
        UPDATE ibex_core.memory_lifecycle_outbox
           SET erasure_state = :state,
               delivered_at = CASE WHEN :state = 'complete' THEN NOW() ELSE NULL END
         WHERE org_id = :org AND memory_id = :memory AND revision = :revision
        """,
        {**_revision_params(revision), "state": state},
    )


async def test_forget_response_is_additive_and_reports_pending_erasure(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A fresh forget returns the same ``data`` and an honest ``pending``."""
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="forget response fixture"
    )

    response = await _forget(
        session_factory, org_id=org_id, agent_id=agent_id, memory_id=memory_id
    )

    assert response.data.memory_id == memory_id
    assert response.data.revision == 2
    assert response.data.tombstoned is True
    assert response.erasure.state == "pending"
    assert response.erasure.stores.objectstore == "pending"
    assert response.erasure.stores.session_event == "pending"
    assert response.erasure.stores.cache == "pending"
    assert response.erasure.stores.cache_hot == "pending"

    # The wire shape: the old keys are untouched and the new block is a sibling.
    body = response.model_dump(mode="json")
    assert set(body) == {"data", "erasure"}
    assert body["data"] == {
        "memory_id": str(memory_id),
        "revision": 2,
        "tombstoned": True,
    }
    # ClickHouse is not in the map: the consumer cannot prove that store, so the
    # response makes no claim about it rather than a false ``not_applicable``.
    assert body["erasure"]["stores"] == {
        "objectstore": "pending",
        "session_event": "pending",
        "cache": "pending",
        "cache_hot": "pending",
    }


#: The three store maps the response cases exercise: everything proven, a store
#: with nothing to erase, and a store that could not be reached.
_ALL_VERIFIED = {
    "objectstore": "verified",
    "session_event": "verified",
    "cache": "verified",
    "cache_hot": "verified",
}
_NOT_APPLICABLE = {
    "objectstore": "verified",
    "session_event": "not_applicable",
    "cache": "not_applicable",
    "cache_hot": "not_applicable",
}
_ONE_FAILED = {
    "objectstore": "verified",
    "session_event": "failed",
    "cache": "verified",
    "cache_hot": "verified",
}


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            _ErasureCase(
                receipts=_ALL_VERIFIED,
                outbox_state="complete",
                expected_state="complete",
                expected_stores=_ALL_VERIFIED,
            ),
            id="all-verified",
        ),
        pytest.param(
            _ErasureCase(
                receipts=_NOT_APPLICABLE,
                outbox_state="complete",
                expected_state="complete",
                expected_stores=_NOT_APPLICABLE,
            ),
            id="not-applicable-counts",
        ),
        pytest.param(
            _ErasureCase(
                receipts=_ONE_FAILED,
                outbox_state="partial",
                expected_state="partial",
                expected_stores=_ONE_FAILED,
            ),
            id="partial",
        ),
        pytest.param(
            _ErasureCase(
                receipts=_ONE_FAILED,
                outbox_state="failed",
                expected_state="failed",
                expected_stores=_ONE_FAILED,
            ),
            id="terminal-failed",
        ),
    ],
)
async def test_erasure_view_reports_the_receipts_without_over_claiming(
    session_factory: async_sessionmaker[AsyncSession],
    case: _ErasureCase,
) -> None:
    """The response mirrors the proof: nothing is promoted to ``verified``."""
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content=f"erasure view {case.outbox_state}"
    )
    response = await _forget(
        session_factory, org_id=org_id, agent_id=agent_id, memory_id=memory_id
    )
    revision = _Revision(
        org_id=org_id, memory_id=memory_id, revision=response.data.revision
    )
    await _seed_receipts(session_factory, revision, case.receipts)
    await _set_outbox_state(session_factory, revision, case.outbox_state)

    erasure = await read_forget_erasure(
        session_factory,
        org_id=org_id,
        memory_id=memory_id,
        revision=revision.revision,
    )

    assert erasure.state == case.expected_state
    assert erasure.stores.model_dump() == case.expected_stores


async def test_erasure_view_never_reports_another_tenants_receipts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Receipts are tenant-scoped: org B's proof must not colour org A's answer."""
    org_a, agent_a, memory_a = await seed_org_agent_memory(
        session_factory, content="tenant scoping fixture A"
    )
    org_b, _agent_b, memory_b = await seed_org_agent_memory(
        session_factory, content="tenant scoping fixture B"
    )
    response = await _forget(
        session_factory, org_id=org_a, agent_id=agent_a, memory_id=memory_a
    )
    other = _Revision(
        org_id=org_b, memory_id=memory_b, revision=response.data.revision
    )
    await _seed_receipts(
        session_factory,
        other,
        {"objectstore": "verified", "session_event": "verified"},
    )
    await _set_outbox_state(session_factory, other, "complete")

    erasure = await read_forget_erasure(
        session_factory, org_id=org_a, memory_id=memory_a, revision=other.revision
    )

    assert erasure.state == "pending"
    assert erasure.stores.model_dump() == {
        "objectstore": "pending",
        "session_event": "pending",
        "cache": "pending",
        "cache_hot": "pending",
    }


async def test_erasure_view_degrades_to_pending_when_the_read_fails(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A committed forget must not become a 503 because the proof is unreadable.

    The caller would retry a tombstoned memory and get 409; "no proof recorded
    yet" is the honest, actionable answer instead.
    """
    org_id, _agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="degraded read fixture"
    )

    class _Broken:
        def __call__(self):
            raise SQLAlchemyError("pool exhausted")

    erasure = await read_forget_erasure(
        _Broken(), org_id=org_id, memory_id=memory_id, revision=2
    )

    assert erasure.state == "pending"
    assert erasure.stores.objectstore == "pending"


async def test_erasure_view_without_a_revision_is_pending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An unknown revision has no proof, and is not reported as complete."""
    org_id, _agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content="unknown revision fixture"
    )
    erasure = await read_forget_erasure(
        session_factory, org_id=org_id, memory_id=memory_id, revision=99
    )
    assert erasure.state == "pending"


async def test_forget_for_an_unknown_memory_still_404s(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The additive field must not change the existing error contract."""
    org_id, agent_id, _memory_id = await seed_org_agent_memory(
        session_factory, content="unknown memory fixture"
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as missing:
        await _forget(
            session_factory, org_id=org_id, agent_id=agent_id, memory_id=uuid4()
        )
    assert missing.value.status_code == 404
