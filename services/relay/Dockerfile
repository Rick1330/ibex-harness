# IBEX Evidence Relay — multi-stage, non-root, static Go binary.
#
# Build:
#   podman build -t ibex-relay:local -f services/relay/Dockerfile .
#   docker build -t ibex-relay:local -f services/relay/Dockerfile .
#
# The daemon is default-off: with IBEX_RELAY_ENABLED=false it validates its
# configuration, logs why it is inert, and exits 0 without connecting to
# anything. Enabling it requires IBEX_RELAY_POSTGRES_DSN and
# IBEX_RELAY_CLICKHOUSE_DSN (services/relay/README.md, ADR-0085).
#
# The runtime image is inert on start by design, so a restart policy turns a
# disabled container into a restart loop: enable the gate before deploying it.
# GAP-011 stays open (no hosted/HA profile enables this daemon).

# golang:1.26.11-alpine3.24 — the same build pin as services/proxy and
# services/auth. The build copies the whole packages tree, which includes the
# generated protobuf stubs (packages/proto/gen/go/…, gitignored): the relay
# reaches ibex.auth.v1 through packages/pgtenant, so `buf generate` must run
# before the image build, exactly as it does for auth and proxy.
FROM golang@sha256:ae52b5bc6ed045a9ed26ab03dc19327a802a9cc9aa8b27ed57f5c6b60579b0bb AS build
WORKDIR /src
ARG TARGETOS=linux
ARG TARGETARCH=amd64
COPY go.mod go.sum ./
RUN go mod download -x
COPY packages ./packages
COPY services/relay ./services/relay
RUN CGO_ENABLED=0 GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" \
    go build -trimpath -o /out/relay ./services/relay/cmd/relay

FROM alpine@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6
# Same base digest as services/proxy, so the same base-image fixes apply
# (CVE-2026-14456 openssl, CVE-2026-85091 zlib, CVE-2026-107891 musl). The image
# scan gate blocks CRITICAL/HIGH, so these are applied here rather than inherited.
RUN apk upgrade --no-cache libcrypto3 libssl3 zlib musl musl-utils \
  && adduser -D -H -u 10001 ibex
USER 10001:10001
COPY --from=build /out/relay /usr/local/bin/relay
EXPOSE 8081
# Liveness only. /ready is the dependency gate (Postgres + ClickHouse) and
# belongs to the deployment, not to the image; /health proves the process is
# serving. The Go siblings carry no HEALTHCHECK because every profile that runs
# them declares one — no profile runs the relay today, so the image carries it.
# Like the Python images (services/context, services/console), Podman 5.7
# defaults to the OCI format, which drops HEALTHCHECK: build with
# `podman build --format docker` to keep it.
#
# Shell form on purpose: the probe resolves IBEX_PORT when the check runs, from
# the same variable and default (8081) the HTTP server binds to
# (services/relay/internal/config/env_config.go). The exec form would freeze the
# port at build time and report a relay on a non-default port as unhealthy.
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- "http://127.0.0.1:${IBEX_PORT:-8081}/health"
ENTRYPOINT ["/usr/local/bin/relay"]
