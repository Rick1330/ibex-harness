"""Unit tests for unresolved-conflict suppression (milestone 5.B.2)."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from app.read.conflicts import (
    collapse_conflict_pairs,
    conflict_groups_from_row,
    record_suppressed,
)
from app.read.metrics import CONFLICT_SUPPRESSED
from tests.unit.find_similar_support import make_result


def _grouped(memory_id: UUID, *groups: UUID):
    return replace(make_result(memory_id), conflict_groups=groups)


def test_hits_without_groups_are_all_kept() -> None:
    hits = [_grouped(uuid4()) for _ in range(3)]

    assert collapse_conflict_pairs(hits) == hits


def test_a_shared_group_keeps_only_the_first_hit() -> None:
    group = uuid4()
    high, low = _grouped(uuid4(), group), _grouped(uuid4(), group)

    kept = collapse_conflict_pairs([high, low])

    assert kept == [high]


def test_disjoint_groups_are_both_kept() -> None:
    first, second = _grouped(uuid4(), uuid4()), _grouped(uuid4(), uuid4())

    assert collapse_conflict_pairs([first, second]) == [first, second]


def test_a_dropped_hit_does_not_poison_later_groups() -> None:
    # A{1}, B{1,2}, C{2}: B dies against A, so C is free to survive -- the
    # returned page still contains no conflicting pair.
    one, two = uuid4(), uuid4()
    a, b, c = _grouped(uuid4(), one), _grouped(uuid4(), one, two), _grouped(uuid4(), two)

    kept = collapse_conflict_pairs([a, b, c])

    assert kept == [a, c]


def test_three_way_conflict_keeps_only_the_top_hit() -> None:
    group = uuid4()
    hits = [_grouped(uuid4(), group) for _ in range(3)]

    kept = collapse_conflict_pairs(hits)

    assert kept == [hits[0]]


def test_conflict_groups_from_row_parses_uuids() -> None:
    group = uuid4()
    assert conflict_groups_from_row({"conflict_groups": [str(group)]}) == (group,)


def test_conflict_groups_from_row_tolerates_missing_and_null() -> None:
    assert conflict_groups_from_row({}) == ()
    assert conflict_groups_from_row({"conflict_groups": None}) == ()


@pytest.mark.parametrize("count", [0, 1, 5])
def test_collapse_is_a_no_op_on_conflict_free_pages(count: int) -> None:
    hits = [make_result(uuid4()) for _ in range(count)]

    assert collapse_conflict_pairs(hits) == hits


def test_record_suppressed_counts_only_the_reported_drops() -> None:
    before = CONFLICT_SUPPRESSED._value.get()

    record_suppressed(5, 3)

    assert CONFLICT_SUPPRESSED._value.get() == before + 2


def test_record_suppressed_ignores_a_list_that_kept_everything() -> None:
    before = CONFLICT_SUPPRESSED._value.get()

    record_suppressed(3, 3)

    assert CONFLICT_SUPPRESSED._value.get() == before
