"""Shared auth gRPC helpers for IBEX Python services.

The ``grpc`` dependency is an optional extra: this package root must import
without it so codec-, permission-, and trust-only consumers (for example
``packages/mcp_gateway``) do not need a compiled gRPC runtime. Dial clients that
need a channel import :mod:`authclient.channel` directly.
"""

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
from authclient.errors import AuthFailedError, AuthUnavailableError, OrgSuspendedError
from authclient.permissions import (
    ADMIN,
    AGENT_DEFAULT,
    MEMORY_READ,
    MEMORY_WRITE,
    ORG_SETTINGS_WRITE,
    READ_ONLY,
    USER_MANAGE,
    bitmap_for_role,
    has_permission,
)
from authclient.target import assert_trusted_insecure_auth_target

__all__ = [
    "ADMIN",
    "AGENT_DEFAULT",
    "MAX_TOKEN_BYTES",
    "MEMORY_READ",
    "MEMORY_WRITE",
    "ORG_SETTINGS_WRITE",
    "READ_ONLY",
    "USER_MANAGE",
    "AuthCodecError",
    "AuthFailedError",
    "AuthUnavailableError",
    "OrgSuspendedError",
    "ValidateAgentWire",
    "ValidateTokenWire",
    "assert_trusted_insecure_auth_target",
    "bitmap_for_role",
    "decode_validate_agent_response",
    "decode_validate_token_response",
    "encode_validate_agent_request",
    "encode_validate_token_request",
    "encode_varint",
    "has_permission",
]
