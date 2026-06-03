FROM golang:1.25-alpine3.20 AS build
WORKDIR /src
COPY go.mod go.sum ./
COPY services/proxy ./services/proxy
RUN go build -o /out/proxy ./services/proxy/cmd/proxy

FROM alpine:3.20
RUN adduser -D -H -u 10001 ibex
USER ibex
COPY --from=build /out/proxy /usr/local/bin/proxy
EXPOSE 8082
ENTRYPOINT ["/usr/local/bin/proxy"]
