# Thin migrate image — compiled /ibex-migrate only (not the API uvicorn image).
FROM golang@sha256:512690a5660563b57d37ecc31129e7f136e831db2aed24a1dbeb8ad7380dc0fa AS build
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
USER ibex
COPY --from=build /out/ibex-migrate /ibex-migrate
ENTRYPOINT ["/ibex-migrate"]
