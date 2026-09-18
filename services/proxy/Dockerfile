FROM golang@sha256:512690a5660563b57d37ecc31129e7f136e831db2aed24a1dbeb8ad7380dc0fa AS build
WORKDIR /src
ARG TARGETOS=linux
ARG TARGETARCH=amd64
COPY go.mod go.sum ./
RUN go mod download -x
COPY packages ./packages
COPY services/proxy ./services/proxy
RUN CGO_ENABLED=0 GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" \
    go build -trimpath -o /out/proxy ./services/proxy/cmd/proxy

FROM alpine@sha256:5b02b42e375f7426f8d65c3af331ca05d9878f9989230354504e0b9dfd431f60
# CVE-2026-14456: openssl 3.5.7 → 3.5.8 (alpine 3.24 image lag vs package index)
RUN apk upgrade --no-cache libcrypto3 libssl3 \
  && adduser -D -H -u 10001 ibex
USER ibex
COPY --from=build /out/proxy /usr/local/bin/proxy
EXPOSE 8082
ENTRYPOINT ["/usr/local/bin/proxy"]
