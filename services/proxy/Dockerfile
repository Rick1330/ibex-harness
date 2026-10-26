# golang:1.26.10-alpine3.24 — bumped for GO-2026-6809 (crypto/x509)
FROM golang@sha256:f20d83a83e18dbd2a4714b8ffd4b30b287b6243962dd75608e86abcc63ba4efc AS build
WORKDIR /src
ARG TARGETOS=linux
ARG TARGETARCH=amd64
COPY go.mod go.sum ./
RUN go mod download -x
COPY packages ./packages
COPY services/proxy ./services/proxy
COPY infra/provider-capabilities ./infra/provider-capabilities
RUN CGO_ENABLED=0 GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" \
    go build -trimpath -o /out/proxy ./services/proxy/cmd/proxy

FROM alpine@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6
# CVE-2026-14456: openssl 3.5.7 → 3.5.8 (alpine 3.24 image lag vs package index)
RUN apk upgrade --no-cache libcrypto3 libssl3 \
  && adduser -D -H -u 10001 ibex
USER ibex
COPY --from=build /out/proxy /usr/local/bin/proxy
COPY --from=build /src/infra/provider-capabilities/manifest.v1.json /etc/ibex/provider-capabilities/manifest.v1.json
ENV IBEX_PROVIDER_CAPABILITY_MANIFEST=/etc/ibex/provider-capabilities/manifest.v1.json
EXPOSE 8082
ENTRYPOINT ["/usr/local/bin/proxy"]
