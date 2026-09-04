"""Load the generate-and-diff ModelCapability catalog (ADR-0067)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_CATALOG_PATH = _DATA_DIR / "model_capabilities.v1.json"


class UnknownModelError(KeyError):
    """Raised when ``model`` is absent from the generated capability catalog."""


@dataclass(frozen=True, slots=True)
class ModelCapability:
    model_id: str
    provider: str
    context_window: int
    max_output_tokens: int
    supports_tools: bool
    supports_vision: bool
    supports_streaming: bool
    tokenizer_family: str


@dataclass(frozen=True, slots=True)
class TokenizerFamilyPolicy:
    estimate_kind: str
    safety_buffer_fraction: float


@dataclass(frozen=True, slots=True)
class CapabilityCatalog:
    schema_version: int
    source: str
    models: dict[str, ModelCapability]
    tokenizer_families: dict[str, TokenizerFamilyPolicy]

    def for_model(self, model: str) -> ModelCapability:
        key = model.strip()
        cap = self.models.get(key)
        if cap is None:
            raise UnknownModelError(f"unknown model {model!r} — not in generated capability catalog")
        return cap

    def family_policy(self, family: str) -> TokenizerFamilyPolicy:
        policy = self.tokenizer_families.get(family)
        if policy is None:
            raise UnknownModelError(f"unknown tokenizer_family {family!r}")
        return policy


def _parse_model(row: dict[str, Any]) -> ModelCapability:
    return ModelCapability(
        model_id=str(row["model_id"]),
        provider=str(row["provider"]),
        context_window=int(row["context_window"]),
        max_output_tokens=int(row["max_output_tokens"]),
        supports_tools=bool(row["supports_tools"]),
        supports_vision=bool(row["supports_vision"]),
        supports_streaming=bool(row["supports_streaming"]),
        tokenizer_family=str(row["tokenizer_family"]),
    )


def _parse_family(row: dict[str, Any]) -> TokenizerFamilyPolicy:
    frac = float(row["safety_buffer_fraction"])
    if not 0.0 <= frac <= 1.0:
        raise ValueError(f"safety_buffer_fraction out of range: {frac}")
    return TokenizerFamilyPolicy(
        estimate_kind=str(row["estimate_kind"]),
        safety_buffer_fraction=frac,
    )


def load_catalog(path: Path | None = None) -> CapabilityCatalog:
    catalog_path = path if path is not None else _DEFAULT_CATALOG_PATH
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    if int(raw.get("schema_version", 0)) != 1:
        raise ValueError(f"unsupported schema_version: {raw.get('schema_version')!r}")
    models: dict[str, ModelCapability] = {}
    for row in raw["models"]:
        cap = _parse_model(row)
        models[cap.model_id] = cap
    families = {
        name: _parse_family(policy) for name, policy in dict(raw["tokenizer_families"]).items()
    }
    return CapabilityCatalog(
        schema_version=1,
        source=str(raw["source"]),
        models=models,
        tokenizer_families=families,
    )


@lru_cache(maxsize=1)
def default_catalog() -> CapabilityCatalog:
    return load_catalog()
