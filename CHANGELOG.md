# IBEX Harness — Changelog

All notable changes to IBEX Harness are documented in this file.

We follow:

- **Semantic Versioning** for platform release tags: `vMAJOR.MINOR.PATCH`
- **URL-based API versioning** for REST: `/v1`, `/v2`
- **Additive evolution** for protobuf contracts (breaking changes require new package versions)

Release notes are human-readable summaries of user-visible changes, security fixes, and migrations — not raw git logs. See [RELEASING.md](web/engineering/RELEASING.md) for the automated version release pipeline.

---

## [Unreleased]

### Added

- OpenAI non-streaming provider adapter (`packages/provider/openai`) and proxy wiring for `POST /v1/chat/completions`
- Public API reference documentation at [ibexharness.com/docs/api-reference](https://ibexharness.com/docs/api-reference)
- Cosign-signed SBOM assets on tagged GitHub Releases
- OpenSSF Best Practices enrollment documentation and evidence map

### Changed

- Version release pipeline renamed to IBEX **Version Release PR** workflow (user-facing naming)
- Canonical changelog moved to repository root for release tooling and badge scanners

### Fixed

- SBOM workflow Grype install (pinned version, checksum verify, fail-closed DB update retries)
- Branch protection: `required_linear_history` on `main`

### Security

- Private vulnerability reporting documented in [`.github/SECURITY.md`](.github/SECURITY.md)
- Grype/Syft SBOM generation on `main` and release tags

---

## Changelog discipline

- Every version release PR must update this file.
- Security-sensitive exploit details are not disclosed before patch adoption.
- Breaking changes require a MAJOR bump or new REST API version plus a migration guide.
