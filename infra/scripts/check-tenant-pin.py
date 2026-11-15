#!/usr/bin/env python3
"""Fail when a file sets the RLS org GUC without pinning the tenant role.

The tenancy claim rests on one rule: a transaction that reads or writes tenant
rows must first assume a role that RLS actually applies to. Under the owner
login a missing pin is invisible -- ``SET LOCAL`` outside a transaction is a
silent no-op and the owner bypasses every policy -- so the defect does not
surface until the DSN moves to a capability login. That is exactly how six
stores shipped inert.

This guard is the mechanical version of the rule: any tracked file that writes
``app.current_org_id`` must also issue ``SET LOCAL ROLE`` (or delegate to
``packages/pgtenant``, which does both). Adding a new unpinned store now fails
``make repo-guards`` instead of waiting for a cross-tenant bug.

Exit 1 on a violation, 0 otherwise. Stdlib only.
"""

from __future__ import annotations

import re
import subprocess
import sys

GUC_WRITE = re.compile(r"set_config\(\s*'app\.current_org_id'")
ROLE_PIN = re.compile(r"SET LOCAL ROLE\s+\w+|pgtenant\.PinOrg")

# Files that legitimately write the GUC without pinning, each with the reason it
# is safe. Keep this list short and justified; it is the only way to bypass the
# guard, so an unexplained entry defeats it.
ALLOWED: dict[str, str] = {
    "packages/privacyaudit/ledger.go": (
        "CLI-only verifier (infra/scripts/cmd/privacy-audit-verify) that keeps the "
        "owner DSN by design; it never runs inside a service or a tenant request."
    ),
}

# Test code sets the GUC to *simulate* a tenant and asserts on it; it is not a
# production read path and pinning it would test the pin with the pin.
SKIP_SUFFIXES = ("_test.go",)
SKIP_SEGMENTS = ("/tests/", "/testdata/", "/.venv/", "/build/")
# Benchmark harnesses run against an owner DSN by design, like the privacy-audit
# CLI: they seed and measure, they do not serve a tenant request.
SKIP_PREFIXES = ("benchmarks/",)


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "grep", "-l", "-e", "app.current_org_id", "--", "*.go", "*.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode not in (0, 1):
        sys.exit(f"check-tenant-pin: git grep failed: {out.stderr.strip()}")
    return [line for line in out.stdout.splitlines() if line]


def is_skipped(path: str) -> bool:
    """True when the file is test code, build output, or an owner-DSN harness."""
    if path.endswith(SKIP_SUFFIXES) or path in ALLOWED:
        return True
    if path.startswith(SKIP_PREFIXES):
        return True
    return any(segment in path for segment in SKIP_SEGMENTS)


def sets_org_guc_without_pin(path: str) -> bool:
    """True when a tracked file writes the org GUC and never pins a role."""
    with open(path, encoding="utf-8") as handle:
        body = handle.read()
    return bool(GUC_WRITE.search(body)) and not ROLE_PIN.search(body)


def main() -> int:
    violations = [
        path for path in tracked_files()
        if not is_skipped(path) and sets_org_guc_without_pin(path)
    ]
    if not violations:
        print("check-tenant-pin: every org-GUC writer also pins a tenant role")
        return 0

    print(
        "check-tenant-pin: these files set app.current_org_id without "
        "pinning a tenant role:",
        file=sys.stderr,
    )
    for path in violations:
        print(f"  {path}", file=sys.stderr)
    print(
        "\nPin the role first (SET LOCAL ROLE ibex_app) or delegate to "
        "packages/pgtenant.PinOrg, which issues both statements in order. "
        "If the file is genuinely owner-DSN-only, add it to ALLOWED in "
        "infra/scripts/check-tenant-pin.py with the reason.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
