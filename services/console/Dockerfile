# IBEX Console — Nuxt 4 SSR (node-server preset), multi-stage, non-root, pnpm.
#
# HEALTHCHECK is only emitted for a Docker-format build. Podman 5.7 defaults to
# OCI, which drops it: build with `--format docker` or declare an
# equivalent compose `healthcheck`.
#
# Build:
#   podman build -t ibex-console:local -f services/console/Dockerfile .
#
# Run (the operator API origin stays server-side; never expose it to the
# browser as a public runtime config value):
#   podman run --rm -p 3000:3000 \
#     -e IBEX_OPERATOR_API_ORIGIN=https://<edge-origin> \
#     -e IBEX_OPERATOR_SESSION_COOKIE_NAME=ibex_session \
#     ibex-console:local
#
# The origin must be the HTTPS edge URL. The BFF refuses to set the session
# cookie over a non-HTTPS origin (services/console/server/utils/operator/http.ts;
# ADR-0097 §4), so an `http://` upstream value here would authenticate and then
# fail to persist the session.
#
# Runtime env read by the Nitro BFF / server:
#   IBEX_OPERATOR_API_ORIGIN          upstream operator API base URL
#   IBEX_OPERATOR_SESSION_COOKIE_NAME session cookie name (default ibex_session)
#   NUXT_PUBLIC_IBEX_ENV              public environment label (no secrets)
#   HOST / PORT                       Nitro listen address (0.0.0.0:3000 here)
#
# Secrets are injected at run time. No credential or upstream origin is baked
# into this image.

# --------------------------------------------------------------------------- #
# Stage 1 — workspace install and production build.                            #
# --------------------------------------------------------------------------- #
FROM node@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d AS build

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

WORKDIR /src

# Workspace configuration and every workspace manifest pnpm needs for a frozen
# filtered install. .npmrc is part of the install contract (node-linker=hoisted).
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY site/package.json ./site/package.json
COPY packages/proto/package.json ./packages/proto/package.json
COPY services/console/package.json ./services/console/package.json

RUN pnpm install --frozen-lockfile --filter @ibex/console...

# Copy the application source after the dependency layer.
COPY services/console ./services/console

RUN NODE_ENV=production pnpm --filter @ibex/console build

# --------------------------------------------------------------------------- #
# Stage 2 — runtime image (Nitro node-server output only).                     #
# --------------------------------------------------------------------------- #
FROM node@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d AS runtime

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000

RUN groupadd -g 10001 ibex \
    && useradd -u 10001 -g ibex -r -s /usr/sbin/nologin ibex

WORKDIR /app

COPY --from=build /src/services/console/.output ./.output

USER 10001:10001

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:' + (process.env.NITRO_PORT || process.env.PORT || '3000') + '/').then((res) => process.exit(res.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", ".output/server/index.mjs"]
