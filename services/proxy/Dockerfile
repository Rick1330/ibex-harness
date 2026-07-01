FROM golang:1.25-alpine3.22@sha256:6c527152c9ad2fb220f17c02b9a79d76731aafb28302f4f3b40f1449f9892036 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download -x
COPY packages ./packages
COPY services/proxy ./services/proxy
RUN go build -o /out/proxy ./services/proxy/cmd/proxy

FROM alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b
RUN adduser -D -H -u 10001 ibex
USER ibex
COPY --from=build /out/proxy /usr/local/bin/proxy
EXPOSE 8082
ENTRYPOINT ["/usr/local/bin/proxy"]
