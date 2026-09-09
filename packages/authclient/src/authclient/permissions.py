"""Permission bits — must match packages/permissions (ADR-0009)."""

from __future__ import annotations

MEMORY_READ = 1 << 0
MEMORY_WRITE = 1 << 1
MEMORY_DELETE = 1 << 2
DIRECTIVE_READ = 1 << 8
DIRECTIVE_WRITE = 1 << 9
SESSION_CREATE = 1 << 16
SESSION_READ = 1 << 17
SESSION_TERMINATE = 1 << 18
TRACE_READ = 1 << 24
TRACE_EXPORT = 1 << 25
USER_MANAGE = 1 << 32
BILLING_READ = 1 << 33
BILLING_MANAGE = 1 << 34
ORG_SETTINGS_WRITE = 1 << 35
TOKEN_CREATE = 1 << 36
TOKEN_REVOKE = 1 << 37

AGENT_DEFAULT = MEMORY_READ | MEMORY_WRITE | SESSION_CREATE | SESSION_READ | TRACE_READ
READ_ONLY = MEMORY_READ | DIRECTIVE_READ | SESSION_READ | TRACE_READ
ADMIN = (
    AGENT_DEFAULT
    | DIRECTIVE_READ
    | DIRECTIVE_WRITE
    | SESSION_TERMINATE
    | TRACE_EXPORT
    | USER_MANAGE
    | BILLING_READ
    | BILLING_MANAGE
    | ORG_SETTINGS_WRITE
    | TOKEN_CREATE
    | TOKEN_REVOKE
)

ROLE_BITMAP = {
    "owner": ADMIN,
    "admin": ADMIN,
    "member": AGENT_DEFAULT,
    "viewer": READ_ONLY,
}


def has_permission(bitmap: int, required: int) -> bool:
    return bitmap & required == required


def bitmap_for_role(role: str) -> int:
    return ROLE_BITMAP.get(role, 0)
