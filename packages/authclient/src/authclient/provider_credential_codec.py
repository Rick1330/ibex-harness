"""Protobuf wire codec for AuthService provider-credential RPCs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from authclient.codec import (
    _WIRE_LEN,
    _WIRE_VARINT,
    MAX_LIST_MESSAGE_BYTES,
    MAX_MESSAGE_BYTES,
    MAX_SUBMESSAGE_BYTES,
    MAX_TOKEN_BYTES,
    _bounded_string,
    _decode_plaintext,
    _decode_timestamp,
    _decode_utf8,
    _decode_varint,
    _encode_api_key_field,
    _encode_string_field,
    _read_bytes,
    _require_present,
    _skip_unknown,
    _walk_fields,
)


@dataclass(frozen=True, slots=True)
class CreateProviderCredentialEncodeFields:
    org_id: str
    provider_name: str
    api_key: str
    base_url: str = ""


@dataclass(frozen=True, slots=True)
class ProviderCredentialMetadataWire:
    provider_name: str
    status: str
    key_hint: str
    base_url: str = ""
    encryption_key_id: str = ""
    last_validated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class GetProviderCredentialWire:
    api_key: str = ""
    base_url: str = ""
    is_platform_default: bool = False


@dataclass(frozen=True, slots=True)
class ListProviderCredentialsWire:
    credentials: list[ProviderCredentialMetadataWire]


@dataclass(slots=True)
class _CredMetaDecodeState:
    provider_name: str | None = None
    status: str | None = None
    key_hint: str | None = None
    base_url: str = ""
    encryption_key_id: str = ""
    last_validated_at: datetime | None = None


@dataclass(slots=True)
class _GetCredDecodeState:
    api_key: str = ""
    base_url: str = ""
    is_platform_default: bool = False


@dataclass(slots=True)
class _ListCredDecodeState:
    credentials: list[ProviderCredentialMetadataWire] = field(default_factory=list)

def encode_create_provider_credential_request(
    fields: CreateProviderCredentialEncodeFields,
) -> bytes:
    """Encode CreateProviderCredentialRequest."""
    out = (
        _encode_string_field(1, fields.org_id)
        + _encode_string_field(2, fields.provider_name)
        + _encode_api_key_field(3, fields.api_key)
    )
    if fields.base_url:
        out += _encode_string_field(4, fields.base_url)
    return out


def decode_create_provider_credential_response(
    payload: bytes,
) -> ProviderCredentialMetadataWire:
    """Decode CreateProviderCredentialResponse (metadata only)."""
    return _decode_cred_metadata(payload)


def encode_org_provider_ref_request(*, org_id: str, provider_name: str) -> bytes:
    return _encode_string_field(1, org_id) + _encode_string_field(2, provider_name)


def encode_get_provider_credential_request(*, org_id: str, provider_name: str) -> bytes:
    return encode_org_provider_ref_request(org_id=org_id, provider_name=provider_name)


def decode_get_provider_credential_response(payload: bytes) -> GetProviderCredentialWire:
    state = _GetCredDecodeState()
    _walk_fields(
        payload,
        lambda buf, idx: _decode_get_cred_field(buf, idx, state),
        max_bytes=MAX_MESSAGE_BYTES,
    )
    return GetProviderCredentialWire(
        api_key=state.api_key,
        base_url=state.base_url,
        is_platform_default=state.is_platform_default,
    )


def encode_delete_provider_credential_request(*, org_id: str, provider_name: str) -> bytes:
    return encode_org_provider_ref_request(org_id=org_id, provider_name=provider_name)


def encode_list_provider_credentials_request(*, org_id: str) -> bytes:
    return _encode_string_field(1, org_id)


def decode_list_provider_credentials_response(
    payload: bytes,
) -> ListProviderCredentialsWire:
    state = _ListCredDecodeState()
    _walk_fields(
        payload,
        lambda buf, idx: _decode_list_cred_field(buf, idx, state),
        max_bytes=MAX_LIST_MESSAGE_BYTES,
    )
    return ListProviderCredentialsWire(credentials=state.credentials)


def _decode_cred_metadata(raw: bytes) -> ProviderCredentialMetadataWire:
    state = _CredMetaDecodeState()
    _walk_fields(
        raw,
        lambda buf, idx: _decode_cred_meta_field(buf, idx, state),
        max_bytes=MAX_SUBMESSAGE_BYTES,
    )
    ctx = "provider credential metadata"
    return ProviderCredentialMetadataWire(
        provider_name=_require_present(state.provider_name, ctx, "provider_name"),
        status=_require_present(state.status, ctx, "status"),
        key_hint=_require_present(state.key_hint, ctx, "key_hint"),
        base_url=state.base_url,
        encryption_key_id=state.encryption_key_id,
        last_validated_at=state.last_validated_at,
    )


def _decode_cred_meta_field(buf: bytes, idx: int, state: _CredMetaDecodeState) -> int:
    key, idx = _decode_varint(buf, idx)
    field, wire = key >> 3, key & 0x07
    if wire == _WIRE_LEN:
        data, idx = _read_bytes(buf, idx, max_len=MAX_SUBMESSAGE_BYTES)
        _apply_cred_meta_len(state, field, data)
        return idx
    return _skip_unknown(buf, idx, wire)


def _apply_cred_meta_len(state: _CredMetaDecodeState, field: int, data: bytes) -> None:
    strings = {
        1: ("provider_name", "provider_name"),
        2: ("status", "status"),
        3: ("key_hint", "key_hint"),
        4: ("base_url", "base_url"),
        5: ("encryption_key_id", "encryption_key_id"),
    }
    if field in strings:
        attr, label = strings[field]
        setattr(state, attr, _bounded_string(_decode_utf8(data), label))
        return
    if field == 6:
        state.last_validated_at = _decode_timestamp(data)


def _decode_get_cred_field(buf: bytes, idx: int, state: _GetCredDecodeState) -> int:
    key, idx = _decode_varint(buf, idx)
    field, wire = key >> 3, key & 0x07
    if wire == _WIRE_LEN:
        data, idx = _read_bytes(buf, idx, max_len=MAX_TOKEN_BYTES)
        _apply_get_cred_len(state, field, data)
        return idx
    if wire == _WIRE_VARINT:
        return _apply_get_cred_varint(buf, idx, state, field)
    return _skip_unknown(buf, idx, wire)


def _apply_get_cred_len(state: _GetCredDecodeState, field: int, data: bytes) -> None:
    if field == 1:
        state.api_key = _decode_plaintext(data)
        return
    if field == 2:
        state.base_url = _bounded_string(_decode_utf8(data), "base_url")


def _apply_get_cred_varint(
    buf: bytes, idx: int, state: _GetCredDecodeState, field: int
) -> int:
    num, idx = _decode_varint(buf, idx)
    if field == 3:
        state.is_platform_default = bool(num)
    return idx


def _decode_list_cred_field(buf: bytes, idx: int, state: _ListCredDecodeState) -> int:
    key, idx = _decode_varint(buf, idx)
    field, wire = key >> 3, key & 0x07
    if wire == _WIRE_LEN:
        raw, idx = _read_bytes(buf, idx, max_len=MAX_SUBMESSAGE_BYTES)
        if field == 1:
            state.credentials.append(_decode_cred_metadata(raw))
        return idx
    return _skip_unknown(buf, idx, wire)
