"""Which Redis failures a retry can fix, defined once for the cache paths.

The write path and the forget path both need the same answer: an expired
password, a missing permission, or a wrong-type reply is a property of the
deployment or the command, and retrying it only delays the honest failure. A
timeout, a dropped connection, or a cluster state that says "try again" is an
outage the next attempt can fix.

This module is deliberately free of ``app`` imports. The worker cannot import
the memory service (separate deployment unit, and both services use ``app`` as
their top-level package), so the worker mirrors this rule and
``services/worker/tests/unit/test_lifecycle_erasure_redis_failures.py`` loads
this file by path and executes both implementations against every exception
class ``redis.exceptions`` defines. That contract test is what keeps the mirror
from drifting; the file having no ``app`` dependency is what lets it run.
"""

from __future__ import annotations

from redis.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BusyLoadingError,
    ClusterDownError,
    DataError,
    MasterDownError,
    TryAgainError,
)
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

#: Failures a later attempt can fix. A timeout or a dropped connection is the
#: outage a retry is for; ``AuthenticationError`` and ``AuthorizationError``
#: subclass ``ConnectionError``, so the non-retryable tuple is checked first.
_RETRYABLE_REDIS_FAILURES = (
    RedisTimeoutError,
    RedisConnectionError,
    BusyLoadingError,
    TryAgainError,
    MasterDownError,
    ClusterDownError,
)

#: Failures that are a property of the deployment or the command, not an outage:
#: an expired password, a missing permission, and a wrong-type reply cannot
#: succeed on the next attempt no matter how long the caller waits. ``DataError``
#: is a client-side refusal for the same reason.
_NON_RETRYABLE_REDIS_FAILURES = (
    AuthenticationError,
    AuthorizationError,
    DataError,
)


def is_retryable_redis_failure(exc: BaseException) -> bool:
    """Whether a failed Redis command is worth retrying.

    Only a timeout, a connection failure, or a cluster state that says "try
    again" is. A wrong-type or authentication error is recorded immediately with
    its reason: retrying it delays the honest ``failed`` state and cannot change
    the outcome.

    The retryable tuple names the transient ``ResponseError`` subclasses
    (``TryAgainError``, ``MasterDownError``) explicitly. A generic
    ``ResponseError`` — a wrong-type reply, a missing permission — is in neither
    tuple and is therefore not retryable.
    """
    if isinstance(exc, _NON_RETRYABLE_REDIS_FAILURES):
        return False
    return isinstance(exc, (OSError, *_RETRYABLE_REDIS_FAILURES))
