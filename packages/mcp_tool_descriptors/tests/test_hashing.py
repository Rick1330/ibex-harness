"""The canonical hash rule: titles out, stable JSON in, SHA-256 over the bytes."""

from __future__ import annotations

from mcp_tool_descriptors import canonical_sha256, short_digest


def test_canonical_hash_ignores_titles_but_keeps_title_properties() -> None:
    titled = {"title": "Input", "properties": {"title": {"type": "string"}}}
    untitled = {"properties": {"title": {"type": "string"}}}
    assert canonical_sha256(titled) == canonical_sha256(untitled)
    assert canonical_sha256([{"title": "T", "type": "string"}]) == (
        canonical_sha256([{"type": "string"}])
    )
    assert canonical_sha256({"a": 1}) != canonical_sha256({"a": 2})


def test_canonical_hash_ignores_key_order_and_whitespace() -> None:
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})


def test_canonical_hash_keeps_a_non_string_title() -> None:
    assert canonical_sha256({"title": 7}) != canonical_sha256({})


def test_canonical_hash_is_stable_for_a_description_string() -> None:
    description = "Read one session.\n"
    same_description = "Read one session.\n"
    assert canonical_sha256(description) == canonical_sha256(same_description)
    assert canonical_sha256("") != canonical_sha256(" ")


def test_short_digest_is_the_first_twelve_characters() -> None:
    digest = canonical_sha256({"a": 1})
    assert short_digest(digest) == digest[:12]
    assert len(short_digest(digest)) == 12
