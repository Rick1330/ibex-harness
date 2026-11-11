# Thin migrate image — compiled /ibex-migrate only (not the API uvicorn image).
# golang:1.26.11-alpine3.24 — bumped for GO-2026-6859 (net/http)
FROM golang@sha256:ae52b5bc6ed045a9ed26ab03dc19327a802a9cc9aa8b27ed57f5c6b60579b0bb AS build
WORKDIR /src
ARG TARGETOS=linux
ARG TARGETARCH=amd64
COPY go.mod go.sum ./
RUN go mod download -x
COPY packages ./packages
COPY infra/migrations ./infra/migrations
RUN CGO_ENABLED=0 GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" \
    go build -trimpath -o /out/ibex-migrate ./infra/migrations/postgres/cmd/migrate

FROM alpine@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b
RUN apk upgrade --no-cache libcrypto3 libssl3 \
  && adduser -D -H -u 10001 ibex
USER 10001:10001
COPY --from=build /out/ibex-migrate /ibex-migrate
ENTRYPOINT ["/ibex-migrate"]
