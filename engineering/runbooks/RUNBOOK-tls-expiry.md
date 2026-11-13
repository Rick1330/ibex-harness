# Runbook: TLS certificate expiry (P1/P2)

**Scope.** The `v1-single-node` profile terminates TLS at Caddy (edge leaf) and
on the Auth gRPC listener (auth leaf), both issued by a per-install CA. Expiry
is silent until a client handshake fails, because nothing renews the leaves
automatically.

## Symptoms

- Browsers or `curl` report `certificate has expired` on the edge port
  (`https://localhost:${IBEX_EDGE_PORT}`).
- The `edge` container healthcheck fails:
  `curl -fsS --cacert /run/secrets/ca.crt https://127.0.0.1:8443/_edge/health`
  (`infra/compose/v1-single-node/compose.yml`:527-532).
- Auth refuses to start or drops gRPC readiness with a certificate-validity
  error (`services/auth/internal/config/config.go`:128-139).
- Internal service-to-service gRPC calls fail with TLS verification errors.

## Detection

1. Read the expiry directly, without restarting anything:

   ```bash
   openssl x509 -in infra/compose/v1-single-node/certs/edge.crt -noout -subject -enddate
   openssl x509 -in infra/compose/v1-single-node/certs/auth.crt -noout -subject -enddate
   openssl x509 -in infra/compose/v1-single-node/certs/ca.crt   -noout -subject -enddate
   ```

2. Confirm which material the containers actually mount. Caddy uses
   `/run/secrets/edge.crt` and `edge.key` (`infra/compose/v1-single-node/edge/Caddyfile`:17);
   Auth reads `IBEX_AUTH_GRPC_TLS_CERT_FILE=/run/secrets/auth.crt` and the key
   (`compose.yml`:169-170). These are copies installed from `certs/` by
   `make v1-secrets` (`infra/scripts/gen-v1-secrets.sh`:344-350).
3. Know the lifetimes: the CA is issued for 3650 days and each leaf for 825 days
   (`infra/scripts/gen-v1-tls.sh`:238,265). A leaf can expire while the CA is
   still valid.

## First response

1. **Do not disable TLS or switch Caddy to `auto_https` to clear the error.**
   Both leave the deployment exposed and break the auth TLS contract.
2. Record the affected leaf, its SANs, and the expiry timestamp. Auth's leafs
   must carry `DNS:auth` / `127.0.0.1`; the edge leaf must carry `localhost` /
   `edge` (`gen-v1-tls.sh`:207-210).
3. Keep the existing CA. Reissuing a leaf does not require rotating the CA.

## Recovery

1. Reissue only the expired/invalid leaf. `gen-v1-tls.sh` is idempotent: it
   reuses a valid CA and regenerates only missing, mismatched, wrong-purpose or
   expired leaves (`gen-v1-tls.sh`:22-24,170-210). Run it without `--force`.
2. Install the new leaf copies into the secrets directory:
   `make v1-secrets` re-runs the TLS generator and re-copies `ca.crt`, `auth.*`,
   `edge.*` (`gen-v1-secrets.sh`:344-350). It also detects a changed
   fingerprint and marks the cert material so `v1-up` recreates the mounted
   services (`gen-v1-secrets.sh`:355-360).
3. Restart the affected services (`edge`, `auth`) so they load the new leaf.
   Auth validates the leaf on load, so a stale process keeps serving the old one.
4. Verify: the edge healthcheck passes and `openssl s_client` against the edge
   port shows the new `notAfter`.

**Rotating the CA** (compromise, not expiry) is a different action:
`gen-v1-tls.sh --force` rotates the CA and reissues both leaves
(`gen-v1-tls.sh`:37-40). Every client that trusts the old `ca.crt` must be
updated in the same change.

## Escalation

- Escalate a CA compromise to security; expiry alone is routine.
- Escalate to the owner if expiry is caused by a deployment that pins a stale
  leaf or ignores the regenerated fingerprint.

## Evidence to keep

- `openssl x509 -enddate` output for the old and new leaves.
- The CA fingerprint before and after (never the private keys).
- Which services were restarted, and the healthcheck result after.
