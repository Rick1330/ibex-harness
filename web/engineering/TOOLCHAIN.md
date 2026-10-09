# IBEX Harness — Toolchain and Environment Setup

## Source of truth

Tool versions are defined in [`infra/tool-versions.conf`](../../infra/tool-versions.conf). Do not duplicate version numbers in docs or scripts. Run:

```bash
make check-tools
```

The checker compares installed tools with the manifest and prints remediation guidance. It does not silently upgrade tools, lockfiles, `go.mod`, or `go.sum`.

| Tool | Manifest key |
| --- | --- | --- |
| Go | `GO_VERSION` |
| golangci-lint | `GOLANGCI_LINT_VERSION` |
| Buf | `BUF_VERSION` |
| Gitleaks | `GITLEAKS_VERSION` |
| gotestsum | `GOTESTSUM_VERSION` |
| Node.js | `NODE_MAJOR` |
| pnpm | `PNPM_VERSION` |
| Python | `PYTHON_VERSION` |
| uv | `UV_VERSION` |

`go.mod`, `package.json`, `.nvmrc`, and the CI installation blocks remain authoritative for their respective ecosystems. If those files change, update `infra/tool-versions.conf` in the same change.

## Fast path

On a fresh clone:

```bash
make setup
make check-tools
```

For diagnostics without changing anything:

```bash
make setup-check
make env-doctor
```

`make setup` installs frozen dependencies, generates protobuf output, starts development and test dependencies, applies migrations, initializes required object-store buckets, and runs direct readiness probes. It refuses to leave `go.sum` modified.

## Container runtimes and networking

The command surface supports both runtimes:

```bash
IBEX_RUNTIME=docker make compose-dev-up
IBEX_RUNTIME=podman make compose-dev-up
```

`IBEX_RUNTIME=auto` (the default) prefers Docker Compose v2 and falls back to Podman Compose. Podman users may use either `podman compose` or `podman-compose`.

Networking is selected independently:

```bash
IBEX_NETWORK=bridge make compose-dev-up   # default; Docker/Podman bridge network
IBEX_NETWORK=host make compose-dev-up     # restricted sandboxes; committed overlay
```

Host mode has no Compose service DNS and no `host.docker.internal` gateway. The committed overlays under [`infra/compose/overlays/host/`](../../infra/compose/overlays/host/) replace service references with loopback endpoints, remove bridge-only mappings, relocate conflicting listeners, and use direct host ports.

Use `make env-doctor` when the runtime or network behavior is unclear. It reports OS, architecture, shell, selected runtime, network mode, injected `OTEL_*` variables, localhost resolution, and the port map.

## OS installation recipes

### Windows / Git Bash

Install Git for Windows (including Git Bash), Docker Desktop or Podman Desktop, Go, Node 22, Python 3.12, Buf, Gitleaks, and GNU Make. Then run the commands from Git Bash:

```bash
corepack enable
corepack prepare pnpm@9.15.9 --activate
make setup
```

If Corepack rejects stale package-manager signatures, install the pinned pnpm directly:

```bash
npm install --global pnpm@9.15.9
```

### macOS

Install Homebrew packages for Git, Go, Node, Python, Buf, Gitleaks, GNU Make, and either Docker Desktop or Podman. Activate the pinned pnpm with Corepack or npm, then run `make setup`.

### Linux

Install Git, GNU Make, Bash, curl, certificates, the versions listed in `infra/tool-versions.conf`, and one supported container runtime. Install Buf, Gitleaks, golangci-lint, gotestsum, and uv using their official release/package instructions. Verify exact versions with:

```bash
make check-tools
```

Auto-install is intentionally not performed by `make setup`: package managers and privilege boundaries differ across distributions. The setup command detects missing tools and prints the exact remediation category instead of making unreviewed global changes.

## Dependency setup details

The setup path uses:

```bash
pnpm install --frozen-lockfile --ignore-scripts
```

and each checked-in Python service’s existing `*-uv-sync.sh` helper. Protobuf stubs are generated with `buf generate`; generated output remains governed by the repository’s existing ignore rules.

Go module operations are guarded: setup checks that `go.sum` is unchanged after the operation and restores it before failing if a command mutates it. Never use `go mod download all` as an unattended setup step.

## Local stacks and ports

Development defaults:

| Service | Port |
| --- | ---: |
| PostgreSQL | 5432 |
| Redis | 6379 |
| ClickHouse HTTP | 8123 |
| ClickHouse native | 9002 |
| MinIO API | 9100 |
| MinIO console | 9101 |

Test defaults:

| Service | Port |
| --- | ---: |
| PostgreSQL | 5433 |
| Redis | 6380 |
| ClickHouse HTTP | 8124 |
| ClickHouse native | 9000 |

MinIO uses 9100/9101 by default to avoid the ClickHouse native 9000 collision. Override ports through the Compose `.env.example` files rather than editing Compose YAML.

Observability ports are controlled by `infra/compose/observability/.env.example`. In host mode, Tempo owns the OTLP listener ports and the Collector overlay uses relocated receiver ports; service configuration uses `127.0.0.1` rather than Compose DNS.

## Initialization and readiness

After Compose starts:

```bash
make db-migrate
make clickhouse-migrate
make stack-init
```

`stack-init` uses direct PostgreSQL/Redis/ClickHouse/MinIO probes instead of trusting container health status. ClickHouse readiness matches the exact response `Ok.`. Required buckets are idempotently created when an AWS-compatible CLI is available.

## Test telemetry isolation

Sandbox and CI hosts may inject external OpenTelemetry variables. Repository test commands unset `OTEL_EXPORTER_OTLP_*`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, and exporter selectors unless:

```bash
IBEX_ALLOW_EXTERNAL_OTEL=1
```

Use `make env-doctor` to see whether external telemetry variables are present. Do not copy their values into logs, issues, commits, or documentation.

## Troubleshooting

- **No runtime:** install Docker Compose v2 or Podman + Podman Compose, then rerun `make check-tools`.
- **Bridge networking fails:** use `IBEX_NETWORK=host`; inspect `make env-doctor` and the host overlay files.
- **Rootful Podman rejects image names:** repository Compose images are fully qualified with `docker.io/` where applicable.
- **Port already in use:** run `make env-doctor`, change the corresponding `.env.example` value in a local `.env`, and rerun the stack command.
- **Container says unhealthy but direct service works:** run `make stack-init`; host-mode overlays use direct probes because image healthcheck binaries and bridge ports are not portable.
- **Worker receives S3 404:** run `make stack-init` to create `ibex-sessions` and `ibex-exports`.
- **Integration migration locks:** run migration-backed packages serially with `GO_TEST_P=1`; do not run shared-database migration suites concurrently.
- **Web typecheck:** run the web typecheck target after `pnpm install` and protobuf/content generation; typecheck is a required gate even when build/tests pass.

## Canonical checks

```bash
make repo-guards
make lint-docs
make security-scan
make check-tools
make proto-lint
make stack-init
```
