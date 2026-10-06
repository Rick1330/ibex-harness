"""Contract tests for read-path lifecycle predicates."""

from app.read.full_text import FTS_SQL
from app.read.hot_cache import _HYDRATE_HOT_SQL
from app.read.repository import _HYDRATE_SQL
from app.vectorstore.pgvector_store import SEARCH_SQL

_EXPECTED_PREDICATES = (
    "valid_from <= CURRENT_TIMESTAMP",
    "(valid_until IS NULL OR valid_until > CURRENT_TIMESTAMP)",
)

_SEARCH_PREDICATES = (
    "(:include_expired OR valid_from <= CURRENT_TIMESTAMP)",
    "(:include_expired OR valid_until IS NULL OR valid_until > CURRENT_TIMESTAMP)",
)


def test_all_authoritative_read_paths_enforce_half_open_validity() -> None:
    for sql in (SEARCH_SQL, FTS_SQL, _HYDRATE_SQL, _HYDRATE_HOT_SQL):
        assert any(
            predicate in sql
            for predicate in (
                _EXPECTED_PREDICATES[0],
                "m.valid_from <= CURRENT_TIMESTAMP",
                _SEARCH_PREDICATES[0],
            )
        )
        assert any(
            predicate in sql
            for predicate in (
                _EXPECTED_PREDICATES[1],
                "(m.valid_until IS NULL OR m.valid_until > CURRENT_TIMESTAMP)",
                _SEARCH_PREDICATES[1],
            )
        )


def test_all_authoritative_read_paths_keep_active_and_tombstone_guards() -> None:
    for sql in (SEARCH_SQL, FTS_SQL, _HYDRATE_SQL, _HYDRATE_HOT_SQL):
        assert "status = 'active'" in sql or "m.status = 'active'" in sql
        assert "deleted_at IS NULL" in sql or "m.deleted_at IS NULL" in sql
