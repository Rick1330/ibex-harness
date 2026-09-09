"""Shared auth gRPC helpers for IBEX Python services."""

from authclient.codec import (
    MAX_TOKEN_BYTES,
    AuthCodecError,
    ValidateAgentWire,
    ValidateTokenWire,
    decode_validate_agent_response,
    decode_validate_token_response,
    encode_validate_agent_request,
    encode_validate_token_request,
    encode_varint,
)
from authclient.errors import AuthFailedError, AuthUnavailableError
from authclient.permissions import MEMORY_READ, MEMORY_WRITE, has_permission
from authclient.target import assert_trusted_insecure_auth_target

__all__ = [
    "AuthCodecError",
    "AuthFailedError",
    "AuthUnavailableError",
    "MEMORY_READ",
    "MEMORY_WRITE",
    "MAX_TOKEN_BYTES",
    "ValidateAgentWire",
    "ValidateTokenWire",
    "assert_trusted_insecure_auth_target",
    "decode_validate_agent_response",
    "decode_validate_token_response",
    "encode_validate_agent_request",
    "encode_validate_token_request",
    "encode_varint",
    "has_permission",
]
