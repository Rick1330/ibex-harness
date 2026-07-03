#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = Path("benchmarks/output")


def data_path() -> Path:
    return OUT_DIR / "benchmark-data.json"


def badge_path() -> Path:
    return OUT_DIR / "badge.svg"

STATUS_COLORS = {
    "pass": "#22c55e",
    "regression": "#f59e0b",
    "fail": "#ef4444",
    "unknown": "#6b7280",
}


def resolve_status(data: dict) -> str:
    runs = data.get("runs", [])
    if not runs:
        return "unknown"
    return str(runs[0].get("status") or "unknown")


def resolve_p99(data: dict) -> float:
    runs = data.get("runs", [])
    if not runs:
        return 0.0
    k6 = runs[0].get("k6", {})
    return float(k6.get("p99_ms", 0.0))


def build_svg(status: str, p99_ms: float) -> str:
    color = STATUS_COLORS.get(status, STATUS_COLORS["unknown"])
    label = f"benchmarks {status} p99 {p99_ms:.2f}ms"
    width = max(180, len(label) * 7 + 20)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" aria-label="{label}">
  <title>{label}</title>
  <rect width="{width}" height="20" fill="#1f2937" rx="3"/>
  <rect x="0" width="90" height="20" fill="{color}" rx="3"/>
  <text x="6" y="14" fill="#ffffff" font-family="monospace" font-size="11">benchmarks</text>
  <text x="96" y="14" fill="#e5e7eb" font-family="monospace" font-size="11">{status} p99 {p99_ms:.2f}ms</text>
</svg>
"""


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data_file = data_path()
    badge_file = badge_path()
    if not data_file.exists():
        data = {"schema_version": 1, "baseline_sha": "", "runs": []}
    else:
        data = json.loads(data_file.read_text(encoding="utf-8"))

    status = resolve_status(data)
    p99_ms = resolve_p99(data)
    badge_file.write_text(build_svg(status, p99_ms), encoding="utf-8")
    print(json.dumps({"ok": True, "status": status, "p99_ms": p99_ms}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
