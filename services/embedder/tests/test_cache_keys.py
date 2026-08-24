"""Unit tests for content-hash keys and org-scoped Redis key format."""

from __future__ import annotations

from uuid import UUID

from app.cache.keys import cache_key_for_text, content_digest, redis_key

_ORG_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class TestContentDigest:
    def test_stable_for_same_inputs(self) -> None:
        a = content_digest(model_id="m", dimensions=8, text="hello")
        b = content_digest(model_id="m", dimensions=8, text="hello")
        assert a == b
        assert len(a) == 64

    def test_model_id_changes_digest(self) -> None:
        a = content_digest(model_id="m1", dimensions=8, text="hello")
        b = content_digest(model_id="m2", dimensions=8, text="hello")
        assert a != b

    def test_dimensions_changes_digest_matryoshka(self) -> None:
        a = content_digest(model_id="m", dimensions=256, text="hello")
        b = content_digest(model_id="m", dimensions=3072, text="hello")
        assert a != b

    def test_text_changes_digest(self) -> None:
        a = content_digest(model_id="m", dimensions=8, text="hello")
        b = content_digest(model_id="m", dimensions=8, text="Hello")
        assert a != b

    def test_pipe_in_model_id_not_ambiguous(self) -> None:
        """Length-prefixing avoids delimiter collisions with model ids containing |."""
        left = content_digest(model_id="org|model", dimensions=8, text="x")
        # Different encoding of ambiguous concatenation must not collide.
        right = content_digest(model_id="org", dimensions=8, text="modelx")
        assert left != right

    def test_exact_utf8_no_normalization(self) -> None:
        # Combining vs precomposed would differ if we NFC'd; we must not.
        a = content_digest(model_id="m", dimensions=8, text="café")
        b = content_digest(model_id="m", dimensions=8, text="cafe\u0301")
        assert a != b


class TestRedisKey:
    def test_org_prefix_and_version(self) -> None:
        digest = "a" * 64
        key = redis_key(org_id=_ORG_A, digest_hex=digest)
        assert key == f"{_ORG_A}:embed:v1:{digest}"

    def test_cross_tenant_keys_differ(self) -> None:
        ka = cache_key_for_text(
            org_id=_ORG_A, model_id="m", dimensions=8, text="same"
        )
        kb = cache_key_for_text(
            org_id=_ORG_B, model_id="m", dimensions=8, text="same"
        )
        assert ka != kb
        assert ka.startswith(f"{_ORG_A}:")
        assert kb.startswith(f"{_ORG_B}:")
