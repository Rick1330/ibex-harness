"""Provider credential request/response schemas (no secrets)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

ProviderName = Literal[
    "openai",
    "anthropic",
    "azure_openai",
    "bedrock",
    "vllm_self_hosted",
]

ApiKeyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=8192),
]

BaseURLStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]


class ProviderCredentialUpsertRequest(BaseModel):
    provider_name: ProviderName
    api_key: ApiKeyStr
    base_url: BaseURLStr | None = None


class ProviderCredentialResponse(BaseModel):
    provider_name: str
    status: str
    key_hint: str
    base_url: str | None = None
    last_validated_at: datetime | None = None


class ProviderCredentialListResponse(BaseModel):
    credentials: list[ProviderCredentialResponse] = Field(default_factory=list)
