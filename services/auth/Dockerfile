FROM golang:1.25-alpine3.20 AS build
WORKDIR /src
COPY go.mod go.sum ./
COPY services/auth ./services/auth
RUN go build -o /out/auth ./services/auth/cmd/auth

FROM alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b
RUN adduser -D -H -u 10001 ibex
USER ibex
COPY --from=build /out/auth /usr/local/bin/auth
EXPOSE 8081
ENTRYPOINT ["/usr/local/bin/auth"]
