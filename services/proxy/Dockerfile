FROM golang:1.21.13-alpine3.20 AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN go build -o /out/proxy ./cmd/proxy

FROM alpine:3.20
RUN adduser -D -H -u 10001 ibex
USER ibex
COPY --from=build /out/proxy /usr/local/bin/proxy
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/proxy"]
