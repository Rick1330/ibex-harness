# Runbook: Credentials master key lost or rotated (P1)

**Scope.** `IBEX_CREDENTIALS_MASTER_KEY` is the AES-256-GCM key-encryption key
(KEK) that seals org-scoped provider API keys in Auth
(`engineering/adr/0074-provider-credential-storage.md`:3,27;
`engineering/ENVIRONMENT_VARIABLES.md`:382-383). It is Auth-only and never
shipped to the API or proxy. `IBEX_CREDENTIALS_MASTER_KEY_ID` is rotation
metadata stored with each sealed blob.

**The hard fact.** This key has **no backup or recovery step in this
repository**. The release plan records that gap as open
(`engineering/architecture-v2/31-v1-release-plan-2026-11-09.md`:97,205), and
nothing in the tree persists the key anywhere beyond the operator's own secret
store. There is no in-repo command that recovers a lost key, and this runbook
does not invent one.

## Symptoms

- Auth refuses to start outside `development`:
  `IBEX_CREDENTIALS_MASTER_KEY is required when IBEX_ENV=production`
  (`services/auth/internal/config/config.go`:245-257).
- Provider calls that resolve an org credential fail closed instead of falling
  back to the platform key (`services/auth/internal/service/provider_credentials.go`:113,157-159`).
- After a key rotation, decryption fails for every blob sealed under the old key
  (AES-GCM authentication failure), even though the rows are intact.

## Detection

1. Confirm which key state the process sees: Auth validates the key at config
   load (`config.go`:71,245-257`). A missing key in production is a startup
   failure, not a running degradation.
2. Distinguish **missing** from **wrong**:
   - Missing: Auth does not start; the error names the variable.
   - Wrong/changed: Auth starts, has a key, and decryption fails per credential.
3. Identify the key id in use (`IBEX_CREDENTIALS_MASTER_KEY_ID`, default `v1`)
   and the key id recorded on the failing blob.

## First response

1. **Do not generate a new key to get past the probe.** A fresh key cannot
   decrypt blobs sealed with the old one; it converts a recoverable
   configuration error into permanent credential loss.
2. Locate the exact key the deployment was using. The only place it can be is
   the operator's secret store or deployment secret — there is no repository
   fallback.
3. Freeze credential mutations until the key is settled, so no new blobs are
   sealed under a key you are about to change.

## Recovery

- **Key found (correct one):** restore it into the deployment secret and restart
  Auth; verify one org provider credential resolves through the API.
- **Key genuinely lost:** sealed provider credentials are unrecoverable. The
  database is intact, but each stored provider key is ciphertext nobody can
  open. Recovery is a credential re-entry event:
  1. Provision a new `IBEX_CREDENTIALS_MASTER_KEY` and bump
     `IBEX_CREDENTIALS_MASTER_KEY_ID`.
  2. Have each affected org re-submit its provider API key so it is re-sealed
     under the new key.
  3. Record that credentials were lost, for which orgs, and when.
- **Rotation with the old key still present:** decrypt with the old key id,
  re-seal under the new key id, and only then retire the old key. There is no
  in-repo rotation tool; this is a manual, audit-logged operation.

## Escalation

- Escalate to security and the platform owner immediately on suspected key
  compromise (not just loss): a leaked KEK means every sealed provider key is
  compromised.
- Escalate to the owner that a backup step does not exist; that is an open
  release row, not something this runbook can close.

## Evidence to keep

- The Auth startup error and timestamp.
- The key id in use and the key id on a failing blob (never the key value).
- Which orgs' credentials failed to decrypt, and which were re-entered.
- For a compromise, rotation and re-seal timeline with audit log references.
