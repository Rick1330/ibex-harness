FROM golang:1.21.13-alpine3.20 AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN go build -o /out/auth ./cmd/auth

FROM alpine:3.20
RUN adduser -D -H -u 10001 ibex
USER ibex
COPY --from=build /out/auth /usr/local/bin/auth
EXPOSE 8081
ENTRYPOINT ["/usr/local/bin/auth"]
