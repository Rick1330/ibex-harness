"""Stub tool schema and handler tests."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.errors import PermissionDeniedError, SchemaError
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.principal import Principal
from app.tools import (
    SEARCH_MEMORY_SCHEMA,
    WRITE_MEMORY_SCHEMA,
    parse_search_args,
    parse_write_args,
    stub_search_memory,
    stub_write_memory,
)

ORG_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def test_search_schema_rejects_extra() -> None:
    with pytest.raises(SchemaError):
        parse_search_args({"query": "x", "extra": 1})


def test_write_schema_rejects_bad_category() -> None:
    with pytest.raises(SchemaError):
        parse_write_args({"content": "hello", "category": "nope"})


def test_search_requires_memory_read() -> None:
    principal = Principal(org_id=ORG_A, permissions=0)
    with pytest.raises(PermissionDeniedError):
        stub_search_memory(principal, parse_search_args({"query": "q"}))


def test_write_requires_memory_write() -> None:
    principal = Principal(org_id=ORG_A, permissions=MEMORY_READ)
    with pytest.raises(PermissionDeniedError):
        stub_write_memory(principal, parse_write_args({"content": "c"}))


def test_stub_search_is_org_scoped() -> None:
    a = stub_search_memory(
        Principal(org_id=ORG_A, permissions=MEMORY_READ),
        parse_search_args({"query": "same"}),
    )
    b = stub_search_memory(
        Principal(org_id=ORG_B, permissions=MEMORY_READ),
        parse_search_args({"query": "same"}),
    )
    assert a["org_id"] == str(ORG_A)
    assert b["org_id"] == str(ORG_B)
    assert a["results"][0]["memory_id"] != b["results"][0]["memory_id"]


def test_stub_write_shape() -> None:
    out = stub_write_memory(
        Principal(org_id=ORG_A, permissions=MEMORY_WRITE),
        parse_write_args({"content": "remember this"}),
    )
    assert out["stub"] is True
    assert out["persisted"] is False
    assert out["source"] == "mcp_explicit"
    assert out["org_id"] == str(ORG_A)


def test_schemas_forbid_additional_properties() -> None:
    assert SEARCH_MEMORY_SCHEMA["additionalProperties"] is False
    assert WRITE_MEMORY_SCHEMA["additionalProperties"] is False
