"""Constants, budgets and store vocabulary of the memory-erasure consumer.

``RECEIPT_STORES`` is the set of stores whose absence this consumer can *prove*,
because a producer records a ref for every copy. ClickHouse is deliberately not
in it: no producer writes a per-memory ClickHouse locator (the evidence relay
projects session resources only), so an absent ClickHouse ref cannot be read as
"this memory has no ClickHouse copy". A ref that does name ClickHouse is still
erased and receipted; a memory with no such ref simply makes no ClickHouse claim,
instead of the false ``not_applicable`` a missing ref used to produce.

The two cache stores are the disclosure fix. ``cache`` is the object entry that
carries the memory's ``content``; ``cache_hot`` is the per-agent hot sorted set,
whose member is removed with ZREM rather than the key with DEL — the key holds
every other memory's score for that agent. A cache locator is caller-written
text, so each stage refuses a key outside its own ``<org>:{namespace}:`` before
deleting anything, and an unreachable or unconfigured Redis is ``failed``, never
``verified``.
"""

from __future__ import annotations

#: Outbox event types that end a memory. The claim function repeats this set in
#: SQL; ``test_lifecycle_erasure_contract`` fails if the two ever disagree.
ERASURE_EVENT_TYPES: tuple[str, ...] = ("forgotten", "purged", "expired")

RECEIPT_STORES: tuple[str, ...] = ("objectstore", "session_event", "cache", "cache_hot")

#: The two Redis structures, in the vocabulary the database contract uses.
CACHE_STORES: tuple[str, ...] = ("cache", "cache_hot")

#: Receipt statuses that prove a store without further work.
SATISFIED_RECEIPT_STATUSES = frozenset({"verified", "not_applicable"})

#: Rows claimed per sweep run. One at a time keeps the lease and the per-row
#: deadline accounting honest; the beat supplies the throughput.
_CLAIM_BATCH = 1

_RETRY_BASE_SECONDS = 30
_RETRY_CAP_SECONDS = 3600
#: Fraction of the capped delay that is randomized either way. Bounded so a
#: retry stays inside ``_RETRY_CAP_SECONDS`` while two erasures hitting the same
#: outage do not wake at the same instant.
_RETRY_JITTER_FRACTION = 0.25
_ERROR_MAX_CHARS = 300

#: Headroom over the configured job budget for writing receipts and settling
#: the outbox row after the last store stage, plus a further grace before the
#: process is killed. The Celery soft limit must be strictly larger than the
#: budget the sweep enforces, or a legal configuration is killed mid-settle.
_ERASURE_SETTLEMENT_HEADROOM_SECONDS = 60.0
_ERASURE_KILL_GRACE_SECONDS = 60.0

#: Redis namespace each cache store may address. The namespace check is the
#: tenant guard *and* the blast-radius guard: a ref is caller-written text, so a
#: locator naming ``{org}:directive:...`` must be refused rather than deleted.
#: Checking the namespace rather than an exact key keeps the worker independent
#: of the memory service's key format while still refusing every key that is not
#: one of this store's own structures.
_CACHE_NAMESPACES = {"cache": "memory", "cache_hot": "hot_memories"}

#: The marker the memory service writes before it deletes the object cache entry
#: (``app.cache.memory_keys.MEMORY_FORGOTTEN_NAMESPACE``). The worker writes the
#: same marker *before* its own delete, so a delayed after-commit create cannot
#: recreate what this stage just proved absent. It is not a store and carries no
#: content: the object entry is what the receipt is about.
_CACHE_FORGOTTEN_NAMESPACE = "memory_forgotten"

#: Marker lifetime. It must match ``MEMORY_FORGOTTEN_TTL_SECONDS`` in
#: ``services/memory/app/cache/memory_keys.py``; the two services cannot import
#: each other, and ``test_lifecycle_erasure_contract`` pins the values together.
#: A week outlives any write that was already in flight; the marker holds only an
#: id and expires, so the set stays bounded and content-free.
_CACHE_FORGOTTEN_TTL_SECONDS = 7 * 24 * 60 * 60


def _task_limits(job_timeout_seconds: float) -> tuple[int, int]:
    """Celery (soft, hard) limits for one erasure job budget.

    Derived rather than fixed: ``lifecycle_erasure_job_timeout_seconds`` is
    configurable up to 3600 s, so a fixed 900 s soft limit killed a legal 1800 s
    job before its own deadline. Settlement (receipts and the outbox update)
    runs after the last store stage, so the soft limit carries headroom for it
    and the hard limit adds a further grace before the process is killed.
    """
    soft = int(job_timeout_seconds + _ERASURE_SETTLEMENT_HEADROOM_SECONDS)
    return soft, soft + int(_ERASURE_KILL_GRACE_SECONDS)
