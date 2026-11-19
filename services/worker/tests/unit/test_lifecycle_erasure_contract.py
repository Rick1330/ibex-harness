"""Contract tests: a declaration here must agree with the thing it mirrors.

Three facts are declared twice — once in this package and once outside it — and
each pair is a contract rather than a comment:

* the event filter in the ``SECURITY DEFINER`` claim function (migration 000074)
  must name exactly ``ERASURE_EVENT_TYPES``: a Python constant that lists fewer
  types than the function is a comment, and one that lists more is a lie;
* every store the consumer can prove has a stage, and no stage exists for a store
  nobody decided about, so ``_STAGE_BY_STORE`` and ``RECEIPT_STORES`` are pinned
  to each other;
* the forgotten-marker namespace and lifetime are duplicated from the memory
  service, which the worker cannot import, so the copies are pinned here.

The tests in ``..._sql.py`` guard the shape of the statements themselves; these
guard the agreement with what is outside the package.
"""

from __future__ import annotations

import ast
import operator
import pathlib
from collections.abc import Callable

from app.tasks import lifecycle_erasure as le
from app.tasks.lifecycle_erasure import ERASURE_EVENT_TYPES, RECEIPT_STORES

#: The migration that owns the claim function's event filter.
_CLAIM_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[4]
    / "infra/migrations/postgres/000074_memory_lifecycle_erasure_state.up.sql"
)

#: The memory service's key definitions, which the worker cannot import.
_MEMORY_KEYS = (
    pathlib.Path(__file__).resolve().parents[4]
    / "services/memory/app/cache/memory_keys.py"
)

#: The marker contract, as data: (worker constant, memory-service constant, the
#: relation that must hold between them). The namespace must be the one the
#: memory service writes, or the guard covers a key nobody checks; the lifetime
#: must be the same, or one service's marker expires under the other's. A row
#: can pin an ordering (``operator.ge``) if a future marker ever needs to
#: outlive — rather than equal — its counterpart, without changing the loop.
_FORGOTTEN_MARKER_CONTRACT: tuple[
    tuple[str, str, Callable[[object, object], bool]], ...
] = (
    ("_CACHE_FORGOTTEN_NAMESPACE", "MEMORY_FORGOTTEN_NAMESPACE", operator.eq),
    ("_CACHE_FORGOTTEN_TTL_SECONDS", "MEMORY_FORGOTTEN_TTL_SECONDS", operator.eq),
)


def test_claim_function_names_exactly_the_erasure_event_types() -> None:
    """The migration's SQL literal set and the Python constant must not drift.

    The event filter lives in the ``SECURITY DEFINER`` claim function, so the
    file is the contract: a Python constant that lists fewer types than the
    function is a comment, and one that lists more is a lie.
    """
    sql = " ".join(_CLAIM_MIGRATION.read_text(encoding="utf-8").split())
    for event_type in ERASURE_EVENT_TYPES:
        assert f"'{event_type}'" in sql, event_type
    for excluded in ("'created'", "'content_updated'", "'superseded'", "'quarantined'"):
        assert excluded not in sql, excluded


def test_stage_table_covers_every_receipt_store() -> None:
    """Every store this consumer can prove has a stage, and every stage is known.

    ``_STAGE_BY_STORE`` is a superset of ``RECEIPT_STORES`` because a ref can name
    a store outside the provable set (ClickHouse) and it must still be erased;
    the key set is pinned so a new stage cannot appear without a decision here.
    """
    assert set(RECEIPT_STORES) <= set(le._STAGE_BY_STORE)
    assert set(le._STAGE_BY_STORE) == {
        "objectstore",
        "clickhouse",
        "session_event",
        "cache",
        "cache_hot",
    }


def test_cache_guard_constants_match_the_memory_service() -> None:
    """The two services must agree on the marker, or the guard protects nothing.

    The worker cannot import ``app.cache.memory_keys`` (a different deployment),
    so the namespace and the marker lifetime are duplicated deliberately and this
    contract test is what keeps the copies equal.
    """
    memory_service = _module_literals(_MEMORY_KEYS)
    for worker_name, memory_name, holds in _FORGOTTEN_MARKER_CONTRACT:
        assert holds(getattr(le, worker_name), memory_service[memory_name]), worker_name


def _module_literals(path: pathlib.Path) -> dict[str, object]:
    """The module-level ``NAME = <literal>`` assignments of a Python file."""
    values: dict[str, object] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        values[target.id] = _literal(node.value)
    return values


def _literal(node: ast.AST) -> object:
    """Fold a constant or a ``*`` of constants; refuse any other node type."""
    if isinstance(node, ast.Constant):
        return node.value
    if not isinstance(node, ast.BinOp):
        raise TypeError("not a literal")
    if not isinstance(node.op, ast.Mult):
        raise TypeError("not a literal")
    return _literal(node.left) * _literal(node.right)  # type: ignore[operator]
