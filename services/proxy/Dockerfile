# golang:1.26.11-alpine3.24 — bumped for GO-2026-6859 (net/http); 1.26.10 for GO-2026-6809 (crypto/x509)
FROM golang@sha256:ae52b5bc6ed045a9ed26ab03dc19327a802a9cc9aa8b27ed57f5c6b60579b0bb AS build
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
# CVE-2026-85091: zlib 1.3.2-r0 → 1.3.2-r1
# CVE-2026-107891: musl and musl-utils 1.2.6-r2 → 1.2.6-r3
RUN apk upgrade --no-cache libcrypto3 libssl3 zlib musl musl-utils \
  && adduser -D -H -u 10001 ibex
USER 10001:10001
COPY --from=build /out/proxy /usr/local/bin/proxy
COPY --from=build /src/infra/provider-capabilities/manifest.v1.json /etc/ibex/provider-capabilities/manifest.v1.json
ENV IBEX_PROVIDER_CAPABILITY_MANIFEST=/etc/ibex/provider-capabilities/manifest.v1.json
EXPOSE 8082
ENTRYPOINT ["/usr/local/bin/proxy"]
