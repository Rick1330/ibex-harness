FROM golang@sha256:457d8584db11412777c4196146b8060fdaabe0b0ba7b62c553d08e07d8c22bd3 AS build
WORKDIR /src
ARG TARGETOS=linux
ARG TARGETARCH=amd64
COPY go.mod go.sum ./
RUN go mod download -x
COPY packages ./packages
COPY services/proxy ./services/proxy
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -trimpath -o /out/proxy ./services/proxy/cmd/proxy

FROM alpine@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b
RUN adduser -D -H -u 10001 ibex
USER ibex
COPY --from=build /out/proxy /usr/local/bin/proxy
EXPOSE 8082
ENTRYPOINT ["/usr/local/bin/proxy"]
