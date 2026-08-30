#!/usr/bin/env python3
"""Minimal TEI sidecar shim for Phase 3 memory e2e (1024-d stub vectors only).

Not production inference — satisfies embedder gpu profile geometry for local/CI gates.
"""

from __future__ import annotations

import argparse
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.backends.stub import StubBackend

_MODEL_ID = "BAAI/bge-m3"
_DIMENSIONS = 1024
_MAX_BATCH_TEXTS = 64
_MAX_TEXT_BYTES = 32 * 1024
_STUB = StubBackend.for_profile("gpu")  # type: ignore[arg-type]

app = FastAPI()


def _invalid_inputs(message: str) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": message})


def _parse_json_object(body: Any) -> dict[str, Any] | JSONResponse:
    if not isinstance(body, dict):
        return _invalid_inputs("request body must be a JSON object")
    return body


def _parse_embed_texts(inputs: Any) -> list[str] | JSONResponse:
    if not isinstance(inputs, list) or not inputs:
        return _invalid_inputs("inputs must be a non-empty list")
    if len(inputs) > _MAX_BATCH_TEXTS:
        return _invalid_inputs(f"inputs batch size exceeds {_MAX_BATCH_TEXTS}")
    texts: list[str] = []
    for index, item in enumerate(inputs):
        if not isinstance(item, str):
            return _invalid_inputs(f"inputs[{index}] must be a string")
        if len(item.encode("utf-8")) > _MAX_TEXT_BYTES:
            return _invalid_inputs(f"inputs[{index}] exceeds {_MAX_TEXT_BYTES} bytes")
        texts.append(item)
    return texts


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/info")
async def info() -> dict[str, object]:
    return {"model_id": _MODEL_ID, "dim": _DIMENSIONS}


@app.post("/embed")
async def embed(request: Request) -> JSONResponse:
    try:
        body: Any = await request.json()
    except Exception:
        return _invalid_inputs("request body must be JSON")
    parsed = _parse_json_object(body)
    if isinstance(parsed, JSONResponse):
        return parsed
    texts = _parse_embed_texts(parsed.get("inputs"))
    if isinstance(texts, JSONResponse):
        return texts
    vectors = await _STUB.embed(texts)
    return JSONResponse(content=vectors.tolist())


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 e2e stub TEI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18083)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
