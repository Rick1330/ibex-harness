#!/usr/bin/env python3
"""Run extraction quality eval against gold_set/v1 (cassette | live | vllm).

Profiles:
  cassette (default / smoke / fast) — replay openai_cassettes.jsonl; $0; CI gate.
  live / record — call OpenAI when OPENAI_API_KEY is set (budgeted refresh).
  vllm — call VLLMExtractionProvider (manual; not CI-enforced).

Fails closed if cassette_manifest.prompt_sha256 != sha256(EXTRACTION_SYSTEM_PROMPT_BATCH)
unless EXTRACTION_EVAL_ALLOW_PROMPT_DRIFT=1 (operators only).

Also fails closed when gold-set file hashes, conversation ID sets, or declared
cardinalities diverge from cassette_manifest.json.
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

_CONVERSATIONS_NAME = "conversations.jsonl"
_EXPECTED_NAME = "expected_memories.jsonl"
_CASSETTES_NAME = "openai_cassettes.jsonl"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():  # NOSONAR pythonsecurity:S2083
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()  # NOSONAR pythonsecurity:S2083


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


def _conversation_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row["conversation_id"]) for row in rows}


def _assert_gold_integrity(
    manifest: dict[str, Any],
    conversations: list[dict[str, Any]],
    expected_rows: list[dict[str, Any]],
    *,
    cassettes: dict[str, dict[str, Any]] | None,
) -> None:
    conv_path = GOLD_DIR / _CONVERSATIONS_NAME
    exp_path = GOLD_DIR / _EXPECTED_NAME
    cas_path = GOLD_DIR / _CASSETTES_NAME

    expected_hashes = {
        "conversations_sha256": _file_sha256(conv_path),
        "expected_memories_sha256": _file_sha256(exp_path),
    }
    for key, actual in expected_hashes.items():
        declared = str(manifest.get(key) or "")
        if declared != actual:
            raise SystemExit(f"gold-set {key} mismatch: manifest={declared[:16]}… actual={actual[:16]}…")

    conv_ids = _conversation_ids(conversations)
    exp_ids = _conversation_ids(expected_rows)
    declared_count = int(manifest.get("conversation_count") or 0)
    if len(conv_ids) != declared_count or len(conversations) != declared_count:
        raise SystemExit(
            f"conversation cardinality mismatch: declared={declared_count} "
            f"rows={len(conversations)} unique_ids={len(conv_ids)}"
        )
    if conv_ids != exp_ids:
        raise SystemExit("conversation_id set mismatch between conversations and expected_memories")

    if cassettes is not None:
        cas_hash = _file_sha256(cas_path)
        declared_cas = str(manifest.get("cassettes_sha256") or "")
        if declared_cas != cas_hash:
            raise SystemExit(
                f"gold-set cassettes_sha256 mismatch: manifest={declared_cas[:16]}… actual={cas_hash[:16]}…"
            )
        cassette_count = int(manifest.get("cassette_count") or 0)
        if len(cassettes) != cassette_count or cassette_count != declared_count:
            raise SystemExit(
                f"cassette cardinality mismatch: declared={cassette_count} "
                f"loaded={len(cassettes)} conversations={declared_count}"
            )
        if set(cassettes) != conv_ids:
            raise SystemExit("conversation_id set mismatch between conversations and cassettes")


def _memory_to_dict(memory: Any) -> dict[str, Any]:
    if hasattr(memory, "model_dump"):
        return memory.model_dump(mode="json")
    return dict(memory)


def _predict_cassette(
    conversation_id: str,
    cassettes: dict[str, dict[str, Any]],
) -> tuple[dict[int, list[dict[str, Any]]], str]:
    row = cassettes.get(conversation_id)
    if row is None:
        raise KeyError(f"missing cassette for {conversation_id}")
    batch = parse_batch_result(str(row["raw_json"]))
    by_turn: dict[int, list[dict[str, Any]]] = {}
    for turn in batch.turns:
        by_turn[turn.turn_index] = [_memory_to_dict(m) for m in turn.memories]
    return by_turn, str(row.get("model") or "gpt-4o-mini")


def _predict_live(turns: list[TurnPayload], *, provider_name: str) -> tuple[dict[int, list[dict]], str]:
    from app.config import get_settings
    from app.extraction.factory import load_active_extraction_provider

    os.environ["IBEX_WORKER_EXTRACTION_PROVIDER"] = provider_name
    get_settings.cache_clear()  # type: ignore[attr-defined]
    provider = load_active_extraction_provider()
    user = format_batch_user_content(turns)
    call = provider.extract(EXTRACTION_SYSTEM_PROMPT_BATCH, user)
    batch = parse_batch_result(call.raw_json)
    by_turn = {
        turn.turn_index: [_memory_to_dict(m) for m in turn.memories] for turn in batch.turns
    }
    return by_turn, call.model


def _load_cassettes() -> dict[str, dict[str, Any]]:
    cassettes: dict[str, dict[str, Any]] = {}
    for row in _load_jsonl(GOLD_DIR / _CASSETTES_NAME):
        cassettes[str(row["conversation_id"])] = row
    return cassettes


def _score_conversations(
    conversations: list[dict[str, Any]],
    expected_by_conv: dict[str, list[dict[str, Any]]],
    *,
    mode: str,
    provider: str,
    cassettes: dict[str, dict[str, Any]],
) -> tuple[list[Any], str, list[dict[str, Any]]]:
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
                        {"turn_index": ti, "memories": by_turn.get(ti, [])}
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

    return turn_scores, model_used, recorded


def _build_report(
    *,
    mode: str,
    provider: str,
    model_used: str,
    conversation_count: int,
    metrics: dict[str, float],
) -> dict[str, Any]:
    enforcement = "manual" if provider == "vllm" or mode == "vllm" else "ci"
    return {
        "benchmark": "extraction_quality",
        "gold_set": "v1",
        "mode": mode,
        "provider": "vllm" if mode == "vllm" or provider == "vllm" else "openai",
        "model": model_used,
        "enforcement": enforcement,
        "conversation_count": conversation_count,
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


def _refresh_manifest_hashes(manifest: dict[str, Any], *, model_used: str, generated_at: str) -> None:
    cas_path = GOLD_DIR / _CASSETTES_NAME
    manifest["prompt_sha256"] = _prompt_sha256()
    manifest["recorded_at"] = generated_at
    manifest["model"] = model_used
    manifest["cassette_kind"] = "live_openai_recorded"
    manifest["cassettes_sha256"] = _file_sha256(cas_path)
    manifest["conversations_sha256"] = _file_sha256(GOLD_DIR / _CONVERSATIONS_NAME)
    manifest["expected_memories_sha256"] = _file_sha256(GOLD_DIR / _EXPECTED_NAME)
    (GOLD_DIR / "cassette_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_latest(report: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(  # NOSONAR pythonsecurity:S2083,pythonsecurity:S8707
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )


def run_eval(*, mode: str, provider: str) -> dict[str, Any]:
    conversations = _load_jsonl(GOLD_DIR / _CONVERSATIONS_NAME)
    expected_rows = _load_jsonl(GOLD_DIR / _EXPECTED_NAME)
    manifest = json.loads(
        (GOLD_DIR / "cassette_manifest.json").read_text(encoding="utf-8")  # NOSONAR
    )

    expected_by_conv: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in expected_rows:
        expected_by_conv[str(row["conversation_id"])].append(row)

    cassettes: dict[str, dict[str, Any]] = {}
    if mode in {"cassette", "smoke", "fast"}:
        _assert_prompt_matches_manifest(manifest)
        cassettes = _load_cassettes()
        _assert_gold_integrity(manifest, conversations, expected_rows, cassettes=cassettes)
    else:
        _assert_gold_integrity(manifest, conversations, expected_rows, cassettes=None)

    turn_scores, model_used, recorded = _score_conversations(
        conversations,
        expected_by_conv,
        mode=mode,
        provider=provider,
        cassettes=cassettes,
    )
    metrics = aggregate_scores(turn_scores)
    report = _build_report(
        mode=mode,
        provider=provider,
        model_used=model_used,
        conversation_count=len(conversations),
        metrics=metrics,
    )

    if mode == "record" and recorded:
        (GOLD_DIR / _CASSETTES_NAME).write_text(
            "\n".join(json.dumps(r) for r in recorded) + "\n",
            encoding="utf-8",
        )
        _refresh_manifest_hashes(
            manifest, model_used=model_used, generated_at=report["generated_at"]
        )
        print(f"re-recorded {len(recorded)} OpenAI cassettes", file=sys.stderr)

    _write_latest(report)
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
