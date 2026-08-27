"""Unit tests for content normalization and SHA-256 hashing."""

from __future__ import annotations

from app.dedup.hash import content_hash_sha256, normalize_content


def test_normalize_collapses_whitespace_and_lowercases() -> None:
    assert normalize_content("  Hello   WORLD\n") == "hello world"


def test_identical_normalized_content_same_hash() -> None:
    a = content_hash_sha256("User prefers Python")
    b = content_hash_sha256("  user   prefers   python  ")
    assert a == b
    assert len(a) == 64
    assert a == a.lower()


def test_different_content_different_hash() -> None:
    assert content_hash_sha256("alpha") != content_hash_sha256("beta")
