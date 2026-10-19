# Relay service

Deployable evidence relay daemon for the `ibex_core.evidence_outbox` outbox. It claims
pending rows, verifies an authoritative tombstone/version fence, delivers to a
projection sink, and finalizes the row. It is **default-off** and is not certified
for hosted or HA use.

- Status: `implemented-local` (issue [#1002](https://github.com/Rick1330/ibex-harness/issues/1002)); GAP-011 remains open.
- Decision record: [ADR-0085](../../web/content/docs/adr/0085-evidence-relay-daemon-and-session-fence.mdx).

## Source entry points

| Path | Responsibility |
| --- | --- |
| `cmd/relay/main.go` | Process entrypoint (`os.Exit(bootstrap.Run(os.Args[1:]))`). |
| `internal/bootstrap/run.go` | Gate check, runtime construction, loop + HTTP lifecycle. |
| `internal/bootstrap/wire.go` | Role-pinned PostgreSQL pool, ClickHouse pilot sink, fence checker, relay wiring. |
| `internal/bootstrap/loop.go` | Claim/deliver cycle, backoff, stale in-flight recovery. |
| `internal/bootstrap/health.go` | `/health`, `/ready`, `/metrics`. |
| `internal/bootstrap/shutdown.go` | Drain ordering, dependency close. |
| `internal/config/` | Env var parsing, defaults, bounds, fail-closed validation. |
| `internal/fence/` | Authoritative session fence checker over migration `000047`. |

The relay library itself lives in `packages/evidenceoutbox` (`relay.go`); this service
is the process wrapper, fence authority client, and operational surface.

## Behavior

- When `IBEX_RELAY_ENABLED=false` (default) the daemon logs a reason and exits `0` without connecting to anything. Configuration is still validated first, so a missing or invalid `IBEX_ENV` fails closed (exit `1`) before the disabled fast path.
- When enabled it requires both `IBEX_RELAY_POSTGRES_DSN` and `IBEX_RELAY_CLICKHOUSE_DSN`; a missing or unreachable dependency is a fatal startup error (exit `1`).
- Each cycle recovers stale in-flight rows, claims a batch, and for each row: validates redaction class/fence/digest, checks the authoritative session fence, delivers through the fence-aware sink hook, then marks delivered or (on failure) failed/poison.
- Fence `alive` delivers; `tombstoned`, `stale_version`, or `not_found` poisons the row (`ErrTombstonedResource`); a non-`session`/malformed fence poisons without retry (`ErrUnsupportedFenceResource`); database errors stay retryable.
- Shutdown sets draining, cancels the loop, waits for the in-flight batch, then closes the HTTP surface and dependencies. Claims abandoned by an interrupted batch are recovered by the next cycle's stale-recovery window (`IBEX_RELAY_RECOVER_AFTER`) rather than released at shutdown, which would also reset other instances' claims.

## Configuration

| Variable | Default | Bounds | Notes |
| --- | --- | --- | --- |
| `IBEX_RELAY_ENABLED` | `false` | `1/true/yes/on` or `0/false/no/off` | Gate; enabling requires both DSNs. |
| `IBEX_RELAY_POSTGRES_DSN` | — | — | Secret. Pool is role-pinned at connect time. |
| `IBEX_RELAY_CLICKHOUSE_DSN` | — | — | Secret. Projection pilot sink. |
| `IBEX_RELAY_POLL_INTERVAL` | `2s` | `500ms`–`5m` | Idle poll interval. |
| `IBEX_RELAY_BATCH_SIZE` | `32` | `1`–`256` | Rows claimed per cycle. |
| `IBEX_RELAY_MAX_ATTEMPTS` | `8` | `1`–`100` | Attempts before a row is poisoned. |
| `IBEX_RELAY_RECOVER_AFTER` | `60s` | `1s`–`1h` | Stale in-flight recovery age. |
| `IBEX_RELAY_OPERATION_TIMEOUT` | `30s` | `1s`–`5m` | Per-cycle dependency deadline. |
| `IBEX_RELAY_ERROR_BACKOFF` | `5s` | `500ms`–`1m` | Error backoff base (doubles, capped at `1m`). |
| `IBEX_SHUTDOWN_TIMEOUT` | `30s` | — | Shared graceful-shutdown budget. |
| `IBEX_ENV`, `IBEX_SERVICE_NAME`, `IBEX_LOG_LEVEL`, `IBEX_PORT` | — | — | Shared process settings; `IBEX_ENV` is required. |

Secrets are never logged, and error messages do not echo DSNs.

## Identity and prerequisites

The daemon connects as a login role and pins `ibex_evidence_relay` per connection via the
PostgreSQL startup option `-c role=ibex_evidence_relay` (URL and keyword DSN forms are
supported). It asserts `current_user = ibex_evidence_relay` at startup and fails closed
otherwise. Deployment must grant membership of `ibex_evidence_relay` to that login role;
`ibex_evidence_relay` stays `NOLOGIN` and is not granted to `ibex_app`. Migration `000047`
grants it `EXECUTE` only on the session fence helper.

## Metrics

`ibex_relay_batches_total{result}`, `ibex_relay_claimed_total`, `ibex_relay_delivered_total`,
`ibex_relay_retried_total`, `ibex_relay_dead_letter_total`, `ibex_relay_recovered_total`,
`ibex_relay_batch_duration_seconds`, `ibex_relay_delivery_duration_seconds{result}`,
`ibex_relay_fence_check_duration_seconds{outcome}`, and `ibex_process_up`. Labels are
bounded; unknown values collapse to `error`.

## Testing

```sh
# Unit
GOTOOLCHAIN=go1.26.9 go test ./services/relay/...

# Integration (requires PostgreSQL; use -p 1 so migration locks do not collide)
POSTGRES_TEST_DSN=postgres://ibex:ibex@127.0.0.1:5433/ibex_test?sslmode=disable \
  GOTOOLCHAIN=go1.26.9 go test -tags=integration -p 1 ./services/relay/...
```

CI wiring: `go-services` (unit + build), `relay-integration` (PostgreSQL integration),
plus the shared race, lint, coverage, govulncheck, and license jobs.

## Known limitations

- ClickHouse remains a non-production projection pilot (G4-gated); there is no production sink or hosted/HA recovery evidence.
- No relay-level tenant/agent allowlist, request-auth layer, or operator/admin endpoint.
- The fence read, outbox write, and projection are not a single atomic transaction.
- Chat acknowledgement is not response-bound, so durable-before-ack is not yet proven end to end.
- GAP-005 and GAP-011 remain open; see the [gap register](../../web/engineering/architecture-v2/18-gap-register.md).
