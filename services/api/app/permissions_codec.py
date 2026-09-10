"""Permission string ↔ ADR-0009 bitmap codec (management API only)."""

from __future__ import annotations

from apierror_py import VALIDATION_ERROR, FieldError

from app.errors import ApiError

# Canonical strings → bit index (locked catalog for 4.A.4).
_PERMISSION_BITS: dict[str, int] = {
    "memory:read": 0,
    "memory:write": 1,
    "memory:delete": 2,
    "memory:bulk_export": 3,
    "directive:read": 8,
    "directive:write": 9,
    "directive:promote": 10,
    "directive:revoke": 11,
    "session:create": 16,
    "session:read": 17,
    "session:terminate": 18,
    "trace:read": 24,
    "trace:export": 25,
    "admin:user_manage": 32,
    "admin:billing_read": 33,
    "admin:billing_manage": 34,
    "admin:org_manage": 35,  # alias for OrgSettingsWrite — never bit 9
    "admin:token_create": 36,
    "admin:token_revoke": 37,
    "marketplace:publish": 40,
    "marketplace:install": 41,
    "federation:share": 48,
}

# Bit → canonical string (bit 35 emits admin:org_manage).
_BIT_TO_STRING: dict[int, str] = {bit: name for name, bit in _PERMISSION_BITS.items()}

KNOWN_PERMISSION_STRINGS: frozenset[str] = frozenset(_PERMISSION_BITS)


def strings_to_bitmap(permissions: list[str]) -> int:
    """OR permission strings into an int64 bitmap. Unknown/wrong-case → VALIDATION_ERROR."""
    bitmap = 0
    for raw in permissions:
        bit = _PERMISSION_BITS.get(raw)
        if bit is None:
            raise ApiError(
                code=VALIDATION_ERROR,
                message="Request validation failed",
                detail="One or more fields failed validation",
                field_errors=[
                    FieldError(
                        field="permissions",
                        code="INVALID",
                        message=f"unknown permission string: {raw!r}",
                    )
                ],
            )
        bitmap |= 1 << bit
    return bitmap


def bitmap_to_strings(bitmap: int) -> list[str]:
    """Emit known set bits as canonical permission strings (stable bit order)."""
    out: list[str] = []
    for bit in sorted(_BIT_TO_STRING):
        if bitmap & (1 << bit):
            out.append(_BIT_TO_STRING[bit])
    return out
