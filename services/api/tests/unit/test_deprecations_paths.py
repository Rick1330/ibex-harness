"""Unit tests for the proxy path selector and the duplicate rules (W5.4).

A ``proxy`` entry is addressed by one exact request path, and the proxy refuses to
start on two announced entries for one path, so these tests pin the grammar, the
required field, the ``unknown-field`` message a path on any other surface keeps,
and the scope of the duplicate rule: it mirrors the loader's notice map, so only
an announced entry with the headers declared can collide.

The field rules live in ``test_deprecations.py`` and the registry cross-checks in
``test_deprecations_cross.py``; the builders they all share are in
``deprecations_test_support.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.deprecations_test_support import checked, entry, proxy_entry


def test_announced_proxy_deprecation_with_an_exact_path_passes(tmp_path: Path) -> None:
    """The proxy addresses a route by exact path; a valid entry is the committed shape."""
    assert checked(tmp_path, [proxy_entry()]) == []


def test_proxy_entry_without_a_path_fails(tmp_path: Path) -> None:
    """The proxy rejects a path-less proxy entry at startup, so CI must reject it first."""
    record_entry = proxy_entry()
    del record_entry["path"]
    assert checked(tmp_path, [record_entry]) == ["missing-field: dep.agents.read lacks path"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (None, "invalid-field: dep.agents.read.path must be a string, not None"),
        ("", "empty-field: dep.agents.read has empty path"),
    ],
    ids=["null", "empty"],
)
def test_proxy_path_must_be_a_non_empty_string(tmp_path: Path, path: object, expected: str) -> None:
    """A null or empty selector is not a path, and the dedicated rule owns its message."""
    record_entry = proxy_entry()
    record_entry["path"] = path
    assert checked(tmp_path, [record_entry]) == [expected]


@pytest.mark.parametrize(
    "path",
    [
        "v1/chat",
        "/v1/chat/",
        "/v1/chat/{id}",
        "/v1/chat?stream=1",
        "/v1/chat#frag",
        "/v1/chat completions",
        "/v1//chat",
    ],
    ids=["relative", "trailing-slash", "template", "query", "fragment", "space", "empty-segment"],
)
def test_proxy_entry_with_an_invalid_path_fails(tmp_path: Path, path: str) -> None:
    """The grammar is the proxy's: one exact route path, never a template or a query."""
    failures = checked(tmp_path, [proxy_entry(path=path)])
    assert failures == [
        (
            f"invalid-path: dep.agents.read.path {path!r} must be one exact route path "
            "(no trailing slash, no template, no query)"
        )
    ]


def test_duplicate_announced_proxy_path_fails(tmp_path: Path) -> None:
    """The proxy keys its notices by exact path and exits on a second entry for one path."""
    entries = [proxy_entry(id="dep.a"), proxy_entry(id="dep.b")]
    assert checked(tmp_path, entries) == [
        "duplicate-path: dep.a and dep.b both announce /v1/chat/completions"
    ]


def test_two_announced_proxy_entries_on_different_paths_pass(tmp_path: Path) -> None:
    """Distinct paths are distinct notices, so the proxy can announce both."""
    entries = [proxy_entry(id="dep.a"), proxy_entry(id="dep.b", path="/v1/embeddings")]
    assert checked(tmp_path, entries) == []


def test_duplicate_path_scope_is_the_loader_announcing_entries_only(tmp_path: Path) -> None:
    """A proposal and an announcement may share a path: the loader drops the proposal first.

    ``buildDeprecationNotices`` indexes only the entries it announces, so the rule
    must not be wider than that or the check would reject a record the proxy starts on.
    """
    proposal = proxy_entry(
        id="dep.a",
        status="proposed",
        headers_implemented=False,
        announced_on=None,
    )
    assert checked(tmp_path, [proposal, proxy_entry(id="dep.b")]) == []
    second_proposal = proxy_entry(
        id="dep.b",
        status="proposed",
        headers_implemented=False,
        announced_on=None,
    )
    assert checked(tmp_path, [proposal, second_proposal]) == []


@pytest.mark.parametrize("value", ["/v1/agents", "", None], ids=["path", "empty", "null"])
def test_path_on_a_non_proxy_entry_fails(tmp_path: Path, value: object) -> None:
    """`path` is the proxy selector: on a REST entry it is a claim nothing reads.

    The message stays the same one `unknown-field` a stray field always produced,
    including for a null or empty value.
    """
    record_entry = entry()
    record_entry["path"] = value
    failures = checked(tmp_path, [record_entry])
    assert failures == ["unknown-field: dep.agents.read has path"]
