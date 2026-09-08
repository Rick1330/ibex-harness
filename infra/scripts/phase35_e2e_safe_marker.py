#!/usr/bin/env python3
"""Generate a Presidio-clean uniqueness marker for Phase 3.5 e2e.

Random hex / long concatenations / many NATO tokens false-positive as NRP/PERSON/
LOCATION. We sample short material/color words and verify the full memory + chat
bodies used by the suite stay pii_detected=False.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

_WORDS = (
    "oak",
    "pine",
    "cedar",
    "maple",
    "birch",
    "willow",
    "elm",
    "flint",
    "slate",
    "granite",
    "basalt",
    "copper",
    "zinc",
    "nickel",
    "tin",
    "nylon",
    "cotton",
    "linen",
    "wool",
    "silk",
    "hemp",
    "canvas",
    "felt",
    "ember",
    "frost",
    "gust",
    "haze",
    "mist",
    "dew",
    "spark",
    "glow",
    "red",
    "blue",
    "green",
    "amber",
    "coral",
    "onyx",
)

_REPO = Path(__file__).resolve().parents[2]
_MEMORY_APP = _REPO / "services" / "memory"


def _memory_content(marker: str) -> str:
    return f"ibex phase three five learning loop durable preference marker {marker}"


def _probe_bodies(marker: str) -> list[str]:
    return [
        _memory_content(marker),
        f"phase35 warm turn zero remember later {marker}",
        f"Please remember my preference marker {marker} forever.",
        f"phase35 overhead probe about {marker}",
    ]


def _sample_marker() -> str:
    return " ".join(secrets.choice(_WORDS) for _ in range(5))


def _pii_service():
    sys.path.insert(0, str(_MEMORY_APP))
    from app.config import Settings  # noqa: WPS433
    from app.pii.service import PiiService  # noqa: WPS433

    return PiiService(Settings())


def generate(max_attempts: int = 80) -> str:
    svc = _pii_service()
    for _ in range(max_attempts):
        marker = _sample_marker()
        if all(not svc.process(body).pii_detected for body in _probe_bodies(marker)):
            return marker
    raise RuntimeError(f"no Presidio-clean marker after {max_attempts} attempts")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-attempts", type=int, default=80)
    args = parser.parse_args()
    print(generate(max_attempts=args.max_attempts), end="")


if __name__ == "__main__":
    main()
