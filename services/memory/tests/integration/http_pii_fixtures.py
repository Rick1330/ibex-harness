"""PII-clean HTTP test content (hand-verified, not generated at runtime).

Why fixtures instead of generate-until-clean retries:
HTTP integration tests target routing, idempotency, Redis cache, and status codes —
not PII-stage behavior (that belongs in test_pii_service.py and test_pii_persist.py
with the real Presidio pipeline per CODING_STANDARDS.md).

Presidio + en_core_web_md can false-positive on random secrets.token_hex() suffixes
(digit runs, short tokens resembling entities). Each string below was chosen to avoid
person names, email/phone patterns, and location-shaped phrases; verified clean in CI
via test_http_fixture_strings_presidio_clean.
"""

from __future__ import annotations

# Seed row inserted before HTTP client exercises (uniqueness vs test bodies below).
HTTP_SEED_CONTENT = (
    "Organized folders improve retrieval speed during weekly workspace audits"
)

# Distinct bodies per HTTP integration scenario (no shared content_hash collisions).
HTTP_NOVEL_WRITE_CONTENT = (
    "Dark theme reduces glare during evening dashboard review sessions"
)
HTTP_DUPLICATE_PAYLOAD_CONTENT = (
    "Identical payload marker for duplicate detection path testing only"
)
HTTP_REDIS_CACHE_CONTENT = (
    "Cache population probe uses neutral technical vocabulary exclusively"
)
HTTP_IDEMPOTENT_WRITE_CONTENT = (
    "Idempotency replay probe with stable neutral operational wording"
)

# For tests that only need uniqueness and do not exercise PII (e.g. broken-redis path).
HTTP_UNIQUE_SUFFIX_CONTENT = "After commit resilience probe neutral wording ref"
