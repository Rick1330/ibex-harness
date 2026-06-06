FROM golang:1.25-alpine3.20 AS build
WORKDIR /src
COPY go.mod go.sum ./
COPY services/auth ./services/auth
RUN go build -o /out/auth ./services/auth/cmd/auth

FROM alpine:3.23@sha256:5b10f432ef3da1b8d4c7eb6c487f2f5a8f096bc91145e68878dd4a5019afde11
RUN adduser -D -H -u 10001 ibex
USER ibex
COPY --from=build /out/auth /usr/local/bin/auth
EXPOSE 8081
ENTRYPOINT ["/usr/local/bin/auth"]
