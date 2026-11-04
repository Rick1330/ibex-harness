"""The suppression kill switch (ADR-0094): off means both sides of a conflict survive."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.read.models import MemorySearchResult
from app.read.repository import MemoryReadRepository


def _repository(*, enabled: bool) -> MemoryReadRepository:
    # Only the settings drive _collapse; the collaborators are unused on that path.
    return MemoryReadRepository(
        session_factory=object(),  # type: ignore[arg-type]
        vector_store=object(),  # type: ignore[arg-type]
        settings=Settings(conflict_suppression_enabled=enabled),
    )


def _hit(content: str, groups: tuple[UUID, ...]) -> MemorySearchResult:
    now = datetime.now(tz=UTC)
    return MemorySearchResult(
        id=uuid4(),
        org_id=uuid4(),
        agent_id=uuid4(),
        content=content,
        category="factual",
        confidence=0.9,
        status="active",
        similarity=0.9,
        source="vector",
        created_at=now,
        updated_at=now,
        conflict_groups=groups,
    )


class TestSuppressionSwitch:
    def test_on_by_default(self) -> None:
        assert Settings().conflict_suppression_enabled is True

    def test_enabled_collapses_a_pending_conflict(self) -> None:
        group = uuid4()
        results = [_hit("first", (group,)), _hit("second", (group,))]

        kept = _repository(enabled=True)._collapse(results)

        assert len(kept) == 1
        assert kept[0].content == "first"

    def test_disabled_keeps_both_sides(self) -> None:
        group = uuid4()
        results = [_hit("first", (group,)), _hit("second", (group,))]

        kept = _repository(enabled=False)._collapse(results)

        assert [hit.content for hit in kept] == ["first", "second"]

    def test_disabled_still_returns_a_new_list(self) -> None:
        # Callers slice and append to the result; handing back the input list would let a
        # downstream mutation rewrite the caller's page.
        results = [_hit("only", ())]

        kept = _repository(enabled=False)._collapse(results)

        assert kept == results
        assert kept is not results

    def test_disabled_does_not_touch_unconflicted_rows(self) -> None:
        results = [_hit("a", ()), _hit("b", ())]

        assert len(_repository(enabled=False)._collapse(results)) == 2

    def test_the_switch_is_exported_in_settings(self) -> None:
        # The benchmark's full_graph mode reads this field by name; a rename would silently
        # disable the mode instead of failing.
        assert "conflict_suppression_enabled" in Settings.model_fields


class TestHotCacheSwitch:
    def test_hot_path_honours_the_switch(self) -> None:
        # /hot had its own unconditional collapse; the switch is only honest if every read
        # path that suppresses obeys it.
        from app.read.hot_cache import MemoryHotCacheReader

        group = uuid4()
        results = [_hit("first", (group,)), _hit("second", (group,))]

        assert len(MemoryHotCacheReader._collapse(results, True)) == 1
        assert len(MemoryHotCacheReader._collapse(results, False)) == 2

    def test_hot_query_defaults_to_suppressing(self) -> None:
        from app.read.models import HotMemoryQuery

        query = HotMemoryQuery(org_id=uuid4(), agent_id=uuid4())

        assert query.suppress_conflicts is True


class TestHotContextSettings:
    def test_hot_context_reads_the_app_settings_not_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both routes must honour `create_app(settings=...)`."""
        from starlette.requests import Request

        from app.deps import get_hot_memory_context

        app_settings = Settings(conflict_suppression_enabled=False)

        class _State:
            settings = app_settings

        class _App:
            state = _State()

        request = Request({"type": "http", "app": _App(), "headers": []})
        monkeypatch.setenv("IBEX_MEMORY_CONFLICT_SUPPRESSION_ENABLED", "true")

        context = get_hot_memory_context(request, object(), object(), object())  # type: ignore[arg-type]

        assert context.settings is app_settings
        assert context.settings.conflict_suppression_enabled is False
