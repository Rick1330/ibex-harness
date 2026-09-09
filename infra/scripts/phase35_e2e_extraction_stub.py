#!/usr/bin/env python3
"""OpenAI-compatible /chat/completions stub for Phase 3.5 learning-loop e2e.

Deterministic BatchExtractionResult JSON — no live OpenAI/vLLM.
Worker points IBEX_WORKER_EXTRACTION_OPENAI_BASE_URL here with provider=openai.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_TURN_RE = re.compile(r'<turn\s+index="(\d+)"', re.IGNORECASE)
_DEFAULT_MARKER = "loop oak pine cedar maple"
_STUB_MODEL = "gpt-4o-mini"
_MAX_TURN_INDEX = 10_000


def _turn_indexes(user_content: str) -> list[int]:
    """Return sanitized turn indexes only (ints); never echo request text."""
    found: list[int] = []
    for match in _TURN_RE.finditer(user_content):
        idx = int(match.group(1))
        if 0 <= idx <= _MAX_TURN_INDEX:
            found.append(idx)
    if found:
        return sorted(set(found))
    return [0]


def _memory_content(marker: str) -> str:
    # Presidio-clean (no digit-dash / hex patterns). Exact string used for inject/search
    # so stub TEI vectors match. Marker is server-configured, not request-reflected.
    return f"ibex phase three five learning loop durable preference marker {marker}"


def _batch_payload(turn_indexes: list[int], marker: str) -> dict[str, Any]:
    content = _memory_content(marker)
    turns = []
    for idx in turn_indexes:
        turns.append(
            {
                "turn_index": idx,
                "memories": [
                    {
                        "content": content,
                        "categories": [{"label": "preference", "confidence": 0.95}],
                        "confidence": 0.95,
                    }
                ],
            }
        )
    return {"turns": turns}


def _completion_body(turn_indexes: list[int], marker: str) -> dict[str, Any]:
    # Fixed model + marker-derived memories only — no request field reflection (S5131).
    payload = json.dumps(_batch_payload(turn_indexes, marker))
    return {
        "id": "chatcmpl-p35-stub",
        "object": "chat.completion",
        "model": _STUB_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": payload},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 24, "total_tokens": 32},
    }


def _user_content(body: object) -> str:
    if not isinstance(body, dict):
        return ""
    messages = body.get("messages")
    if not isinstance(messages, list):
        return ""
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            return str(msg.get("content") or "")
    return ""


def _parse_json_body(raw: bytes) -> object | None:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


class Handler(BaseHTTPRequestHandler):
    marker: str = _DEFAULT_MARKER

    # Silence access/error logs without overriding log_message(format, ...)
    # (avoids Codacy "redefine built-in format" vs override-arity conflict).
    def log_request(self, code: object = "-", size: object = "-") -> None:
        return

    def log_error(self, *_args: object) -> None:
        return

    def _json(self, code: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in {"", "/health", "/v1/health"}:
            self._json(200, {"status": "ok"})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if path not in {"/chat/completions", "/v1/chat/completions"}:
            self._json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        body = _parse_json_body(raw)
        if body is None:
            self._json(400, {"error": "invalid_json"})
            return
        turns = _turn_indexes(_user_content(body))
        self._json(200, _completion_body(turns, self.marker))


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3.5 extraction OpenAI stub")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18091)
    parser.add_argument(
        "--marker",
        default=os.environ.get("IBEX_E2E_P35_MARKER", _DEFAULT_MARKER),
    )
    args = parser.parse_args()
    Handler.marker = args.marker
    # Loopback-only process-managed e2e stub (not a public listener).
    server = ThreadingHTTPServer((args.host, args.port), Handler)  # NOSONAR python:S5332
    listen = f"{args.host}:{args.port}"
    print(f"phase35 extraction stub listening on {listen}")
    server.serve_forever()  # NOSONAR python:S5332


if __name__ == "__main__":
    main()
