# Local observability stack (ADR-0051)

The Compose profile provides loopback-only Prometheus, Grafana, Tempo, Loki, OpenTelemetry Collector, and Alertmanager for local verification. It is not production HA or long-retention evidence.

## Quick start

```bash
make observability-up
# Start the application stack separately, then generate deterministic traffic:
make observability-live-verify
# or, when the stack is already running:
make observability-traffic
make observability-smoke
```

`make verify-phase25` performs checks without generating live traffic unless explicitly opted in:

```bash
IBEX_VERIFY_PHASE25_E2E=1 make verify-phase25
```

Host services must already be running for the traffic path to produce application series. Do not claim a populated dashboard from `verify-phase25` without the opt-in and a running stack.

| UI | Default URL |
| --- | --- |
| Grafana | <http://127.0.0.1:3000> (anonymous Viewer) |
| Prometheus | <http://127.0.0.1:19090> |
| Tempo | <http://127.0.0.1:3200> |
| Loki | <http://127.0.0.1:3100> |
| Alertmanager | <http://127.0.0.1:9093> |
| OTLP gRPC | `127.0.0.1:4317` |

Configuration lives in [`infra/monitoring/`](../../monitoring/). Never commit generated bearer files or expose this stack beyond loopback without an explicit security review.
