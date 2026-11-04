# golang:1.26.10-alpine3.24 — bumped for GO-2026-6809 (crypto/x509)
FROM golang@sha256:2920bb124f1a2e12a1d39f0cab756ae0068441ee1da7655dec7f5e374944095b AS build
WORKDIR /src
ARG TARGETOS=linux
ARG TARGETARCH=amd64
COPY go.mod go.sum ./
RUN go mod download -x
COPY packages ./packages
COPY services/auth ./services/auth
RUN CGO_ENABLED=0 GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" \
    go build -trimpath -o /out/auth ./services/auth/cmd/auth

FROM alpine@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6
# CVE-2026-14456: openssl 3.5.7 → 3.5.8 (alpine 3.24 image lag vs package index)
RUN apk upgrade --no-cache libcrypto3 libssl3 \
  && adduser -D -H -u 10001 ibex
USER 10001:10001
COPY --from=build /out/auth /usr/local/bin/auth
EXPOSE 8081
ENTRYPOINT ["/usr/local/bin/auth"]
