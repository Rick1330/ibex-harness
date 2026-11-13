"""Unit tests for content-hash keys and org-scoped Redis key format.

The digest is a cache contract, not an implementation detail: the pinned values below
are the bytes a deployment already has in Redis, so any change to them silently
invalidates (or worse, mis-serves) every cached vector. The revision tests cover the
one optional field added on top of that layout.
"""

from __future__ import annotations

import hashlib
import struct
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.cache.keys import (
    EmbeddingIdentity,
    cache_key_for_text,
    content_digest,
    redis_key,
)
from app.config import MAX_MODEL_REVISION_LEN, Settings
from app.limits import MAX_MODEL_ID_LEN

_ORG_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

# Digest of (model_id="m", dimensions=8, text="hello") with no revision field, which
# is what the cache has stored since G4.M4. Do not change without a key-version bump.
_PINNED_NO_REVISION = "4664cd09297dee102954e605cfe50be4e4cabd069191d4294caa8d768dbb8542"
# Realistic shape: the pinned v1-single-node embedding model.
_PINNED_BGE_M3_EMPTY_TEXT = "6d063e6ea8f9c1d069e8b2ae281e8ea7df5d6e65a63212c7cad22bb1d5a0be3a"


def _identity(
    model_id: str = "m",
    dimensions: int = 8,
    revision: str | None = None,
) -> EmbeddingIdentity:
    return EmbeddingIdentity(
        model_id=model_id,
        dimensions=dimensions,
        model_revision=revision,
    )


def _digest(
    text: str,
    *,
    model_id: str = "m",
    dimensions: int = 8,
    revision: str | None = None,
) -> str:
    return content_digest(
        identity=_identity(model_id, dimensions, revision),
        text=text,
    )


def _pre_revision_digest(*, model_id: str, dimensions: int, text: str) -> str:
    """Independent reimplementation of the documented pre-revision layout."""
    model_bytes = model_id.encode("utf-8")
    text_bytes = text.encode("utf-8")
    payload = (
        struct.pack(">I", len(model_bytes))
        + model_bytes
        + struct.pack(">I", dimensions)
        + struct.pack(">I", len(text_bytes))
        + text_bytes
    )
    return hashlib.sha256(payload).hexdigest()


class TestContentDigest:
    def test_stable_for_same_inputs(self) -> None:
        a = _digest("hello")
        b = _digest("hello")
        assert a == b
        assert len(a) == 64

    def test_model_id_changes_digest(self) -> None:
        a = _digest("hello", model_id="m1")
        b = _digest("hello", model_id="m2")
        assert a != b

    def test_dimensions_changes_digest_matryoshka(self) -> None:
        a = _digest("hello", dimensions=256)
        b = _digest("hello", dimensions=3072)
        assert a != b

    def test_text_changes_digest(self) -> None:
        a = _digest("hello")
        b = _digest("Hello")
        assert a != b

    def test_pipe_in_model_id_not_ambiguous(self) -> None:
        """Length-prefixing avoids delimiter collisions with model ids containing |."""
        left = _digest("x", model_id="org|model")
        # Different encoding of ambiguous concatenation must not collide.
        right = _digest("modelx", model_id="org")
        assert left != right

    def test_exact_utf8_no_normalization(self) -> None:
        # Combining vs precomposed would differ if we NFC'd; we must not.
        a = _digest("café")
        b = _digest("cafe\u0301")
        assert a != b


class TestDigestWithoutRevision:
    """No revision configured must reproduce today's bytes exactly."""

    def test_pinned_pre_revision_bytes(self) -> None:
        digest = _digest("hello")
        assert digest == _PINNED_NO_REVISION
        assert digest == _pre_revision_digest(model_id="m", dimensions=8, text="hello")

    def test_pinned_realistic_model_bytes(self) -> None:
        digest = _digest("", model_id="BAAI/bge-m3", dimensions=1024)
        assert digest == _PINNED_BGE_M3_EMPTY_TEXT

    def test_explicit_none_is_the_unset_layout(self) -> None:
        assert _digest("hello", revision=None) == _digest("hello")


class TestDigestWithRevision:
    """A revision is part of vector identity: other weights must never share entries."""

    def test_revision_a_differs_from_revision_b(self) -> None:
        a = _digest("hello", revision="rev-a")
        b = _digest("hello", revision="rev-b")
        assert a != b

    def test_revision_differs_from_unset(self) -> None:
        assert _digest("hello", revision="rev-a") != _PINNED_NO_REVISION

    def test_empty_revision_is_not_a_revision(self) -> None:
        """``""`` means "not distinguished" (the memory-service convention) — same bytes."""
        assert _digest("hello", revision="") == _PINNED_NO_REVISION

    def test_revision_is_length_prefixed(self) -> None:
        """('rev', 'ab') and ('reva', 'b') must not collide with text or model id."""
        left = _digest("c", revision="ab")
        right = _digest("bc", revision="a")
        assert left != right

    def test_revision_cannot_be_moved_into_the_model_id(self) -> None:
        split = _digest("x", revision="rev")
        joined = _digest("x", model_id="mrev")
        assert split != joined


class TestRedisKey:
    def test_org_prefix_and_version(self) -> None:
        digest = "a" * 64
        key = redis_key(org_id=_ORG_A, digest_hex=digest)
        assert key == f"{_ORG_A}:embed:v1:{digest}"

    def test_cross_tenant_keys_differ(self) -> None:
        ka = cache_key_for_text(org_id=_ORG_A, identity=_identity(), text="same")
        kb = cache_key_for_text(org_id=_ORG_B, identity=_identity(), text="same")
        assert ka != kb
        assert ka.startswith(f"{_ORG_A}:")
        assert kb.startswith(f"{_ORG_B}:")

    def test_cross_tenant_keys_differ_under_one_revision(self) -> None:
        identity = _identity(revision="rev")
        ka = cache_key_for_text(org_id=_ORG_A, identity=identity, text="same")
        kb = cache_key_for_text(org_id=_ORG_B, identity=identity, text="same")
        assert ka != kb
        assert ka.startswith(f"{_ORG_A}:embed:v1:")
        assert kb.startswith(f"{_ORG_B}:embed:v1:")

    def test_revision_changes_the_key(self) -> None:
        without = cache_key_for_text(org_id=_ORG_A, identity=_identity(), text="same")
        with_a = cache_key_for_text(org_id=_ORG_A, identity=_identity(revision="a"), text="same")
        with_b = cache_key_for_text(org_id=_ORG_A, identity=_identity(revision="b"), text="same")
        assert without != with_a
        assert with_a != with_b
        assert with_a == redis_key(
            org_id=_ORG_A,
            digest_hex=_digest("same", revision="a"),
        )

    def test_dimensions_change_the_key(self) -> None:
        """Matryoshka: one id, two stored widths, two entries."""
        narrow = cache_key_for_text(org_id=_ORG_A, identity=_identity(dimensions=256), text="same")
        wide = cache_key_for_text(org_id=_ORG_A, identity=_identity(dimensions=1024), text="same")
        assert narrow != wide


class TestModelRevisionSetting:
    """IBEX_EMBEDDING_MODEL_REVISION is refused at startup when it cannot be meant."""

    @pytest.fixture(autouse=True)
    def _clear_revision_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("IBEX_EMBEDDING_MODEL_REVISION", raising=False)

    def test_unset_is_none(self) -> None:
        assert Settings().model_revision is None

    def test_read_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_MODEL_REVISION", "5617a9f61b028005a4858fdac8")
        assert Settings().model_revision == "5617a9f61b028005a4858fdac8"

    @pytest.mark.parametrize("value", ["", "   ", "\t\n "])
    def test_empty_is_none_not_empty_string(self, value: str) -> None:
        """An empty variable must not change the digest layout."""
        assert Settings(model_revision=value).model_revision is None

    def test_is_trimmed(self) -> None:
        assert Settings(model_revision="  rev1 ").model_revision == "rev1"

    def test_at_max_length_accepted(self) -> None:
        value = "r" * MAX_MODEL_REVISION_LEN
        assert Settings(model_revision=value).model_revision == value

    def test_over_max_length_refused_at_startup(self) -> None:
        with pytest.raises(ValidationError, match="maximum length"):
            Settings(model_revision="r" * (MAX_MODEL_REVISION_LEN + 1))

    def test_refused_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_MODEL_REVISION", "r" * (MAX_MODEL_REVISION_LEN + 1))
        with pytest.raises(ValidationError, match="maximum length"):
            Settings()

    def test_revision_bound_is_tighter_than_the_model_id_bound(self) -> None:
        """A revision is a sha or tag; the id bound is for provider model paths."""
        assert MAX_MODEL_REVISION_LEN < MAX_MODEL_ID_LEN
