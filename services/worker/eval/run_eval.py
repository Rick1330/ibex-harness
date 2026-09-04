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
from dataclasses import dataclass
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


def _assert_hash(manifest: dict[str, Any], key: str, path: Path) -> None:
    actual = _file_sha256(path)
    declared = str(manifest.get(key) or "")
    if declared != actual:
        raise SystemExit(f"gold-set {key} mismatch: manifest={declared[:16]}… actual={actual[:16]}…")


def _assert_conversation_cardinality(
    manifest: dict[str, Any],
    conversations: list[dict[str, Any]],
    expected_rows: list[dict[str, Any]],
) -> set[str]:
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
    return conv_ids


def _assert_cassette_integrity(
    manifest: dict[str, Any],
    cassettes: dict[str, dict[str, Any]],
    conv_ids: set[str],
) -> None:
    _assert_hash(manifest, "cassettes_sha256", GOLD_DIR / _CASSETTES_NAME)
    declared_count = int(manifest.get("conversation_count") or 0)
    cassette_count = int(manifest.get("cassette_count") or 0)
    if len(cassettes) != cassette_count or cassette_count != declared_count:
        raise SystemExit(
            f"cassette cardinality mismatch: declared={cassette_count} "
            f"loaded={len(cassettes)} conversations={declared_count}"
        )
    if set(cassettes) != conv_ids:
        raise SystemExit("conversation_id set mismatch between conversations and cassettes")


def _assert_gold_integrity(
    manifest: dict[str, Any],
    conversations: list[dict[str, Any]],
    expected_rows: list[dict[str, Any]],
    *,
    cassettes: dict[str, dict[str, Any]] | None,
) -> None:
    _assert_hash(manifest, "conversations_sha256", GOLD_DIR / _CONVERSATIONS_NAME)
    _assert_hash(manifest, "expected_memories_sha256", GOLD_DIR / _EXPECTED_NAME)
    conv_ids = _assert_conversation_cardinality(manifest, conversations, expected_rows)
    if cassettes is not None:
        _assert_cassette_integrity(manifest, cassettes, conv_ids)


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


_CASSETTE_MODES = frozenset({"cassette", "smoke", "fast"})
_LIVE_MODES = frozenset({"live", "record", "full", "vllm"})


@dataclass(frozen=True, slots=True)
class _EvalCtx:
    mode: str
    provider: str
    cassettes: dict[str, dict[str, Any]]


def _live_provider_name(mode: str, provider: str) -> str:
    if mode == "vllm" or provider == "vllm":
        return "vllm"
    return "openai"


def _predict_for_mode(
    ctx: _EvalCtx,
    cid: str,
    turns: list[TurnPayload],
) -> tuple[dict[int, list[dict[str, Any]]], str, str | None]:
    if ctx.mode in _CASSETTE_MODES:
        by_turn, model = _predict_cassette(cid, ctx.cassettes)
        return by_turn, model, None
    if ctx.mode in _LIVE_MODES:
        pname = _live_provider_name(ctx.mode, ctx.provider)
        by_turn, model = _predict_live(turns, provider_name=pname)
        return by_turn, model, pname
    raise SystemExit(f"unknown mode: {ctx.mode}")


@dataclass(slots=True)
class _RecordBuf:
    mode: str
    rows: list[dict[str, Any]]


def _maybe_record_cassette(
    buf: _RecordBuf,
    pname: str | None,
    cid: str,
    model_used: str,
    by_turn: dict[int, list[dict[str, Any]]],
) -> None:
    if buf.mode != "record" or pname != "openai":
        return
    batch_payload = {
        "turns": [
            {"turn_index": ti, "memories": by_turn.get(ti, [])} for ti in sorted(by_turn)
        ]
    }
    buf.rows.append(
        {
            "conversation_id": cid,
            "model": model_used,
            "raw_json": json.dumps(batch_payload, separators=(",", ":")),
        }
    )


def _score_expected_rows(
    expected_rows: list[dict[str, Any]],
    by_turn: dict[int, list[dict[str, Any]]],
    turn_scores: list[Any],
) -> None:
    for row in expected_rows:
        ti = int(row["turn_index"])
        predicted = by_turn.get(ti, [])
        expected = list(row["expected"])
        kinds = list(row.get("temporal_kinds") or ["indefinite"] * len(expected))
        turn_scores.append(score_turn(predicted, expected, temporal_kinds=kinds))


def _score_conversations(
    conversations: list[dict[str, Any]],
    expected_by_conv: dict[str, list[dict[str, Any]]],
    ctx: _EvalCtx,
) -> tuple[list[Any], str, list[dict[str, Any]]]:
    turn_scores: list[Any] = []
    model_used = "unknown"
    buf = _RecordBuf(mode=ctx.mode, rows=[])

    for conv in conversations:
        cid = str(conv["conversation_id"])
        turns = [TurnPayload.model_validate(t) for t in conv["turns"]]
        by_turn, model_used, pname = _predict_for_mode(ctx, cid, turns)
        _maybe_record_cassette(buf, pname, cid, model_used, by_turn)
        _score_expected_rows(expected_by_conv[cid], by_turn, turn_scores)

    return turn_scores, model_used, buf.rows


@dataclass(frozen=True, slots=True)
class _ReportMeta:
    mode: str
    provider: str
    model_used: str
    conversation_count: int


def _build_report(meta: _ReportMeta, metrics: dict[str, float]) -> dict[str, Any]:
    enforcement = "manual" if meta.provider == "vllm" or meta.mode == "vllm" else "ci"
    provider = "vllm" if meta.provider == "vllm" or meta.mode == "vllm" else "openai"
    notes = (
        "OpenAI cassette/CI metrics are CI-enforced. "
        "vLLM metrics are manual-only (no GPU CI runner; ADR-0066)."
        if enforcement == "ci"
        else "vLLM result is manual / not CI-enforced (ADR-0066 path a)."
    )
    return {
        "benchmark": "extraction_quality",
        "gold_set": "v1",
        "mode": meta.mode,
        "provider": provider,
        "model": meta.model_used,
        "enforcement": enforcement,
        "conversation_count": meta.conversation_count,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prompt_sha256": _prompt_sha256(),
        "metrics": metrics,
        "gated_metrics": gated_metric_names(),
        "notes": notes,
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

    ctx = _EvalCtx(mode=mode, provider=provider, cassettes=cassettes)
    turn_scores, model_used, recorded = _score_conversations(
        conversations,
        expected_by_conv,
        ctx,
    )
    metrics = aggregate_scores(turn_scores)
    report = _build_report(
        _ReportMeta(
            mode=mode,
            provider=provider,
            model_used=model_used,
            conversation_count=len(conversations),
        ),
        metrics,
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
