# Alert routing and severity vocabulary

> Owner: Elshaday Mengesha (@Rick1330)

How an IBEX alert gets from a Prometheus rule to a human or a queue, and where the webhook for each environment comes from.
This document covers the local Compose stack (ADR-0051); production paging-provider integration is a separate operational
gate and is not claimed here.

Files:

| Path | Role |
| --- | --- |
| `alertmanager.yml` | The routing tree and the two webhook receivers. |
| `README.md` | This document: vocabulary, routing table, per-environment webhook. |
| `../alert-receiver/receiver.py` | Local sink used by the delivery test. Records JSONL; not a deployment receiver. |
| `../../compose/observability/docker-compose.alerting-test.yml` | Test-only override that runs Prometheus + Alertmanager against the local sink. |
| `../../scripts/alert-delivery-test.sh` | End-to-end proof that a page and a ticket each reach their webhook. |
| `../../scripts/check-alert-routing.py` | Static gate: every severity in the rule tree has a route. |

---

## 1. Severity vocabulary

The rule tree mixes two vocabularies: `p1|p2|p3` (the older phase-2.5 rules) and `page|ticket` (the platform backup and
worker rules). Two vocabularies plus one routing tree is how alerts get dropped, so the decision is:

**Primary vocabulary: `page` and `ticket`.**

| Severity | Meaning | Destination | Wake a human? |
| --- | --- | --- | --- |
| `page` | Service or data integrity is failing now | `ibex-page` webhook (`/alerts/page`) | Yes |
| `ticket` | Work that must be picked up, but nothing is burning | `ibex-digest` webhook (`/alerts/digest`) | No |

**Legacy values stay accepted by the route matchers, not by new rules.** The matchers read
`severity=~"p1|page"` and `severity=~"p2|p3|ticket"`, so a rule written before the vocabulary decision still lands on
the right channel. Mapping used by the matchers:

| Legacy | Primary | Channel |
| --- | --- | --- |
| `p1` | `page` | `/alerts/page` |
| `p2` | `ticket` | `/alerts/digest` |
| `p3` | `ticket` | `/alerts/digest` |

Rules are being migrated incrementally. Today (verified by `python3 infra/scripts/check-alert-routing.py`): 4 rules use
`p1`, 3 use `p2`, 1 uses `p3`, and the 3 newest use `page`/`ticket`. New or edited rules **must** use `page` or
`ticket`; the legacy aliases exist only so the un-migrated rules cannot fall through.

The gate fails when a rule carries a severity that no route matches, when a route names a receiver that is not defined,
when a receiver has no `webhook_configs`, when an alert has no severity label, when a direct child of the root route has
no severity matcher, when a route selects on a label other than `severity` as well as a severity, or when `local-null`
reappears.

Two rules keep the gate honest:

- **Severity is read only from the `labels:` block.** A `severity:` line under `annotations:` is prose: Alertmanager
  never routes on it, so it does not count and the alert is reported as unlabelled.
- **Only a severity matcher makes a severity routed, and only on a route the gate can evaluate in full.** A route that
  selects on other labels (`service=proxy` and nothing else) cannot make a severity look routed, because the gate cannot
  evaluate those labels. Neither can a route that selects on `service=proxy` *as well as* `severity=page`: that route
  may exclude the alert, so the gate fails closed, names the matcher it cannot evaluate, and does not count the
  severity as routed. Such a route is reported instead of being treated as a catch-all.

The gate also self-tests six cases on every run (one positive control, one unrouted severity, one `service=`-only
route, one severity route carrying an extra `service=` matcher, one severity in an annotation, one `..` path that must be
refused with exit 2), so a gate that has stopped failing is caught by the gate itself. It confines `--rules` and
`--config` to the working directory before reading either: a `..` segment, or a path resolving outside that root, is
refused with exit 2; set `IBEX_ALERT_ROUTING_ALLOW_ROOT` to run it against a tree elsewhere.

---

## 2. Routing tree

```text
route (catch-all, receiver ibex-page, group_by [alertname, severity, service], group_wait 30s)
├── severity=~"p1|page"        -> ibex-page    POST /alerts/page    repeat 1h
└── severity=~"p2|p3|ticket"   -> ibex-digest  POST /alerts/digest  repeat 12h
```

| Alert | Severity | Route | Receiver | Webhook path |
| --- | --- | --- | --- | --- |
| `IbexProxyDown` | `p1` | `p1\|page` | `ibex-page` | `/alerts/page` |
| `IbexAuthDown` | `p1` | `p1\|page` | `ibex-page` | `/alerts/page` |
| `IbexProxyHighErrorRatio` | `p1` | `p1\|page` | `ibex-page` | `/alerts/page` |
| `IbexProcessNotUp` | `p1` | `p1\|page` | `ibex-page` | `/alerts/page` |
| `IbexMemoryDown` | `p2` | `p2\|p3\|ticket` | `ibex-digest` | `/alerts/digest` |
| `IbexMemoryAfterCommitFailures` | `p2` | `p2\|p3\|ticket` | `ibex-digest` | `/alerts/digest` |
| `IbexMCPAuditDrops` | `p2` | `p2\|p3\|ticket` | `ibex-digest` | `/alerts/digest` |
| `IbexMemoryEscalationBacklogGrowth` | `p3` | `p2\|p3\|ticket` | `ibex-digest` | `/alerts/digest` |
| `IBEXPostgresBackupStale` | `page` | `p1\|page` | `ibex-page` | `/alerts/page` |
| `IBEXWorkerTaskDeadLettered` | `page` | `p1\|page` | `ibex-page` | `/alerts/page` |
| `IBEXRestoreDrillMissing` | `ticket` | `p2\|p3\|ticket` | `ibex-digest` | `/alerts/digest` |

The failure-mode each alert corresponds to is mapped in
[`engineering/architecture-v2/14-failure-modes-and-readiness.md`](../../../engineering/architecture-v2/14-failure-modes-and-readiness.md).

### The catch-all fails loud

The root route uses `ibex-page`, not a discard receiver. An alert whose labels match no child route — a new severity, a
typo in a label, an un-migrated rule — is delivered to the page webhook. It is noisy on purpose: a page that nobody
expected is cheap, an alert that quietly disappeared is not.

There is no null receiver in this file and `check-alert-routing.py` fails if one reappears. A receiver with no
integration (the old `local-null`) accepts every notification and discards it, and because Alertmanager reports the
delivery as successful, nothing downstream can detect the loss.

---

## 3. Configuring the webhook per environment

The repository contains no webhook URL, token, or credential. `alertmanager.yml` ships with the in-network placeholder
base `http://alert-receiver:8080` — the service name the receiver is expected to have, deliberately not a production
address. Every environment renders its own copy and mounts it with `--config.file`.

### Why rendering, not environment expansion

The pinned image (`docker.io/prom/alertmanager@sha256:e13b6ed5cb929eeaee733479dce55e10eb3bc2e9c4586c705a4e8da41e5eacf5`)
is **Alertmanager 0.27.0**, which has no `--config.expand-env` flag and no `ALERTMANAGER_CONFIG_EXPAND_ENV` variable.
Verified against the image:

```bash
AM_IMAGE=docker.io/prom/alertmanager@sha256:e13b6ed5cb929eeaee733479dce55e10eb3bc2e9c4586c705a4e8da41e5eacf5
podman run --rm --entrypoint /bin/alertmanager "$AM_IMAGE" \
  --config.file=/etc/alertmanager/alertmanager.yml --config.expand-env
# alertmanager: error: unknown long flag '--config.expand-env', try --help
```

A literal `${IBEX_ALERT_RECEIVER_BASE}` in the URL is also rejected at load time
(`amtool check-config`: `FAILED: unsupported scheme "" for URL`). So the placeholder must stay a syntactically valid
URL and the substitution happens when the file is rendered, before Alertmanager reads it.

### Render step

```bash
# ALERT_RECEIVER_BASE is scheme://host[:port] with no path; the /alerts/page and
# /alerts/digest paths stay as they are. Assign it on its own line first: in a
# command-prefix assignment (`VAR=... sed "s|...|${VAR}|g"`) the shell expands
# ${VAR} before the assignment applies, so the substitution would be empty.
ALERT_RECEIVER_BASE="https://<receiver-host>"
sed "s|http://alert-receiver:8080|${ALERT_RECEIVER_BASE}|g" \
  infra/monitoring/alertmanager/alertmanager.yml > /run/alertmanager/alertmanager.yml

amtool check-config /run/alertmanager/alertmanager.yml   # must exit 0 before the restart
```

The mount is read-only and the rendered file lives outside the repository:

```yaml
volumes:
  - /run/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
```

Rules for the receiver URL:

- The base is deployment configuration: environment variable, ConfigMap, or secret store — never a committed file.
- If the receiver needs authentication, put it in the render step's secret input and use Alertmanager's
  `http_config.authorization` (`credentials_file`) or `bearer_token_file`; do not inline a token in the URL.
- Changing the base requires the same `amtool check-config` gate; the delivery test exercises the same render path
  (`infra/scripts/alert-delivery-test.sh`), so the mechanism itself is tested.

### Local test

```bash
make alert-delivery-test   # renders the config and rules, proves both paths, tears itself down
```

The test starts the sink as the compose service `alert-receiver` on the test network, with **no published host port**,
and renders a random `run_nonce` label into a temporary copy of the probe rules
(`infra/monitoring/prometheus/rules/test/ibex-alert-delivery-probe.yml`, committed file unchanged). A delivery counts
only when the sink record carries both the expected `alertname` and that run's nonce **and no other path carries
that nonce** — a run that fans one alert out to a second receiver is a routing bug, not a pass.

Exposure, stated precisely — the sink is not isolated by its bind address:

| Surface | What it actually gives you |
| --- | --- |
| Rootless podman, no published port | The container network is unreachable from the host (verified: connection refused/timeout). |
| Rootful Docker, no published port | Not equivalent. `IBEX_ALERT_SINK_BIND=0.0.0.0` listens on every address inside the container's netns, so the container IP can be reachable from the host or a routed peer. The absent published port is not by itself the control. |
| Per-run nonce | Defeats a peer that can reach only the sink: a record without this run's label is refused. |
| Prometheus `/api/v1/rules` | The residual: the nonce **is** a rule label, so a peer that can also read the test Prometheus API can read it and forge a matching record. Not fixed; the test Prometheus is loopback-only and lives only for the run. |

Why the sink is a container rather than a host listener:

| Attempted bind | Result |
| --- | --- |
| Rootless bridge gateway (`10.88.0.1`, the `host-gateway`) | `bind: [Errno 99] Cannot assign requested address` — the address belongs to the rootless netns, not the host |
| Host loopback (`127.0.0.1`) | Not reachable from the container: `curl http://host.docker.internal:18099/healthz` is refused |
| Host `0.0.0.0` (the previous design) | Reachable from the container **and** from any peer that can route to the host's non-loopback address (a LAN peer, unless a firewall blocks it), which is why the sink moved into the compose network |

Reproduce the first two rows:

```bash
# 1. The rootless gateway is not a host address, so the host cannot bind it.
python3 -c 'import socket; s=socket.socket(); s.bind(("10.88.0.1",18099))'
# -> OSError: [Errno 99] Cannot assign requested address

# 2. Start a probe listener on loopback, then ask a container to reach it.
python3 -m http.server 18099 --bind 127.0.0.1 &
podman run --rm --label ibex.probe=1 --network podman \
  --add-host host.docker.internal:host-gateway \
  docker.io/library/python@sha256:da54eb86849fe19be7584d8b3f291fcf0c53c196760ab3d70dc6382f681ef9c0 \
  python3 -c 'import urllib.request; urllib.request.urlopen("http://host.docker.internal:18099", timeout=3)'
# -> ConnectionRefusedError with --bind 127.0.0.1; HTTP 200 with --bind 0.0.0.0
```

---

## 4. Verification

| Check | Command | What it proves |
| --- | --- | --- |
| Static routing | `python3 infra/scripts/check-alert-routing.py` | Every rule severity has a route; no `local-null`; every receiver is a webhook. Runs in `make repo-guards`. |
| Config validity | `amtool check-config alertmanager.yml` (host, or the pinned image) | The tree parses and every receiver is well formed. |
| Live delivery | `make alert-delivery-test` | A `page` probe and a `ticket` probe each reached their own webhook path, recorded in a JSONL sink with the run's nonce label. Operator-run, not a CI gate: no CI job starts containers. |
| Served config | `make observability-smoke` | The running Alertmanager serves a config that can deliver: no `local-null`, and `ibex-page` and `ibex-digest` each carry their own `webhook_configs` (checked per receiver, so one receiver's webhook cannot satisfy the check for another). This is the configuration shape, not a delivery — the base stack has no `alert-receiver` service, so the host does not resolve the webhook URL. |

---

## 5. What this does **not** claim

- No page reached a human. The delivery test proves the webhook transport and the routing decision, not an on-call
  acknowledgement, an escalation policy, or a paging provider.
- `infra/helm/observability/` does not ship Alertmanager, so the Helm installation has no alert routing at all yet.
- There is no production receiver, no deduplication policy beyond `group_by`, no silence workflow, and no measured
  notification latency SLO.
- The sink has **no authentication**. It is not reachable from the host under rootless podman (no published port), but
  that is not isolation on its own: under rootful Docker the container IP can be reachable, and the per-run nonce is a
  Prometheus rule label, so a peer that can also read the test Prometheus `/api/v1/rules` can read the nonce and forge a
  matching record. Keep the sink on loopback or on a private network with no published port, and do not expose it outside
  a test run.
- The delivery test proves the routing decision and the webhook transport for one synthetic probe per severity. It does
  not exercise grouping, inhibition, silences, or a real paging provider.
