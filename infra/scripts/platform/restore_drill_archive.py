"""The WAL archive model: what the queue state and segment arithmetic say.

The RPO a report carries is the frontier the restore demonstrated, not a
property of the archive queue: the restore replays every segment from the
backup to the replay point, so a gap either stops recovery or truncates the
replay timestamp. What lives here is the diagnostic arithmetic — how many
segment files one WAL log id holds (which depends on the cluster's
``wal_segment_size``), and how many segments sit between the newest archived one
and the one being written — so an operator reading a miss has the queue state
beside the number.

The functions take what the producer measured and return ``True``, ``False`` or
``None``. ``None`` means "cannot tell" and must never be read as "no backlog":
the caller is a report that refuses to claim more than the run proved.

No producer measures the ``pg_wal`` older-segment count: PostgreSQL retains
already-archived segments there until recycling, so a positive count of segments
older than ``last_archived_wal`` does not mean they are pending archival, and a
healthy run reported a backlog until those files were recycled. Every report
therefore records ``wal_archive_backlog: null``, and the arithmetic below is the
specification of the input a correct measurement would have to supply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# A WAL segment file name is 24 hex digits: timeline, log, segment.
_WAL_SEGMENT_RE = re.compile(r"^[0-9A-Fa-f]{24}$")
# One WAL log id covers 2**32 bytes of the stream. How many segment files that
# is depends on the cluster's wal_segment_size: 4096 for 1 MiB, 256 for 16 MiB,
# 64 for 64 MiB. A fixed 256 is only right for the default, and it turns a real
# multi-segment backlog into a negative gap (or an empty one into a backlog) on
# any other segment size, so the multiplier is derived from what was measured.
_WAL_LOG_BYTES = 2**32


def _wal_segment_position(name: str | None) -> tuple[int, int, int] | None:
    """Split a WAL segment file name into (timeline, log, segment)."""
    value = (name or "").strip()
    if not _WAL_SEGMENT_RE.match(value):
        return None
    return (int(value[0:8], 16), int(value[8:16], 16), int(value[16:24], 16))


def is_count(value: Any) -> bool:
    """Is this a non-negative integer the producer could have measured?"""
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value >= 0


def segments_per_log(wal_segment_size: int | None) -> int | None:
    """Segment files per WAL log id, from the cluster's own segment size.

    ``None`` means the multiplier cannot be derived: the size was not measured,
    is not a divisor of 2**32, or is not a positive integer. The caller must
    treat that as unproven rather than falling back to 256.
    """
    if not is_count(wal_segment_size) or wal_segment_size == 0:
        return None
    if _WAL_LOG_BYTES % wal_segment_size:
        return None
    return _WAL_LOG_BYTES // wal_segment_size


@dataclass(frozen=True)
class ArchiveContinuity:
    """What the cluster's own pg_wal directory adds to segment adjacency.

    Adjacency alone is not continuity: PostgreSQL does not promise archival
    order, and ``last_archived_wal`` does not prove older segments were archived.
    After crash recovery the newest archived segment can sit next to the current
    one while an older required segment is still missing. A segment older than
    ``last_archived_wal`` that is still present in ``pg_wal`` is the strongest
    local signal that the queue has not drained.

    The count is taken across timelines, so segments left behind by a promotion
    keep the queue "not provably drained" until recycling removes them. That
    withholds the RPO claim rather than overstating it, which is the right
    direction: an old timeline's WAL is part of the recoverable history.

    Neither producer supplies this count (see the module docstring), so a report
    built from a producer's environment records ``wal_archive_backlog: null``.
    """

    wal_segment_size: int | None
    older_segments_present: int | None


def _archive_state_proven(
    last: tuple[int, int, int] | None,
    current: tuple[int, int, int] | None,
    last_failed_after_archive: bool | None,
) -> bool:
    """Every input the queue state is read from has to be readable.

    A segment name that does not parse, or a failed-push flag the producer never
    recorded, leaves the queue state unknown. That is not "no backlog": it is
    "cannot tell", and the caller must not turn it into a bound.
    """
    if last is None:
        return False
    if current is None:
        return False
    return last_failed_after_archive is not None


def _segments_behind(
    last: tuple[int, int, int],
    current: tuple[int, int, int],
    continuity: ArchiveContinuity,
) -> int | None:
    """How many segments the writer is ahead of the newest archived one.

    ``None`` when the answer cannot be derived from what was measured: an
    unknown segment size leaves the log multiplier unknown, an unmeasured
    ``pg_wal`` listing leaves continuity unknown, and two timelines cannot be
    compared at all (a promotion is exactly when the archive can lag).
    """
    per_log = segments_per_log(continuity.wal_segment_size)
    if per_log is None:
        return None
    if not is_count(continuity.older_segments_present):
        return None
    if last[0] != current[0]:
        return None
    gap = (current[1] - last[1]) * per_log + (current[2] - last[2])
    return gap if gap >= 0 else None


def wal_archive_backlog(
    *,
    last_archived_wal: str | None,
    current_wal: str | None,
    last_failed_after_archive: bool | None,
    continuity: ArchiveContinuity,
) -> bool | None:
    """Is the WAL archive queue provably drained?

    ``last_archived_time`` records when an upload *completed*, not the
    transaction time the segment it carried covers. While a backlog drains, an
    old segment uploads now and its age looks like a fresh recovery point, so the
    upload age can understate the real lag by the whole length of the backlog.
    That is why the age is a diagnostic and never the RPO: the bound comes from
    the frontier the restore demonstrated.

    The queue state is a diagnostic beside that number, and adjacency is not
    enough to establish it: archival order is not guaranteed, so the newest
    archived segment can be adjacent to the current one while an older required
    segment is still missing. The queue is drained only when the writer is at
    most one segment ahead, no older segment is still sitting in ``pg_wal``, and
    no push has failed since the last success.

    ``False`` therefore means "positively confirmed drained". ``True`` means a
    backlog was observed. ``None`` means "cannot tell", and must never be read as
    "no backlog".
    """
    last = _wal_segment_position(last_archived_wal)
    current = _wal_segment_position(current_wal)
    if not _archive_state_proven(last, current, last_failed_after_archive):
        return None
    gap = _segments_behind(last, current, continuity)
    if gap is None:
        return None
    if gap > 1:
        return True
    if continuity.older_segments_present > 0:
        return True
    return bool(last_failed_after_archive)


