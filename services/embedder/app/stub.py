"""Backward-compat shim — import from app.backends.stub directly."""

from app.backends.stub import StubBackend

__all__ = ["StubBackend"]
