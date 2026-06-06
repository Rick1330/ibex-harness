FROM golang:1.25-alpine3.20 AS build
WORKDIR /src
COPY go.mod go.sum ./
COPY services/proxy ./services/proxy
RUN go build -o /out/proxy ./services/proxy/cmd/proxy

FROM alpine:3.23@sha256:5b10f432ef3da1b8d4c7eb6c487f2f5a8f096bc91145e68878dd4a5019afde11
RUN adduser -D -H -u 10001 ibex
USER ibex
COPY --from=build /out/proxy /usr/local/bin/proxy
EXPOSE 8082
ENTRYPOINT ["/usr/local/bin/proxy"]
