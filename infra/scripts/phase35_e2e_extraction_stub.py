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


def _turn_indexes(user_content: str) -> list[int]:
    found = [int(m.group(1)) for m in _TURN_RE.finditer(user_content)]
    if found:
        return sorted(set(found))
    return [0]


def _memory_content(marker: str) -> str:
    # Presidio-clean (no digit-dash / hex patterns). Exact string used for inject/search
    # so stub TEI vectors match.
    return f"ibex phase three five learning loop durable preference marker {marker}"


def _batch_payload(user_content: str, marker: str) -> dict[str, Any]:
    content = _memory_content(marker)
    turns = []
    for idx in _turn_indexes(user_content):
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


def _completion_body(user_content: str, marker: str, model: str) -> dict[str, Any]:
    payload = json.dumps(_batch_payload(user_content, marker))
    return {
        "id": "chatcmpl-p35-stub",
        "object": "chat.completion",
        "model": model,
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


def _model_name(body: object) -> str:
    if isinstance(body, dict) and body.get("model"):
        return str(body["model"])
    return "gpt-4o-mini"


def _parse_json_body(raw: bytes) -> object | None:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


class Handler(BaseHTTPRequestHandler):
    marker: str = _DEFAULT_MARKER

    # Match BaseHTTPRequestHandler.log_message arity exactly (Codacy override check).
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
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
        self._json(200, _completion_body(_user_content(body), self.marker, _model_name(body)))


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
    # Loopback-only e2e stub; HTTPS not required for process-managed CI.  # NOSONAR
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    # NOSONAR python:S5332 — intentional plaintext HTTP for local e2e stub
    print(f"phase35 extraction stub on http://{args.host}:{args.port} marker={args.marker}")
    server.serve_forever()


if __name__ == "__main__":
    main()
