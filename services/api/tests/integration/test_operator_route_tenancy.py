"""HTTP-level tenant isolation for the operator read routes (P0-21 / W8.4).

Every assertion here goes through ``TestClient`` → router → dependency → SQL, so
it proves the router wiring, the HTTP status, the error envelope, and the
cookie-to-org binding that the service-level RLS suites cannot see. The
``test_operator_*_rls.py`` suites already prove the SQL filters and the RLS GUC;
this file does not repeat them.

These tests prove end-to-end isolation over HTTP, but they cannot tell the
explicit ``org_id`` filter apart from RLS: QA demonstrated a mutant with the
filter removed still passed here until RLS was disabled.
``test_operator_*_rls.py`` is the suite that pins the SQL layer.

Excluded surface and why:

- ``GET /v1/operator/events/stream`` is a long-lived SSE stream. A ``TestClient``
  call would block on the response body instead of returning a status and
  envelope, and the stream takes no tenant selector to assert against.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from tests.integration.conftest import TwoTenantOperator

pytestmark = pytest.mark.integration

_INSERT_AGENT = (
    "INSERT INTO ibex_core.agents (id, org_id, name, slug, status) "
    "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), :name, :slug, 'active')"
)

_INSERT_USER = (
    "INSERT INTO ibex_core.users (id, org_id, email, name, role, status) "
    "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), :email, :name, 'member', 'active')"
)

_INSERT_MEMORY = (
    "INSERT INTO ibex_core.memories ("
    "  id, org_id, agent_id, content, content_hash, content_tokens,"
    "  category, status, confidence, usefulness_score, source,"
    "  retrieval_count, pii_detected, pii_redacted, metadata, tombstoned,"
    "  valid_from, observed_at, created_at, updated_at"
    ") VALUES ("
    "  CAST(:id AS uuid), CAST(:org_id AS uuid), CAST(:agent_id AS uuid),"
    "  :content, :content_hash, 7, 'factual', 'active', 0.80, 0.50,"
    "  'extracted', 2, FALSE, FALSE, CAST(:metadata AS jsonb), :tombstoned,"
    "  :created_at, :created_at, :created_at, :created_at"
    ")"
)

_INSERT_SESSION = (
    "INSERT INTO ibex_core.sessions ("
    "  id, org_id, agent_id, external_id, status, model, provider,"
    "  turn_count, total_input_tokens, total_output_tokens, total_latency_ms,"
    "  last_extracted_turn, created_at, updated_at"
    ") VALUES ("
    "  CAST(:id AS uuid), CAST(:org_id AS uuid), CAST(:agent_id AS uuid),"
    "  :external_id, 'active', 'gpt-4.1', 'openai',"
    "  2, 100, 50, 1200, 1, :created_at, :created_at"
    ")"
)

_INSERT_DIRECTIVE = (
    "INSERT INTO ibex_core.directives (id, org_id, agent_id, injection_mode, is_active) "
    "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), CAST(:agent_id AS uuid), "
    "'system_first', TRUE)"
)

_INSERT_EVIDENCE_RUN = (
    "INSERT INTO ibex_core.evidence_runs ("
    "  id, org_id, request_id, trace_id, schema_version, completeness,"
    "  status, capture_mode, sample_decision, started_at, ended_at"
    ") VALUES ("
    "  CAST(:id AS uuid), CAST(:org_id AS uuid), :request_id, :trace_id,"
    "  'evidence.v1', 'complete', 'ok', 'metadata', 'sampled',"
    "  :started_at, :started_at"
    ")"
)

_INSERT_OUTBOX = (
    "INSERT INTO ibex_core.evidence_outbox ("
    "  org_id, event_id, aggregate_id, aggregate_seq, schema_version,"
    "  event_type, payload, payload_digest, delivery_status, created_at"
    ") VALUES ("
    "  CAST(:org_id AS uuid), CAST(:event_id AS uuid), :aggregate_id, :seq,"
    "  'evidence.v1', 'memory.written', '{}'::jsonb, :digest, 'pending', :created_at"
    ")"
)

_INSERT_LIFECYCLE_EVENT = (
    "INSERT INTO ibex_core.memory_lifecycle_outbox ("
    "  org_id, memory_id, revision, event_type, occurred_at, delivered_at"
    ") VALUES ("
    "  CAST(:org_id AS uuid), CAST(:memory_id AS uuid), :revision,"
    "  :event_type, :occurred_at, NULL"
    ")"
)

_INSERT_DELETION_JOB = (
    "INSERT INTO ibex_core.org_deletion_jobs ("
    "  id, org_id, status, created_at, finished_at"
    ") VALUES ("
    "  CAST(:id AS uuid), CAST(:org_id AS uuid), :status, :created_at, :finished_at"
    ")"
)

_INSERT_DELETION_RECEIPT = (
    "INSERT INTO ibex_core.deletion_store_receipts ("
    "  job_id, store, status, verified_absent_at, idempotency_key"
    ") VALUES ("
    "  CAST(:job_id AS uuid), :store, :status, :verified_absent_at, :idempotency_key"
    ")"
)

_MEMORY_METADATA = '{"visibility":"agent","pinned":false,"tags":["support"]}'


@dataclass(frozen=True)
class _TenantRows:
    """One fully populated read-model row set for a single organization."""

    agent: UUID
    memory: UUID
    session: UUID
    directive: UUID
    evidence_run: UUID
    trace_id: str
    request_id: str


@dataclass(frozen=True)
class _DeletionRows:
    """The deletion-evidence rows seeded for one organization."""

    memories: tuple[UUID, ...]
    job: UUID | None


@dataclass(frozen=True)
class _SeedContext:
    """Shared inputs for the per-table seed helpers of one organization."""

    tenancy: TwoTenantOperator
    org_id: UUID
    created_at: datetime
    label: str


@dataclass(frozen=True)
class _DeletionSpec:
    """The deletion-evidence shape one organization should carry."""

    events: tuple[str, ...]
    tombstoned_memories: int
    job_status: str | None = None


@dataclass(frozen=True)
class _MemorySeed:
    """The per-row memory values that differ between a live row and a tombstone."""

    content: str
    tombstoned: bool


def _seed_context(tenancy: TwoTenantOperator, org_id: UUID, label: str) -> _SeedContext:
    return _SeedContext(
        tenancy=tenancy,
        org_id=org_id,
        created_at=datetime.now(UTC) - timedelta(minutes=5),
        label=label,
    )


def _get_json(
    client: TestClient,
    path: str,
    params: dict[str, str] | None = None,
) -> dict[str, object]:
    response = client.get(path, params=params)
    assert response.status_code == 200, (path, response.text)
    return response.json()


def _trace_window() -> dict[str, str]:
    now = datetime.now(UTC)
    return {
        "started_after": (now - timedelta(hours=1)).isoformat(),
        "started_before": (now + timedelta(minutes=1)).isoformat(),
    }


def _agent_statement(
    ctx: _SeedContext, agent: UUID, *, name: str, slug: str
) -> tuple[str, dict[str, object]]:
    return (
        _INSERT_AGENT,
        {"id": str(agent), "org_id": str(ctx.org_id), "name": name, "slug": slug},
    )


def _memory_statement(
    ctx: _SeedContext, memory: UUID, agent: UUID, seed: _MemorySeed
) -> tuple[str, dict[str, object]]:
    return (
        _INSERT_MEMORY,
        {
            "id": str(memory),
            "org_id": str(ctx.org_id),
            "agent_id": str(agent),
            "content": seed.content,
            "content_hash": f"hash-{memory.hex}",
            "metadata": _MEMORY_METADATA,
            "tombstoned": seed.tombstoned,
            "created_at": ctx.created_at,
        },
    )


def _session_statement(
    ctx: _SeedContext, session: UUID, agent: UUID
) -> tuple[str, dict[str, object]]:
    return (
        _INSERT_SESSION,
        {
            "id": str(session),
            "org_id": str(ctx.org_id),
            "agent_id": str(agent),
            "external_id": f"ext-{session.hex}",
            "created_at": ctx.created_at,
        },
    )


def _directive_statement(
    ctx: _SeedContext, directive: UUID, agent: UUID
) -> tuple[str, dict[str, object]]:
    return (
        _INSERT_DIRECTIVE,
        {"id": str(directive), "org_id": str(ctx.org_id), "agent_id": str(agent)},
    )


def _evidence_run_statement(ctx: _SeedContext, rows: _TenantRows) -> tuple[str, dict[str, object]]:
    return (
        _INSERT_EVIDENCE_RUN,
        {
            "id": str(rows.evidence_run),
            "org_id": str(ctx.org_id),
            "request_id": rows.request_id,
            "trace_id": rows.trace_id,
            "started_at": ctx.created_at,
        },
    )


def _outbox_statement(
    ctx: _SeedContext, rows: _TenantRows, seq: int
) -> tuple[str, dict[str, object]]:
    return (
        _INSERT_OUTBOX,
        {
            "org_id": str(ctx.org_id),
            "event_id": str(uuid4()),
            "aggregate_id": rows.request_id,
            "seq": seq,
            "digest": f"digest-{rows.request_id}",
            "created_at": ctx.created_at,
        },
    )


def _lifecycle_statement(
    ctx: _SeedContext, memory: UUID, event: str
) -> tuple[str, dict[str, object]]:
    return (
        _INSERT_LIFECYCLE_EVENT,
        {
            "org_id": str(ctx.org_id),
            "memory_id": str(memory),
            "revision": 1,
            "event_type": event,
            "occurred_at": ctx.created_at,
        },
    )


def _job_statements(
    ctx: _SeedContext, job: UUID, status: str | None
) -> list[tuple[str, dict[str, object]]]:
    return [
        (
            _INSERT_DELETION_JOB,
            {
                "id": str(job),
                "org_id": str(ctx.org_id),
                "status": status,
                "created_at": ctx.created_at,
                "finished_at": ctx.created_at,
            },
        ),
        (
            _INSERT_DELETION_RECEIPT,
            {
                "job_id": str(job),
                "store": "postgres",
                "status": "verified",
                "verified_absent_at": ctx.created_at,
                "idempotency_key": f"receipt-{job.hex}",
            },
        ),
    ]


async def _seed_tenant_rows(
    tenancy: TwoTenantOperator,
    org_id: UUID,
    *,
    label: str,
    outbox_seq: int = 3,
) -> _TenantRows:
    ctx = _seed_context(tenancy, org_id, label)
    rows = _TenantRows(
        agent=uuid4(),
        memory=uuid4(),
        session=uuid4(),
        directive=uuid4(),
        evidence_run=uuid4(),
        trace_id=f"trace-{label}-{uuid4().hex}",
        request_id=f"req-{label}-{uuid4().hex}",
    )
    await tenancy.seed(
        [
            _agent_statement(
                ctx,
                rows.agent,
                name=f"{label} agent",
                slug=f"{label}-agent-{rows.agent.hex[:8]}",
            ),
            _memory_statement(
                ctx,
                rows.memory,
                rows.agent,
                _MemorySeed(content=f"{label} memory content", tombstoned=False),
            ),
            _session_statement(ctx, rows.session, rows.agent),
            _directive_statement(ctx, rows.directive, rows.agent),
            _evidence_run_statement(ctx, rows),
            _outbox_statement(ctx, rows, outbox_seq),
        ]
    )
    return rows


async def _seed_deletion_rows(ctx: _SeedContext, spec: _DeletionSpec) -> _DeletionRows:
    """Seed tombstones, lifecycle events, and an optional erasure job + receipt."""
    agent = uuid4()
    memories = tuple(uuid4() for _ in range(max(spec.tombstoned_memories, len(spec.events))))
    job = uuid4() if spec.job_status is not None else None
    statements = [
        _agent_statement(
            ctx,
            agent,
            name=f"deletion agent {agent.hex[:8]}",
            slug=f"deletion-agent-{agent.hex[:8]}",
        ),
        *(
            _memory_statement(
                ctx,
                memory,
                agent,
                _MemorySeed(content=f"tombstoned memory {memory.hex[:8]}", tombstoned=True),
            )
            for memory in memories
        ),
        *(
            _lifecycle_statement(ctx, memory, event)
            for event, memory in zip(spec.events, memories[: len(spec.events)], strict=True)
        ),
    ]
    if job is not None:
        statements.extend(_job_statements(ctx, job, spec.job_status))
    await ctx.tenancy.seed(statements)
    return _DeletionRows(memories=memories, job=job)


def test_each_operator_client_is_bound_to_its_cookie_org(
    two_tenant_operator: TwoTenantOperator,
) -> None:
    """After login each client's cookie resolves to the org its PAT was exchanged for."""
    tenancy = two_tenant_operator
    me_a = tenancy.client_a.get("/v1/operator/session/me")
    me_b = tenancy.client_b.get("/v1/operator/session/me")
    assert me_a.status_code == 200, me_a.text
    assert me_b.status_code == 200, me_b.text
    assert me_a.json()["org_id"] == str(tenancy.org_a)
    assert me_b.json()["org_id"] == str(tenancy.org_b)


def test_session_me_prefers_the_cookie_over_a_foreign_bearer(
    two_tenant_operator: TwoTenantOperator,
) -> None:
    """The documented precedence is cookie present → cookie, bearer only as fallback.

    Client A's validator knows only org A's PAT, so a route that consulted the
    bearer first would answer 401 here instead of org A: the two outcomes cannot
    be confused. The control below clears the cookie so the same PAT is proven
    live (it selects org B when nothing overrides it).
    """
    tenancy = two_tenant_operator
    with_bearer = tenancy.client_a.get(
        "/v1/operator/session/me",
        headers={"Authorization": f"Bearer {tenancy.pat_b}"},
    )
    assert with_bearer.status_code == 200, with_bearer.text
    body = with_bearer.json()
    assert body["auth"] == "cookie"
    assert body["org_id"] == str(tenancy.org_a)

    # Positive control: the same foreign PAT with no cookie does select its org.
    tenancy.client_b.cookies.clear()
    bearer_only = tenancy.client_b.get(
        "/v1/operator/session/me",
        headers={"Authorization": f"Bearer {tenancy.pat_b}"},
    )
    assert bearer_only.status_code == 200, bearer_only.text
    assert bearer_only.json() == {
        "auth": "bearer",
        "org_id": str(tenancy.org_b),
        "provisional": False,
    }


@pytest.mark.asyncio
async def test_foreign_tenant_detail_reads_return_not_found(
    two_tenant_operator: TwoTenantOperator,
) -> None:
    """Foreign entity ids 404 with the envelope, never 403 or a leaked name."""
    tenancy = two_tenant_operator
    foreign = await _seed_tenant_rows(tenancy, tenancy.org_b, label="bravo")
    paths = (
        (f"/v1/operator/agents/{foreign.agent}", foreign.agent),
        (f"/v1/operator/memories/{foreign.memory}", foreign.memory),
        (f"/v1/operator/sessions/{foreign.session}", foreign.session),
    )
    for path, foreign_id in paths:
        # Positive control: the row exists and its own tenant can read it.
        owned = tenancy.client_b.get(path)
        assert owned.status_code == 200, (path, owned.text)
        assert owned.json()["id"] == str(foreign_id)
        denied = tenancy.client_a.get(path)
        assert denied.status_code == 404, (path, denied.text)
        assert denied.json()["error"]["code"] == "NOT_FOUND", (path, denied.text)
        assert str(foreign_id) not in denied.text, path
        assert tenancy.org_b_name not in denied.text, path


@pytest.mark.asyncio
async def test_foreign_tenant_directive_and_trace_reads_return_not_found(
    two_tenant_operator: TwoTenantOperator,
) -> None:
    """Directive detail and both trace-id reads 404 for a foreign tenant."""
    tenancy = two_tenant_operator
    foreign = await _seed_tenant_rows(tenancy, tenancy.org_b, label="bravo")
    directive_path = f"/v1/operator/directives/{foreign.directive}"
    runs_path = f"/v1/operator/traces/{foreign.trace_id}"
    detail_path = f"/v1/operator/traces/runs/{foreign.evidence_run}"

    # Positive controls: each shape resolves for its own tenant first.
    owned_directive = tenancy.client_b.get(directive_path)
    assert owned_directive.status_code == 200, owned_directive.text
    assert owned_directive.json()["id"] == str(foreign.directive)
    assert owned_directive.json()["agent_id"] == str(foreign.agent)
    owned_runs = tenancy.client_b.get(runs_path)
    assert owned_runs.status_code == 200, owned_runs.text
    assert [item["run_id"] for item in owned_runs.json()["items"]] == [str(foreign.evidence_run)]
    owned_detail = tenancy.client_b.get(detail_path)
    assert owned_detail.status_code == 200, owned_detail.text
    assert owned_detail.json()["run_id"] == str(foreign.evidence_run)

    negatives = (
        (directive_path, str(foreign.directive)),
        (runs_path, foreign.trace_id),
        (detail_path, str(foreign.evidence_run)),
    )
    for path, foreign_marker in negatives:
        denied = tenancy.client_a.get(path)
        assert denied.status_code == 404, (path, denied.text)
        assert denied.json()["error"]["code"] == "NOT_FOUND", (path, denied.text)
        assert foreign_marker not in denied.text, path
        assert foreign.request_id not in denied.text, path
        assert tenancy.org_b_name not in denied.text, path
        assert tenancy.org_b_slug not in denied.text, path


@pytest.mark.asyncio
async def test_collection_reads_return_only_the_callers_rows(
    two_tenant_operator: TwoTenantOperator,
) -> None:
    """Each collection returns the caller's rows and none of the other org's."""
    tenancy = two_tenant_operator
    own = await _seed_tenant_rows(tenancy, tenancy.org_a, label="alpha")
    foreign = await _seed_tenant_rows(tenancy, tenancy.org_b, label="bravo")
    cases = (
        ("/v1/operator/agents", own.agent, foreign.agent),
        ("/v1/operator/memories", own.memory, foreign.memory),
        ("/v1/operator/sessions", own.session, foreign.session),
        ("/v1/operator/directives", own.directive, foreign.directive),
    )
    for path, own_id, foreign_id in cases:
        # Positive control: org B sees its own row, so the endpoint is live.
        foreign_body = _get_json(tenancy.client_b, path)
        assert [row["id"] for row in foreign_body["data"]] == [str(foreign_id)], path
        response = tenancy.client_a.get(path)
        assert response.status_code == 200, (path, response.text)
        body = response.json()
        assert [row["id"] for row in body["data"]] == [str(own_id)], path
        assert str(foreign_id) not in response.text, path


@pytest.mark.asyncio
async def test_trace_list_excludes_foreign_tenant_runs(
    two_tenant_operator: TwoTenantOperator,
) -> None:
    """Trace reads are scoped: org A has no runs, org B's run never appears."""
    tenancy = two_tenant_operator
    foreign = await _seed_tenant_rows(tenancy, tenancy.org_b, label="bravo")
    window = _trace_window()
    foreign_body = _get_json(tenancy.client_b, "/v1/operator/traces", params=window)
    assert [item["run_id"] for item in foreign_body["items"]] == [str(foreign.evidence_run)]
    response = tenancy.client_a.get("/v1/operator/traces", params=window)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["returned_count"] == 0
    assert body["matched_count"] == 0
    assert foreign.trace_id not in response.text
    assert foreign.request_id not in response.text


@pytest.mark.asyncio
async def test_evidence_summary_excludes_foreign_tenant_runs(
    two_tenant_operator: TwoTenantOperator,
) -> None:
    """The evidence aggregate counts only the caller's runs and outbox rows."""
    tenancy = two_tenant_operator
    foreign = await _seed_tenant_rows(tenancy, tenancy.org_b, label="bravo")
    foreign_body = _get_json(
        tenancy.client_b, "/v1/operator/evidence/summary", params={"range": "24h"}
    )
    assert foreign_body["runs_total"] == 1
    assert foreign_body["delivery"]["pending"] == 1
    response = tenancy.client_a.get("/v1/operator/evidence/summary", params={"range": "24h"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["runs_total"] == 0
    assert body["completeness"]["complete"] == 0
    assert body["delivery"]["pending"] == 0
    assert foreign.request_id not in response.text
    assert foreign.trace_id not in response.text


@pytest.mark.asyncio
async def test_evidence_deletions_count_only_the_callers_tombstones(
    two_tenant_operator: TwoTenantOperator,
) -> None:
    """Deletion evidence scopes tombstones, the tombstone fence, and erasure jobs."""
    tenancy = two_tenant_operator
    own = await _seed_deletion_rows(
        _seed_context(tenancy, tenancy.org_a, "deletion-alpha"),
        _DeletionSpec(events=("forgotten",), tombstoned_memories=1),
    )
    foreign = await _seed_deletion_rows(
        _seed_context(tenancy, tenancy.org_b, "deletion-bravo"),
        _DeletionSpec(
            events=("purged", "purged", "expired"),
            tombstoned_memories=2,
            job_status="succeeded",
        ),
    )
    assert foreign.job is not None

    # Positive control: org B sees its own events, fence, job, and receipt.
    foreign_body = _get_json(tenancy.client_b, "/v1/operator/evidence/deletions")
    assert foreign_body["tombstones"]["events"] == {
        "forgotten": 0,
        "expired": 1,
        "purged": 2,
    }
    assert foreign_body["tombstones"]["pending"] == 3
    assert foreign_body["tombstones"]["tombstoned_memories"] == len(foreign.memories)
    assert foreign_body["erasures"]["succeeded"] == 1
    assert [job["id"] for job in foreign_body["jobs"]] == [str(foreign.job)]
    receipts = foreign_body["jobs"][0]["receipts"]
    assert [(receipt["store"], receipt["status"]) for receipt in receipts] == [
        ("postgres", "verified")
    ]
    assert receipts[0]["verified_absent_at"] is not None

    response = tenancy.client_a.get("/v1/operator/evidence/deletions")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tombstones"]["events"] == {"forgotten": 1, "expired": 0, "purged": 0}
    assert body["tombstones"]["pending"] == 1
    assert body["tombstones"]["tombstoned_memories"] == len(own.memories)
    assert body["erasures"] == {
        "pending": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "hold_blocked": 0,
    }
    assert body["jobs"] == []
    assert body["jobs_truncated"] is False
    assert body["audit"]["entries"] == 0
    assert str(foreign.job) not in response.text
    for memory in foreign.memories:
        assert str(memory) not in response.text


@pytest.mark.asyncio
async def test_overview_and_context_are_tenant_bound(
    two_tenant_operator: TwoTenantOperator,
) -> None:
    """Overview/context read the cookie's org row and its own counts only."""
    tenancy = two_tenant_operator
    await _seed_tenant_rows(tenancy, tenancy.org_a, label="alpha")
    await _seed_tenant_rows(tenancy, tenancy.org_b, label="bravo")
    # Org B carries extra live rows; none of them may reach org A's counts.
    extra_agents = [uuid4(), uuid4()]
    extra_user = uuid4()
    await tenancy.seed(
        [
            (
                _INSERT_AGENT,
                {
                    "id": str(agent_id),
                    "org_id": str(tenancy.org_b),
                    "name": f"bravo extra {index}",
                    "slug": f"bravo-extra-{index}-{agent_id.hex[:8]}",
                },
            )
            for index, agent_id in enumerate(extra_agents)
        ]
        + [
            (
                _INSERT_USER,
                {
                    "id": str(extra_user),
                    "org_id": str(tenancy.org_b),
                    "email": f"bravo-extra-{extra_user.hex[:8]}@example.test",
                    "name": "Bravo extra user",
                },
            )
        ]
    )
    overview_response = tenancy.client_a.get("/v1/operator/overview")
    context_response = tenancy.client_a.get("/v1/operator/context")
    assert overview_response.status_code == 200, overview_response.text
    assert context_response.status_code == 200, context_response.text
    overview = overview_response.json()
    context = context_response.json()
    assert overview["org_id"] == str(tenancy.org_a)
    assert overview["org_name"] == tenancy.org_a_name
    assert overview["org_slug"] == tenancy.org_a_slug
    assert overview["counts"] == {
        "active_users": 1,
        "agents": 1,
        "active_agents": 1,
    }
    assert context["org_id"] == str(tenancy.org_a)
    assert context["org_name"] == tenancy.org_a_name
    assert context["role"] == "owner"
    for response in (overview_response, context_response):
        assert tenancy.org_b_name not in response.text
        assert tenancy.org_b_slug not in response.text


@pytest.mark.asyncio
async def test_platform_health_outbox_watermark_is_tenant_scoped(
    two_tenant_operator: TwoTenantOperator,
) -> None:
    """Platform health has no tenant selector; its watermark must still be scoped."""
    tenancy = two_tenant_operator
    await _seed_tenant_rows(tenancy, tenancy.org_b, label="bravo", outbox_seq=7)
    body = _get_json(tenancy.client_a, "/v1/operator/platform/health")
    watermark = body["outbox_max_aggregate_seq"]
    # Org A has no outbox rows: the route reports 0 (or null), never B's sequence.
    assert watermark in (None, 0), body
    assert watermark != 7, body
    foreign_body = _get_json(tenancy.client_b, "/v1/operator/platform/health")
    assert foreign_body["outbox_max_aggregate_seq"] == 7
