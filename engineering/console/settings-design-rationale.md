# Settings — Tokens, Providers, Webhooks, Audit

Separate Settings tabs (not sidebar items). Fixture clients in
`src/lib/settings/api.ts` mirror completed Tokens / Providers / Webhooks APIs.

## Audit & Actions

Unified timeline over `audit_log` + `operator_action_ledger` fields (not two
tabs). Owner/admin gate until a dedicated `admin:audit_log` bit exists.
Outcomes are explicit: Success / Denied / Pending second approval — never a
spinner for those states. Export writes `audit.export` into the same feed.
Honesty: hash-chain is not Merkle/WORM; no documented `GET /v1/audit-log` yet
(fixtures until the read API lands). Legal-hold rows need `LegalHoldManage`.

## Honesty

- PAT plaintext + webhook/provider secrets: one-time reveal only.
- Permission checkboxes disabled (not hidden) for bits the caller lacks —
  elevation → `403 PERMISSION_ELEVATION_DENIED`.
- `allowed_ips` omitted until enforcement (syntax-only gap documented).
- Webhook delivery history: "coming soon" — no fabricated log.
- Provider `status: active` only after fixture upstream validation (keys
  starting with `bad` → `invalid`).
- Cross-tenant token miss → identical "Token not found" (404, never 403).
- Webhook create requires `TokenCreate` (bit 36); providers need
  `OrgSettingsWrite` (bit 35).
