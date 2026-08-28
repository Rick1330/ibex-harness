"""Shared auth gRPC helpers for IBEX Python services."""

from authclient.codec import (
    MAX_TOKEN_BYTES,
    AuthCodecError,
    ValidateTokenWire,
    decode_validate_token_response,
    encode_validate_token_request,
    encode_varint,
)
from authclient.target import assert_trusted_insecure_auth_target

from authclient.permissions import MEMORY_READ, MEMORY_WRITE, has_permission

__all__ = [
    "AuthCodecError",
    "MEMORY_READ",
    "MEMORY_WRITE",
    "MAX_TOKEN_BYTES",
    "ValidateTokenWire",
    "assert_trusted_insecure_auth_target",
    "decode_validate_token_response",
    "encode_validate_token_request",
    "encode_varint",
    "has_permission",
]
