"""Unit tests for agent schemas (soft provider validation + bounds)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.agents import AgentCreate, AgentListQuery, AgentPatch


def test_create_soft_provider_and_model() -> None:
    body = AgentCreate(
        name="Support",
        slug="support",
        description="  hello  ",
        default_provider=" anthropic ",
        default_model=" claude-3-5 ",
        tags=["prod", "support"],
        config={"a": 1},
        metadata={"b": 2},
    )
    assert body.description == "hello"
    assert body.default_provider == "anthropic"
    assert body.default_model == "claude-3-5"
    assert body.tags == ["prod", "support"]


def test_blank_description_becomes_none() -> None:
    assert AgentCreate(name="A", slug="a", description="   ").description is None
    assert AgentPatch(description="   ").description is None


def test_description_utf8_byte_limit() -> None:
    # 2049 × U+00E9 (2 UTF-8 bytes each) = 4098 > DB octet_length 4096
    oversized = "é" * 2049
    assert len(oversized.encode("utf-8")) > 4096
    with pytest.raises(ValidationError):
        AgentCreate(name="A", slug="a", description=oversized)
    with pytest.raises(ValidationError):
        AgentPatch(description=oversized)


def test_empty_provider_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentCreate(name="A", slug="a", default_provider="  ")


def test_empty_model_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentPatch(default_model="")


def test_provider_max_length() -> None:
    with pytest.raises(ValidationError):
        AgentCreate(name="A", slug="a", default_provider="x" * 65)
    with pytest.raises(ValidationError):
        AgentPatch(default_model="m" * 129)


def test_slug_format() -> None:
    with pytest.raises(ValidationError):
        AgentCreate(name="A", slug="Bad_Slug")


def test_config_and_metadata_bounds() -> None:
    with pytest.raises(ValidationError):
        AgentCreate(name="A", slug="a", config={f"k{i}": i for i in range(51)})
    with pytest.raises(ValidationError):
        AgentPatch(metadata={f"k{i}": "x" * 200 for i in range(50)})
    with pytest.raises(ValidationError):
        AgentCreate(name="A", slug="a", metadata={f"k{i}": i for i in range(51)})


def test_tags_and_list_query_bounds() -> None:
    with pytest.raises(ValidationError):
        AgentCreate(name="A", slug="a", tags=[f"t{i}" for i in range(33)])
    with pytest.raises(ValidationError):
        AgentPatch(tags=[""])
    with pytest.raises(ValidationError):
        AgentCreate(name="A", slug="a", tags=["x" * 65])
    assert AgentPatch(tags=None).tags is None
    q = AgentListQuery(tags=["prod"], search="  hi  ")
    assert q.search == "hi"
    assert q.tags == ["prod"]


def test_tags_max_entries_helper() -> None:
    from app.schemas import agents as schemas

    with pytest.raises(ValueError):
        schemas._bound_tags([f"t{i}" for i in range(33)])


def test_list_query_blank_search() -> None:
    assert AgentListQuery(search="   ").search is None
    assert AgentListQuery(search=None).search is None
    from app.schemas import agents as schemas

    assert schemas._soft_provider_or_model(None, max_len=8, field_name="x") is None
    assert schemas._strip_optional_description(None) is None
    assert schemas._bound_config(None) is None
    assert schemas._bound_metadata(None) is None
    assert schemas._bound_tags(None) is None
