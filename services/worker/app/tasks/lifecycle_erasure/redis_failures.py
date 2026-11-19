"""Which Redis failures the erasure worker must not retry.

The memory service owns this distinction (``services/memory/app/cache/
redis_failures.py``): an expired password, a missing permission, or a wrong-type
reply is a property of the deployment or the command, and retrying it to the
erasure deadline only delays the honest ``failed`` state. A timeout, a dropped
connection, or a cluster state that says "try again" is an outage the next
attempt can fix.

Why this is a mirror rather than an import: the two services are separate
deployment units and neither image ships the other's code, while both use
``app`` as their top-level package name, so a cross-service import cannot
resolve. ``test_lifecycle_erasure_redis_failures.py`` loads the memory module by
file path and executes both implementations against every exception class
``redis.exceptions`` defines; the declared tuples are compared too, so a change
on either side fails that contract test.

The rule is scoped to ``RedisError`` on purpose. ``_stage_store`` calls this for
every store, and a ClickHouse or object-store outage is not a Redis refusal: it
must stay retryable, which is what the ``RedisError`` guard preserves.
"""

from __future__ import annotations

from redis import exceptions as redis_errors

#: Refusals a retry cannot change. Authentication and authorization errors
#: subclass ``ConnectionError``, so they are checked before the outage tuple.
_REFUSALS = (
    redis_errors.AuthenticationError,
    redis_errors.AuthorizationError,
    redis_errors.DataError,
)

#: Outages a later attempt can fix. The transient ``ResponseError`` subclasses
#: are named explicitly; a generic ``ResponseError`` is a refusal.
_OUTAGES = (
    redis_errors.TimeoutError,
    redis_errors.ConnectionError,
    redis_errors.BusyLoadingError,
    redis_errors.TryAgainError,
    redis_errors.MasterDownError,
    redis_errors.ClusterDownError,
)


def is_permanent_redis_failure(exc: BaseException) -> bool:
    """Whether a Redis failure cannot succeed on a retry.

    True for a refusal (authentication, permission, wrong-type reply); False for
    an outage, and False for any exception that is not a Redis error at all, so
    the caller's other failure classes keep their existing classification.
    """
    if not isinstance(exc, redis_errors.RedisError):
        return False
    if isinstance(exc, _REFUSALS):
        return True
    return not isinstance(exc, (OSError, *_OUTAGES))
