#!/usr/bin/env python3
"""Minimal Alertmanager webhook receiver for local delivery tests (P0-19 / W6.2).

Alertmanager 0.27.0 (the pinned image) sends each notification batch as
``POST /alerts`` with a JSON body. This receiver appends one JSON object per
request to ``$IBEX_ALERT_SINK_OUT`` so a test can prove that an alert reached a
real webhook instead of being dropped by a null receiver.

Endpoints
---------
POST /alerts*   Append ``{"path", "received_at", "status", "receiver", "alerts"}``
                to the sink. Every path below /alerts is accepted, so a routing
                tree can give each receiver its own endpoint (/alerts/page,
                /alerts/digest, ...) and the sink still records which one fired.
                Each alert entry carries ``alertname``, ``severity``,
                ``run_nonce`` and ``status`` so a test can require a per-run
                nonce that a peer cannot guess.
GET  /healthz   200 ``{"status": "ok", "records": ..., "bytes": ...}``.

Exposure
--------
This is a test sink, not a delivery service: it has no authentication, and
adding an API token would not make it safe to publish.

The delivery test runs it as a compose service with no published host port.
Under rootless podman that makes the socket unreachable from the host (verified:
connection refused/timeout). The bind address is not what protects it:
``IBEX_ALERT_SINK_BIND=0.0.0.0`` listens on every address inside the container's
network namespace, and under **rootful Docker** the container IP can be reachable
from the host or a routed peer.

Forgery is blocked at the assertion, not at the socket: the delivery test renders
a per-run ``run_nonce`` label into its probe rules and refuses a record that does
not carry it. That defeats a peer which can reach only the sink. It does **not**
defeat a peer that can also read Prometheus ``/api/v1/rules``, because the nonce
is a rule label and that endpoint serves the label to any client of the test
Prometheus port. Run the sink on loopback, or inside a private network with no
published port, and treat the nonce as tamper evidence rather than isolation.

Self-defence
------------
The process never trusts its client:

* a request body above ``MAX_BODY_BYTES`` is rejected with 413 and never read;
* the total number of records and bytes written in one run is capped; past the
  cap the receiver answers 429 and writes nothing (a peer cannot fill the disk);
* every request has a socket timeout, so a half-sent body cannot pin a thread;
* every parse and type error is answered with 400, never raised;
* records are written under a lock, one ``os.write`` per record, so concurrent
  POSTs cannot interleave a line.

Configuration
-------------
IBEX_ALERT_SINK_OUT          Required. Path of the JSONL sink file (append mode).
IBEX_ALERT_SINK_PORT         Default 18099.
IBEX_ALERT_SINK_BIND         Default 127.0.0.1. Set 0.0.0.0 **only** inside a
                             container network with no published port; see
                             Exposure for why that alone is not isolation.
IBEX_ALERT_SINK_READY_FILE   Optional. Written once the listener is bound, so a
                             start-up script can wait on the socket, not a guess.
IBEX_ALERT_SINK_MAX_RECORDS  Default 200. Hard cap on records per run.
IBEX_ALERT_SINK_MAX_BYTES    Default 8388608. Hard cap on bytes per run.
IBEX_ALERT_SINK_TIMEOUT      Default 10 seconds per request.

Standard library only: it runs on a bare host and inside the pinned python image
without any extra package.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

MAX_BODY_BYTES = 1 << 20  # 1 MiB: Alertmanager batches are far smaller.
DEFAULT_MAX_RECORDS = 200
DEFAULT_MAX_BYTES = 8 << 20
DEFAULT_TIMEOUT_SECONDS = 10
ALERTS_PATH = "/alerts"
HEALTH_PATH = "/healthz"
# Labels copied into the sink record. Deliberately a fixed allowlist: the sink is
# a diagnostic, not a copy of every label an integration might attach.
LABEL_KEYS = ("alertname", "severity", "run_nonce")


def _is_alerts_path(path: str) -> bool:
    return path == ALERTS_PATH or path.startswith(ALERTS_PATH + "/")


def _optional_str(value: Any) -> str | None:
    """Return ``value`` when it is a string, else ``None`` (the record shape)."""
    return value if isinstance(value, str) else None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise SystemExit(f"receiver: {name} must be an integer, got {raw!r}") from None
    if value <= 0:
        raise SystemExit(f"receiver: {name} must be positive, got {value}")
    return value


def _sink_path() -> Path:
    raw = os.environ.get("IBEX_ALERT_SINK_OUT", "").strip()
    if not raw:
        raise SystemExit("receiver: IBEX_ALERT_SINK_OUT is required")
    path = Path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Fail at startup rather than on the first delivery: create or open the sink
    # now and close it, so an unwritable path is reported here.
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o666)
    os.close(descriptor)
    return path


class Sink:
    """Append-only JSONL sink with hard record and byte caps."""

    def __init__(self, path: Path, max_records: int, max_bytes: int) -> None:
        self.path = path
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.records = 0
        self.bytes = 0
        self._lock = threading.Lock()

    def append(self, record: dict[str, Any]) -> str | None:
        """Append one record. Returns None on success, else why it was refused."""
        line = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
        with self._lock:
            if self.records >= self.max_records:
                return f"record cap reached ({self.max_records}); refusing further deliveries"
            if self.bytes + len(line) > self.max_bytes:
                return f"byte cap reached ({self.max_bytes}); refusing further deliveries"
            try:
                # 0644 because a rootful Docker bind mount is read by the host user
                # that owns the directory; the file carries no secret.
                fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
            except OSError as exc:
                return f"sink open failed: {exc.strerror}"
            try:
                # One write per record under the lock: concurrent POSTs cannot
                # interleave, and a reader never sees a half-written line.
                view = memoryview(line)
                while view:
                    view = view[os.write(fd, view) :]
                os.fsync(fd)
            except OSError as exc:
                return f"sink write failed: {exc.strerror}"
            finally:
                os.close(fd)
            self.records += 1
            self.bytes += len(line)
        return None


def _alert_summary(alert: dict[str, Any]) -> dict[str, Any]:
    labels = alert.get("labels")
    labels = labels if isinstance(labels, dict) else {}
    summary: dict[str, Any] = {}
    for key in LABEL_KEYS:
        value = labels.get(key)
        summary[key] = value if isinstance(value, str) else None
    status = alert.get("status")
    summary["status"] = status if isinstance(status, str) else None
    return summary


class AlertSinkHandler(BaseHTTPRequestHandler):
    server_version = "ibex-alert-receiver/2"
    # One request per connection: a keep-alive peer cannot hold a thread open.
    protocol_version = "HTTP/1.0"
    timeout = DEFAULT_TIMEOUT_SECONDS

    def _respond(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            # The client is gone. The record was already written or rejected.
            self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.split("?", 1)[0] != HEALTH_PATH:
            self._respond(404, {"error": "not found"})
            return
        sink = self.server.sink  # type: ignore[attr-defined]
        self._respond(
            200,
            {
                "status": "ok",
                "records": sink.records,
                "bytes": sink.bytes,
                "max_records": sink.max_records,
                "max_bytes": sink.max_bytes,
            },
        )

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            self._handle_post()
        except Exception as exc:  # noqa: BLE001 - a bad request must not kill the thread
            sys.stderr.write(
                "receiver: rejected request after %s (%s)\n" % (type(exc).__name__, exc)
            )
            self.close_connection = True
            self._respond(400, {"error": "request rejected"})

    def _handle_post(self) -> None:
        path = self.path.split("?", 1)[0]
        if not _is_alerts_path(path):
            self._respond(404, {"error": "not found"})
            return
        raw = self._read_body()
        if raw is None:
            return
        payload = self._parse_payload(raw)
        if payload is None:
            return
        self._record(path, payload)

    def _read_body(self) -> bytes | None:
        """Read the declared body, or answer and return ``None`` when unusable."""
        if self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            self._respond(411, {"error": "Transfer-Encoding is unsupported; send Content-Length"})
            return None
        raw_length = self.headers.get("Content-Length", "")
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            self._respond(400, {"error": "missing or invalid Content-Length"})
            return None
        if length <= 0:
            self._respond(400, {"error": "empty body"})
            return None
        if length > MAX_BODY_BYTES:
            # Never read the body: drop the connection instead of buffering it.
            self.close_connection = True
            self._respond(413, {"error": f"body exceeds {MAX_BODY_BYTES} bytes"})
            return None
        return self._read_exact(length)

    def _read_exact(self, length: int) -> bytes | None:
        """Read exactly ``length`` bytes, or answer and return ``None``."""
        try:
            raw = self.rfile.read(length)
        except OSError:
            self.close_connection = True
            self._respond(408, {"error": "body read timed out"})
            return None
        if len(raw) != length:
            self.close_connection = True
            self._respond(400, {"error": "short body"})
            return None
        return raw

    def _parse_payload(self, raw: bytes) -> dict[str, Any] | None:
        """Validate the JSON body, or answer and return ``None`` when it is unusable."""
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001 - decode errors and JSON errors are both 400s
            self._respond(400, {"error": "invalid json"})
            return None
        if not isinstance(payload, dict):
            self._respond(400, {"error": "body must be a json object"})
            return None
        alerts = payload.get("alerts")
        if not isinstance(alerts, list) or not alerts:
            self._respond(400, {"error": "body must carry a non-empty alerts array"})
            return None
        return payload

    def _record(self, path: str, payload: dict[str, Any]) -> None:
        """Append the record under the caps, then answer 200 or 429."""
        record = {
            "path": path,
            "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": _optional_str(payload.get("status")),
            "receiver": _optional_str(payload.get("receiver")),
            "alerts": [
                _alert_summary(alert) for alert in payload["alerts"] if isinstance(alert, dict)
            ],
        }
        refusal = self.server.sink.append(record)  # type: ignore[attr-defined]
        if refusal is not None:
            # Cap hit: refuse, do not write. 429 tells the sender to stop, and an
            # operator reading the Alertmanager log sees the refusal.
            self._respond(429, {"error": refusal})
            return
        self._respond(200, {"status": "recorded", "alerts": len(record["alerts"])})

    def log_message(self, fmt: str, *args) -> None:
        # No payloads, no headers: only method/path/status reach stderr.
        sys.stderr.write("receiver: %s\n" % (fmt % args))


class AlertSinkServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 16

    def __init__(self, address: tuple[str, int], sink: Sink) -> None:
        super().__init__(address, AlertSinkHandler)
        self.sink = sink


def main() -> int:
    sink = Sink(
        _sink_path(),
        _env_int("IBEX_ALERT_SINK_MAX_RECORDS", DEFAULT_MAX_RECORDS),
        _env_int("IBEX_ALERT_SINK_MAX_BYTES", DEFAULT_MAX_BYTES),
    )
    AlertSinkHandler.timeout = _env_int("IBEX_ALERT_SINK_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
    bind = os.environ.get("IBEX_ALERT_SINK_BIND", "").strip() or "127.0.0.1"
    port = _env_int("IBEX_ALERT_SINK_PORT", 18099)
    server = AlertSinkServer((bind, port), sink)
    ready_file = os.environ.get("IBEX_ALERT_SINK_READY_FILE", "").strip()
    if ready_file:
        # Written only after the socket is bound: a waiter that sees this file
        # never races a not-yet-listening server.
        Path(ready_file).write_text(f"{bind}:{port}\n", encoding="utf-8")
    sys.stderr.write(
        "receiver: listening on http://%s:%d (sink %s, caps %d records / %d bytes)\n"
        % (bind, port, sink.path, sink.max_records, sink.max_bytes)
    )
    try:
        # Cleartext HTTP is deliberate and is not a service exposure: this is the
        # local delivery-test sink described under "Exposure" above. It publishes
        # no host port, carries no credential, and its records are proved by a
        # per-run nonce rather than by the transport. TLS would need a
        # certificate the test Alertmanager does not have and would change what
        # the delivery test proves, so the sink stays plain HTTP by design.
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
