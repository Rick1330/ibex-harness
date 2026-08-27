#!/usr/bin/env python3
"""Structured PII recall harness for m3.C.1 (>95% target).

Usage (from services/memory):

  uv run python ../../benchmarks/memory/pii/recall_structured.py

Writes recall_structured.json beside this script.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Allow running from repo root or services/memory.
_ROOT = Path(__file__).resolve().parents[3]
_MEMORY = _ROOT / "services" / "memory"
if str(_MEMORY) not in sys.path:
    sys.path.insert(0, str(_MEMORY))

from app.config import Settings  # noqa: E402
from app.pii.service import PiiService  # noqa: E402

# Labeled fixture: each row must detect the expected Presidio entity type.
FIXTURES: list[dict[str, str]] = [
    {"id": "email-1", "text": "write to alice@example.com today", "entity": "EMAIL_ADDRESS"},
    {"id": "email-2", "text": "cc security@ibexharness.com on the thread", "entity": "EMAIL_ADDRESS"},
    {"id": "phone-1", "text": "desk line +1-415-555-2671 is staffed", "entity": "PHONE_NUMBER"},
    {"id": "phone-2", "text": "callback number (212) 555-0199 only", "entity": "PHONE_NUMBER"},
    {"id": "ssn-1", "text": "My SSN is 856-45-6789 verified", "entity": "US_SSN"},
    {"id": "ssn-2", "text": "social security number 219-09-9999 on the form", "entity": "US_SSN"},
    {"id": "cc-1", "text": "charge 4111111111111111 once", "entity": "CREDIT_CARD"},
    {"id": "cc-2", "text": "visa 5500000000000004 declined", "entity": "CREDIT_CARD"},
    {"id": "ip-1", "text": "source 203.0.113.10 blocked", "entity": "IP_ADDRESS"},
    {"id": "ip-2", "text": "peer 198.51.100.42 in logs", "entity": "IP_ADDRESS"},
    {"id": "email-3", "text": "From: noreply@vendor.example.com Subject: invoice", "entity": "EMAIL_ADDRESS"},
    {"id": "phone-3", "text": "SMS to +44 20 7946 0958 overnight", "entity": "PHONE_NUMBER"},
    {"id": "ssn-3", "text": "The patient's SSN is 856-45-6789.", "entity": "US_SSN"},
    {"id": "cc-3", "text": "amex 378282246310005 authorized", "entity": "CREDIT_CARD"},
    {"id": "ip-3", "text": "IPv4 192.0.2.55 seen", "entity": "IP_ADDRESS"},
    {"id": "email-4", "text": "owner is root@localhost.example.org", "entity": "EMAIL_ADDRESS"},
    {"id": "phone-4", "text": "fax 650-555-0111 for wet signatures", "entity": "PHONE_NUMBER"},
    {"id": "cc-4", "text": "mastercard 5105105105105100 on file", "entity": "CREDIT_CARD"},
    {"id": "ip-4", "text": "egress via 233.252.0.1 filtered", "entity": "IP_ADDRESS"},
    {"id": "ssn-4", "text": "employee social security number 457-55-5462", "entity": "US_SSN"},
]

WRITE_BUDGET_MS = 200.0
TARGET_RECALL = 0.95


def main() -> int:
    settings = Settings()
    svc = PiiService(settings)
    # Warmup
    svc.process("warmup alice@example.com")

    hits = 0
    latencies_ms: list[float] = []
    misses: list[str] = []
    for row in FIXTURES:
        t0 = time.perf_counter()
        result = svc.process(row["text"])
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        types = {f.entity_type for f in result.findings}
        if row["entity"] in types:
            hits += 1
        else:
            misses.append(f"{row['id']}: expected {row['entity']} got {sorted(types)}")

    n = len(FIXTURES)
    recall = hits / n
    latencies_ms.sort()
    p95 = latencies_ms[min(len(latencies_ms) - 1, int(round(0.95 * (len(latencies_ms) - 1))))]
    out = {
        "benchmark": "pii_structured_recall",
        "n": n,
        "hits": hits,
        "recall": recall,
        "target_recall": TARGET_RECALL,
        "pass": recall >= TARGET_RECALL,
        "latency_ms_p50": latencies_ms[len(latencies_ms) // 2],
        "latency_ms_p95": p95,
        "write_budget_ms_p95": WRITE_BUDGET_MS,
        "budget_share_p95": p95 / WRITE_BUDGET_MS,
        "spacy_model": settings.pii_spacy_model,
        "misses": misses,
    }
    path = Path(__file__).with_name("recall_structured.json")
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
