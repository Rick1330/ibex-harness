"""Controlled embedding geometry for gold set v2.

The v1 gold set seeds every memory with a one-hot vector at a single "hotspot". Two
memories are therefore either identical (cosine 1.0) or orthogonal (cosine 0.0), and a
"near miss" cannot be expressed at all: every distractor is maximally far away. That makes
it impossible to write a query whose answer is *almost* found by dense retrieval, which is
exactly the case a hybrid or reranked pipeline is supposed to improve.

v2 seeds each memory with a weighted profile over named topics. Topic ``t`` maps to basis
vector ``e_t`` in a 1024-dimensional space, and a profile is ``v = Σ w_t · e_t`` with
``Σ w_t² = 1``. Because the bases are orthogonal:

    cos(v_a, v_b) = Σ_{t ∈ a ∩ b} w_a[t] · w_b[t]

so similarity is a designed quantity — 1.0 for the same profile, 0.0 for disjoint topics,
and a graded value in between. The validator asserts the intended margins instead of hoping
the float noise lands somewhere useful.

Topic assignment is explicit in the gold set (a ``topics`` map), not derived from iteration
order: a corpus whose meaning depends on dict ordering is not reproducible across Python
versions.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

EMBEDDING_DIM = 1024
# A profile with more than a handful of topics stops being interpretable, and the seeded
# vectors stop being sparse enough for the intent of a "topic cluster" to survive scoring.
MAX_TOPICS_PER_PROFILE = 4
MIN_PROFILE_NORM = 0.999
MAX_PROFILE_NORM = 1.001


class ProfileError(ValueError):
    """A profile that cannot be turned into a meaningful unit vector."""


def normalise_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Scale weights to unit L2 norm, rejecting anything that is not a usable profile."""
    _require_usable_profile(weights)
    clean = {topic: _validated_weight(topic, weight) for topic, weight in weights.items()}
    norm = math.sqrt(sum(value * value for value in clean.values()))
    _require_nonzero_norm(norm)
    return {topic: value / norm for topic, value in clean.items()}


def _require_usable_profile(weights: Mapping[str, float]) -> None:
    if not weights:
        raise ProfileError("embedding_profile must name at least one topic")
    if len(weights) > MAX_TOPICS_PER_PROFILE:
        raise ProfileError(
            f"embedding_profile has {len(weights)} topics, more than {MAX_TOPICS_PER_PROFILE}"
        )


def _require_nonzero_norm(norm: float) -> None:
    if norm <= 0.0:
        raise ProfileError("embedding_profile has zero norm")


def _validated_weight(topic: object, weight: object) -> float:
    _require_topic_name(topic)
    value = _as_number(topic, weight)
    _require_unit_range(topic, value, weight)
    return value


def _require_topic_name(topic: object) -> None:
    if not isinstance(topic, str) or not topic:
        raise ProfileError("embedding_profile topic names must be non-empty strings")


def _as_number(topic: object, weight: object) -> float:
    try:
        return float(weight)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        raise ProfileError(
            f"embedding_profile[{topic!r}] must be a number, got {weight!r}"
        ) from None


def _require_unit_range(topic: object, value: float, weight: object) -> None:
    if not math.isfinite(value):
        raise ProfileError(f"embedding_profile[{topic!r}] must be finite, got {weight!r}")
    if not 0.0 < value <= 1.0:
        raise ProfileError(f"embedding_profile[{topic!r}] must be in (0, 1], got {weight!r}")


def profile_cosine(
    left: Mapping[str, float],
    right: Mapping[str, float],
) -> float:
    """Cosine between two profiles, computed from the weights and the orthogonal bases."""
    left_unit = normalise_weights(left)
    right_unit = normalise_weights(right)
    shared = set(left_unit) & set(right_unit)
    return sum(left_unit[topic] * right_unit[topic] for topic in shared)


def profile_vector(
    weights: Mapping[str, float],
    topics: Mapping[str, int],
    *,
    dim: int = EMBEDDING_DIM,
) -> list[float]:
    """Build the dense vector a profile describes, ready for ``pgvector``.

    The vector is a linear combination of unit basis vectors, so a stored embedding has the
    same cosine against another profile as :func:`profile_cosine` reports. That equality is
    tested, because the whole corpus design rests on it.
    """
    unit = normalise_weights(weights)
    for topic in unit:
        _topic_base(topic, topics, dim)
    duplicates = duplicate_bases(topics)
    if duplicates:
        raise ProfileError(
            f"topic map reuses basis indices {duplicates}; profiles would merge clusters"
        )
    vector = [0.0] * dim
    for topic, weight in unit.items():
        base = _topic_base(topic, topics, dim)
        vector[base] += weight
    return vector


def _topic_base(topic: str, topics: Mapping[str, int], dim: int) -> int:
    if topic not in topics:
        raise ProfileError(f"topic {topic!r} is not declared in the gold set 'topics' map")
    base = topics[topic]
    if not isinstance(base, int) or isinstance(base, bool):
        raise ProfileError(f"topic {topic!r} base must be an integer, got {base!r}")
    if not 0 <= base < dim:
        raise ProfileError(f"topic {topic!r} base {base} is outside [0, {dim})")
    return base


def declared_bases(topics: Mapping[str, int]) -> list[int]:
    return [topics[topic] for topic in topics]


def duplicate_bases(topics: Mapping[str, int]) -> list[int]:
    """Bases used by more than one topic, which would silently merge two clusters."""
    seen: set[int] = set()
    duplicates: set[int] = set()
    for base in topics.values():
        if base in seen:
            duplicates.add(base)
        seen.add(base)
    return sorted(duplicates)


def validate_topics(topics: object, *, dim: int = EMBEDDING_DIM) -> list[str]:
    """Report every problem with the topic map, so one run lists them all."""
    if not isinstance(topics, Mapping) or not topics:
        return ["'topics' must be a non-empty object mapping topic name to basis index"]
    errors = [error for topic, base in topics.items() for error in _topic_errors(topic, base, dim)]
    duplicates = duplicate_bases({key: value for key, value in topics.items() if _is_index(value)})
    if duplicates:
        errors.append(f"basis indices reused by several topics: {duplicates}")
    return errors


def _topic_errors(topic: object, base: object, dim: int) -> list[str]:
    if not isinstance(topic, str) or not topic.strip():
        return [f"topic name {topic!r} must be a non-empty string"]
    if not _is_index(base):
        return [f"topic {topic!r} base must be an integer, got {base!r}"]
    return _range_errors(topic, base, dim)


def _range_errors(topic: str, base: int, dim: int) -> list[str]:
    if 0 <= base < dim:
        return []
    return [f"topic {topic!r} base {base} is outside [0, {dim})"]


def _is_index(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
