"""Unit tests for service-auth token comparison."""

from __future__ import annotations

from app.deps import _bearer_token_matches


def test_empty_expected_never_matches() -> None:
    assert _bearer_token_matches("token", "") is False


def test_ascii_tokens_match() -> None:
    assert _bearer_token_matches("service-token", "service-token") is True


def test_ascii_tokens_mismatch() -> None:
    assert _bearer_token_matches("xxxxxxxxxxxxx", "service-token") is False


def test_non_ascii_equal_length_does_not_raise() -> None:
    expected = "service-token"
    provided = "é" * len(expected)
    assert _bearer_token_matches(provided, expected) is False


def test_non_ascii_matching_pair() -> None:
    token = "tokén-α"
    assert _bearer_token_matches(token, token) is True
