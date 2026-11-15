# Docker Compose environments

Development, test, local observability, and the supported `v1-single-node` profile. Each child README documents
services, ports, health semantics, credentials, and destructive volume cleanup. Keep application and data-store
topology aligned with the actual YAML.

## Directories

| Directory | Purpose |
|---|---|
| `dev/` | Development dependency stack (data stores + workers); not a supported deployment. |
| `test/` | Minimal dependencies for integration tests. |
| `observability/` | Local LGTM stack. |
| `v1-single-node/` | The supported single-node profile: one published HTTPS edge port, pinned dependencies, and three one-shot gates in start order — `migrate`, `provision`, then `bootstrap`. Every application service connects on its capability login (`ibex_bootstrap`, `ibex_auth`, `ibex_runtime`, `ibex_worker`) and asserts it at startup; only `migrate` and `provision` use the owner credential. See [the profile source](../../site/content/docs/12.deployment/05.v1-single-node.md) and `engineering/DEPLOYMENT.md` §3.3. |
| `bundles/` | Opt-in memory/context smoke bundles. |
| `overlays/host` | Host-network overlay for development. |
