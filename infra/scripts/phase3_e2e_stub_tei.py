#!/usr/bin/env python3
"""Minimal TEI sidecar shim for Phase 3 memory e2e (1024-d stub vectors only).

Not production inference — satisfies embedder gpu profile geometry for local/CI gates.
"""

from __future__ import annotations

import argparse

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.backends.stub import StubBackend

_MODEL_ID = "BAAI/bge-m3"
_DIMENSIONS = 1024
_STUB = StubBackend.for_profile("gpu")  # type: ignore[arg-type]

app = FastAPI()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/info")
async def info() -> dict[str, object]:
    return {"model_id": _MODEL_ID, "dim": _DIMENSIONS}


@app.post("/embed")
async def embed(request: Request) -> JSONResponse:
    body = await request.json()
    inputs = body.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return JSONResponse(
            status_code=422,
            content={"error": "inputs must be a non-empty list"},
        )
    vectors = await _STUB.embed([str(item) for item in inputs])
    return JSONResponse(content=vectors.tolist())


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 e2e stub TEI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18083)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
