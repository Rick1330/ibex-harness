"""Celery task wiring for extract_session_memories."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.celery_app import celery_app
from app.extraction.batch import BatchJob
from app.extraction.provider import ExtractionTransportError
from app.task_names import TASK_EXTRACT_SESSION_MEMORIES
from app.tasks.extraction import extract_session_memories


def test_extract_task_routing_and_retry() -> None:
    task = celery_app.tasks[TASK_EXTRACT_SESSION_MEMORIES]
    assert task.queue == "extraction"
    assert task.soft_time_limit == 120
    assert task.time_limit == 180
    assert ExtractionTransportError in task.autoretry_for
    assert task.max_retries == 3


def _extract_kwargs(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "org_id": str(uuid4()),
        "agent_id": str(uuid4()),
        "session_id": str(uuid4()),
        "turns": [{"turn_index": 0, "role": "user", "content": "hello world xx"}],
    }
    payload.update(overrides)
    return payload


def _task_settings(
    *,
    token: SecretStr | None | str = "tok",
    db_url: str | None = None,
) -> type:
    token_value: SecretStr | None
    if token is None:
        token_value = None
    elif isinstance(token, SecretStr):
        token_value = token
    else:
        token_value = SecretStr(token)

    class _Settings:
        memory_base_url = "http://memory.example"
        memory_api_token = token_value
        database_url = db_url
        clickhouse_dsn = None

    return _Settings


@pytest.mark.parametrize(
    ("kwargs_mutator", "match"),
    [
        (lambda kw: kw.pop("org_id"), "org_id is required"),
        (lambda kw: kw.update({"agent_id": "not-a-uuid"}), "agent_id must be a UUID"),
        (lambda kw: kw.pop("agent_id"), "agent_id is required"),
    ],
)
def test_extract_task_rejects_bad_ids(kwargs_mutator, match: str) -> None:
    kwargs = _extract_kwargs()
    kwargs_mutator(kwargs)
    with pytest.raises(ValueError, match=match):
        extract_session_memories.run(**kwargs)


@pytest.mark.parametrize(
    ("token", "db_url", "match"),
    [
        ("   ", None, "memory_api_token is required"),
        ("tok", None, "database_url is required"),
        (None, None, "memory_base_url and memory_api_token"),
    ],
)
def test_extract_task_rejects_missing_config(
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
    db_url: str | None,
    match: str,
) -> None:
    monkeypatch.setattr(
        "app.tasks.extraction.get_settings",
        lambda: _task_settings(token=token, db_url=db_url)(),
    )
    with pytest.raises(ValueError, match=match):
        extract_session_memories.run(**_extract_kwargs())


def test_missing_database_url_still_closes_memory_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SessionStore setup failures must not leak the owned HttpMemoryWriter client."""
    closed = {"n": 0}

    class _Writer:
        def close(self) -> None:
            closed["n"] += 1

    monkeypatch.setattr(
        "app.tasks.extraction.get_settings",
        lambda: _task_settings(token="tok", db_url=None)(),
    )
    monkeypatch.setattr(
        "app.tasks.extraction.HttpMemoryWriter",
        lambda *_a, **_k: _Writer(),
    )
    with pytest.raises(ValueError, match="database_url is required"):
        extract_session_memories.run(**_extract_kwargs())
    assert closed["n"] == 1


def test_extract_task_runs_with_injected_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.extraction.batch import BatchRunResult

    closed = {"n": 0}

    class _Writer:
        def close(self) -> None:
            closed["n"] += 1

    class _Store:
        pass

    monkeypatch.setattr(
        "app.tasks.extraction.get_settings",
        lambda: _task_settings(db_url="postgresql+asyncpg://u:p@localhost/db")(),
    )
    monkeypatch.setattr("app.tasks.extraction.load_active_extraction_provider", lambda: object())
    monkeypatch.setattr(
        "app.tasks.extraction.HttpMemoryWriter",
        lambda *_a, **_k: _Writer(),
    )
    monkeypatch.setattr(
        "app.tasks.extraction._require_session_store",
        lambda _s: (_Store(), None),
    )
    monkeypatch.setattr(
        "app.tasks.extraction.run_batch_extraction",
        lambda _job: BatchRunResult(2, 1),
    )
    payload = extract_session_memories.run(
        org_id=str(uuid4()),
        agent_id=str(uuid4()),
        session_id=str(uuid4()),
        turns=[{"turn_index": 0, "role": "user", "content": "hello world xx"}],
    )
    assert payload == {
        "status": "ok",
        "memories_written": 2,
        "turns_processed": 1,
        "skipped": None,
    }
    assert closed["n"] == 1


def test_extract_task_closes_writer_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = {"n": 0}

    class _Writer:
        def close(self) -> None:
            closed["n"] += 1

    monkeypatch.setattr(
        "app.tasks.extraction.get_settings",
        lambda: _task_settings(db_url="postgresql+asyncpg://u:p@localhost/db")(),
    )
    monkeypatch.setattr("app.tasks.extraction.load_active_extraction_provider", lambda: object())
    monkeypatch.setattr(
        "app.tasks.extraction.HttpMemoryWriter",
        lambda *_a, **_k: _Writer(),
    )
    monkeypatch.setattr(
        "app.tasks.extraction._require_session_store",
        lambda _s: (object(), None),
    )
    monkeypatch.setattr(
        "app.tasks.extraction.run_batch_extraction",
        lambda _job: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(RuntimeError, match="boom"):
        extract_session_memories.run(**_extract_kwargs())
    assert closed["n"] == 1


def test_extract_task_requires_session_store_from_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.extraction.batch import BatchRunResult

    seen: dict[str, object] = {}
    disposed = {"n": 0}

    class _Writer:
        def close(self) -> None:
            return None

    class _Engine:
        async def dispose(self) -> None:
            disposed["n"] += 1

    class _Store:
        pass

    monkeypatch.setattr(
        "app.tasks.extraction.get_settings",
        lambda: _task_settings(db_url="postgresql+asyncpg://u:p@localhost/db")(),
    )
    monkeypatch.setattr("app.tasks.extraction.load_active_extraction_provider", lambda: object())
    monkeypatch.setattr(
        "app.tasks.extraction.HttpMemoryWriter",
        lambda *_a, **_k: _Writer(),
    )
    monkeypatch.setattr("app.tasks.extraction.create_engine", lambda _s: _Engine())
    monkeypatch.setattr(
        "app.tasks.extraction.create_session_factory",
        lambda _e: object(),
    )
    monkeypatch.setattr("app.tasks.extraction.PostgresSessionStore", lambda _f: _Store())

    def capture(job: BatchJob) -> BatchRunResult:
        seen["store"] = job.session_store
        return BatchRunResult(0, 0, skipped="no_unprocessed_turns")

    monkeypatch.setattr("app.tasks.extraction.run_batch_extraction", capture)
    payload = extract_session_memories.run(**_extract_kwargs())
    assert payload["status"] == "skipped"
    assert isinstance(seen["store"], _Store)
    assert disposed["n"] == 1
