#!/usr/bin/env python3
"""Run extraction quality eval against gold_set/v1 (cassette | live | vllm).

Profiles:
  cassette (default / smoke / fast) — replay openai_cassettes.jsonl; $0; CI gate.
  live / record — call OpenAI when OPENAI_API_KEY is set (budgeted refresh).
  vllm — call VLLMExtractionProvider (manual; not CI-enforced).

Fails closed if cassette_manifest.prompt_sha256 != sha256(EXTRACTION_SYSTEM_PROMPT_BATCH)
unless EXTRACTION_EVAL_ALLOW_PROMPT_DRIFT=1 (operators only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
_WORKER = _DIR.parent
if str(_WORKER) not in sys.path:
    sys.path.insert(0, str(_WORKER))
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from app.extraction.batch import TurnPayload, format_batch_user_content, parse_batch_result
from app.extraction.prompt_v2 import EXTRACTION_SYSTEM_PROMPT_BATCH
from metrics import aggregate_scores, gated_metric_names, score_turn

GOLD_DIR = _DIR / "gold_set" / "v1"
OUTPUT_DIR = _DIR / "output"
LATEST_PATH = OUTPUT_DIR / "latest.json"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _prompt_sha256() -> str:
    return hashlib.sha256(EXTRACTION_SYSTEM_PROMPT_BATCH.encode()).hexdigest()


def _assert_prompt_matches_manifest(manifest: dict[str, Any]) -> None:
    expected = str(manifest.get("prompt_sha256") or "")
    actual = _prompt_sha256()
    if expected == actual:
        return
    if os.environ.get("EXTRACTION_EVAL_ALLOW_PROMPT_DRIFT") == "1":
        print(
            "WARNING: prompt_sha256 drift allowed via EXTRACTION_EVAL_ALLOW_PROMPT_DRIFT=1",
            file=sys.stderr,
        )
        return
    raise SystemExit(
        "cassette prompt_sha256 mismatch — EXTRACTION_SYSTEM_PROMPT_BATCH changed without "
        "re-recording cassettes. Re-run with EXTRACTION_EVAL_MODE=record (live OpenAI) and "
        "update cassette_manifest.json + openai_cassettes.jsonl in the same PR. "
        f"manifest={expected[:16]}… actual={actual[:16]}…"
    )


def _memory_to_dict(memory: Any) -> dict[str, Any]:
    if hasattr(memory, "model_dump"):
        dumped = memory.model_dump(mode="json")
        return dumped
    return dict(memory)


def _predict_cassette(
    conversation_id: str,
    cassettes: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    row = cassettes.get(conversation_id)
    if row is None:
        raise KeyError(f"missing cassette for {conversation_id}")
    batch = parse_batch_result(str(row["raw_json"]))
    # Flatten turns in index order for scoring keyed by turn_index later
    by_turn: dict[int, list[dict[str, Any]]] = {}
    for turn in batch.turns:
        by_turn[turn.turn_index] = [_memory_to_dict(m) for m in turn.memories]
    return by_turn, str(row.get("model") or "gpt-4o-mini")


def _predict_live(turns: list[TurnPayload], *, provider_name: str) -> tuple[dict[int, list[dict]], str]:
    from app.config import get_settings
    from app.extraction.factory import load_active_extraction_provider

    # Temporarily force provider via env for this process
    os.environ["IBEX_WORKER_EXTRACTION_PROVIDER"] = provider_name
    # Clear cached settings if present
    get_settings.cache_clear()  # type: ignore[attr-defined]
    provider = load_active_extraction_provider()
    user = format_batch_user_content(turns)
    call = provider.extract(EXTRACTION_SYSTEM_PROMPT_BATCH, user)
    batch = parse_batch_result(call.raw_json)
    by_turn = {
        turn.turn_index: [_memory_to_dict(m) for m in turn.memories] for turn in batch.turns
    }
    return by_turn, call.model


def run_eval(*, mode: str, provider: str) -> dict[str, Any]:
    conversations = _load_jsonl(GOLD_DIR / "conversations.jsonl")
    expected_rows = _load_jsonl(GOLD_DIR / "expected_memories.jsonl")
    manifest = json.loads((GOLD_DIR / "cassette_manifest.json").read_text(encoding="utf-8"))

    expected_by_conv: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in expected_rows:
        expected_by_conv[str(row["conversation_id"])].append(row)

    cassettes: dict[str, dict[str, Any]] = {}
    if mode in {"cassette", "smoke", "fast"}:
        _assert_prompt_matches_manifest(manifest)
        for row in _load_jsonl(GOLD_DIR / "openai_cassettes.jsonl"):
            cassettes[str(row["conversation_id"])] = row

    turn_scores = []
    model_used = "unknown"
    recorded: list[dict[str, Any]] = []

    for conv in conversations:
        cid = str(conv["conversation_id"])
        turns = [TurnPayload.model_validate(t) for t in conv["turns"]]
        if mode in {"cassette", "smoke", "fast"}:
            by_turn, model_used = _predict_cassette(cid, cassettes)
        elif mode in {"live", "record", "full", "vllm"}:
            pname = "vllm" if mode == "vllm" or provider == "vllm" else "openai"
            by_turn, model_used = _predict_live(turns, provider_name=pname)
            if mode == "record" and pname == "openai":
                batch_payload = {
                    "turns": [
                        {
                            "turn_index": ti,
                            "memories": by_turn.get(ti, []),
                        }
                        for ti in sorted(by_turn)
                    ]
                }
                recorded.append(
                    {
                        "conversation_id": cid,
                        "model": model_used,
                        "raw_json": json.dumps(batch_payload, separators=(",", ":")),
                    }
                )
        else:
            raise SystemExit(f"unknown mode: {mode}")

        for row in expected_by_conv[cid]:
            ti = int(row["turn_index"])
            predicted = by_turn.get(ti, [])
            expected = list(row["expected"])
            kinds = list(row.get("temporal_kinds") or ["indefinite"] * len(expected))
            turn_scores.append(score_turn(predicted, expected, temporal_kinds=kinds))

    metrics = aggregate_scores(turn_scores)
    enforcement = "manual" if provider == "vllm" or mode == "vllm" else "ci"
    report = {
        "benchmark": "extraction_quality",
        "gold_set": "v1",
        "mode": mode,
        "provider": "vllm" if mode == "vllm" or provider == "vllm" else "openai",
        "model": model_used,
        "enforcement": enforcement,
        "conversation_count": len(conversations),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prompt_sha256": _prompt_sha256(),
        "metrics": metrics,
        "gated_metrics": gated_metric_names(),
        "notes": (
            "OpenAI cassette/CI metrics are CI-enforced. "
            "vLLM metrics are manual-only (no GPU CI runner; ADR-0066)."
            if enforcement == "ci"
            else "vLLM result is manual / not CI-enforced (ADR-0066 path a)."
        ),
    }

    if mode == "record" and recorded:
        (GOLD_DIR / "openai_cassettes.jsonl").write_text(
            "\n".join(json.dumps(r) for r in recorded) + "\n", encoding="utf-8"
        )
        manifest["prompt_sha256"] = _prompt_sha256()
        manifest["recorded_at"] = report["generated_at"]
        manifest["model"] = model_used
        manifest["cassette_kind"] = "live_openai_recorded"
        (GOLD_DIR / "cassette_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(f"re-recorded {len(recorded)} OpenAI cassettes", file=sys.stderr)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _print_summary(report)
    return report


def _print_summary(report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    print("## Extraction quality eval")
    print()
    print(f"- provider: {report['provider']} (enforcement={report['enforcement']})")
    print(f"- mode: {report['mode']}")
    print(f"- model: {report['model']}")
    print(f"- conversations: {report['conversation_count']}")
    print(f"- notes: {report['notes']}")
    print()
    print("### Metrics")
    for name in gated_metric_names():
        print(f"- {name}: {metrics[name]:.4f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        default=os.environ.get("EXTRACTION_EVAL_MODE", "cassette"),
        choices=["cassette", "smoke", "fast", "live", "record", "full", "vllm"],
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("EXTRACTION_EVAL_PROVIDER", "openai"),
        choices=["openai", "vllm"],
    )
    args = parser.parse_args(argv)
    run_eval(mode=args.mode, provider=args.provider)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
