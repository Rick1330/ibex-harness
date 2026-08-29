"""Unit tests for Tier-1 read-path PII guard."""

from __future__ import annotations

from app.read.pii_guard import tier1_structured_pii_present


def test_tier1_detects_email() -> None:
    assert tier1_structured_pii_present("Contact billing@example.com for help")


def test_tier1_skips_email_placeholder() -> None:
    assert not tier1_structured_pii_present("Contact [EMAIL_ADDRESS] for help")


def test_tier1_detects_ssn() -> None:
    assert tier1_structured_pii_present("SSN on file: 123-45-6789")


def test_tier1_detects_phone() -> None:
    assert tier1_structured_pii_present("Call +1-212-555-0182 today")


def test_tier1_clean_content() -> None:
    assert not tier1_structured_pii_present("User prefers dark mode in the IDE")
