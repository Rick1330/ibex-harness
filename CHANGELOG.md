# IBEX Harness — Changelog

All notable changes to IBEX Harness are documented in this file.

We follow:

- **Semantic Versioning** for platform release tags: `vMAJOR.MINOR.PATCH`
- **URL-based API versioning** for REST: `/v1`, `/v2`
- **Additive evolution** for protobuf contracts (breaking changes require new package versions)

Release notes are human-readable summaries of user-visible changes, security fixes, and migrations — not raw git logs. See [RELEASING.md](web/engineering/RELEASING.md) for the automated version release pipeline.

---

## 0.1.0 (2026-07-13)


### Features

* **auth:** token creation and management (m1.1.4) ([#47](https://github.com/Rick1330/ibex-harness/issues/47)) ([0ada899](https://github.com/Rick1330/ibex-harness/commit/0ada899a19631536aa730dda216f328322ecb25e))
* **auth:** validate PAT against Postgres (m1.1.3) ([#16](https://github.com/Rick1330/ibex-harness/issues/16)) ([5691dd8](https://github.com/Rick1330/ibex-harness/commit/5691dd8b1ef891287fb035c83b9dac4236187796))
* **bench:** build world-class benchmark pipeline and IBEX dashboard ([c7343de](https://github.com/Rick1330/ibex-harness/commit/c7343de3801412d8e580653acd33eb9b2e44b948))
* **bench:** data pipeline and docs benchmarks section ([#176](https://github.com/Rick1330/ibex-harness/issues/176)) ([08474f8](https://github.com/Rick1330/ibex-harness/commit/08474f89919248a3de7f1192da45713f1c18369f))
* **db:** users and agents schema, token FK constraints (m1.1.7) ([#57](https://github.com/Rick1330/ibex-harness/issues/57)) ([59e7e04](https://github.com/Rick1330/ibex-harness/commit/59e7e04528ec72e8bb9cab7fc3e67cf00b6d1d93))
* **docs:** apply Matte Graphite design tokens (D.2.2) ([#104](https://github.com/Rick1330/ibex-harness/issues/104)) ([e20d165](https://github.com/Rick1330/ibex-harness/commit/e20d16515842d8e7e1eb2b256c7ec63d8ac836bd))
* **docs:** ASCII text-only Mermaid diagrams ([#129](https://github.com/Rick1330/ibex-harness/issues/129)) ([901ec09](https://github.com/Rick1330/ibex-harness/commit/901ec094978d179da3cfba9c046f3687cdfcbe26))
* **docs:** bootstrap Fumadocs app at docs/app (D.2.1) ([#101](https://github.com/Rick1330/ibex-harness/issues/101)) ([fe58260](https://github.com/Rick1330/ibex-harness/commit/fe5826012ef7402e938469050177316dc6851ff1))
* **docs:** MDX component catalogue (D.2.3) ([#108](https://github.com/Rick1330/ibex-harness/issues/108)) ([1d317f8](https://github.com/Rick1330/ibex-harness/commit/1d317f88fca2eb5a78df54d344d0c5b4ae5479fb))
* **docs:** migrate to Cloudflare Pages static export ([#143](https://github.com/Rick1330/ibex-harness/issues/143)) ([a6d9269](https://github.com/Rick1330/ibex-harness/commit/a6d926913b596371b621eae9e83d84341f8c2de3))
* **docs:** navigation shell (D.2.7) ([#106](https://github.com/Rick1330/ibex-harness/issues/106)) ([37c134d](https://github.com/Rick1330/ibex-harness/commit/37c134d95066fb706d2cfa650f0e4381b31921ee))
* **docs:** unified landing and docs on ibexharness.com ([#189](https://github.com/Rick1330/ibex-harness/issues/189)) ([1aab5d2](https://github.com/Rick1330/ibex-harness/commit/1aab5d28b0407121db0a5da03f6ddc4a3007ee9a))
* **docs:** wave 14 mobile nav, perf, and mermaid ASCII fix ([#137](https://github.com/Rick1330/ibex-harness/issues/137)) ([e2040f1](https://github.com/Rick1330/ibex-harness/commit/e2040f1e65471a96ac4f95c41b9544b0ec0d9075))
* **docs:** Wave 4–5 milestones (D.2.4–D.3.1) ([#114](https://github.com/Rick1330/ibex-harness/issues/114)) ([3265689](https://github.com/Rick1330/ibex-harness/commit/3265689a47d9f243309b43ecfefb32f392414b32))
* **infra:** graceful shutdown with connection draining for auth and proxy (m1.2.7) ([#68](https://github.com/Rick1330/ibex-harness/issues/68)) ([716565e](https://github.com/Rick1330/ibex-harness/commit/716565ebe397407d1257ce2b8f004bca3d36907a))
* **proxy:** add llm provider interface and registry (m2.1.1) ([0841d4a](https://github.com/Rick1330/ibex-harness/commit/0841d4a93a309339d53076b0aa669557e5409d8d))
* **proxy:** agent identity verification via gRPC ValidateAgent (m1.2.5) ([#64](https://github.com/Rick1330/ibex-harness/issues/64)) ([6d244cf](https://github.com/Rick1330/ibex-harness/commit/6d244cfbd4ab067c06336ebc64b0dc7fb67b5346))
* **proxy:** auth gRPC client (m1.2.1) ([42ac2f9](https://github.com/Rick1330/ibex-harness/commit/42ac2f9e8a967a93287fb36274efdf51504d6be2))
* **proxy:** input validation and stable error envelope (m1.2.3) ([#55](https://github.com/Rick1330/ibex-harness/issues/55)) ([0762f8b](https://github.com/Rick1330/ibex-harness/commit/0762f8b5a16f883fc632e2499fad2ff4eea8a330))
* **proxy:** openai non-streaming HTTP client (m2.1.2) ([#211](https://github.com/Rick1330/ibex-harness/issues/211)) ([9d2c383](https://github.com/Rick1330/ibex-harness/commit/9d2c383a7a55d9668f0d1152ed41dd631379b397))
* **proxy:** rate limit skeleton (m1.2.4) ([#62](https://github.com/Rick1330/ibex-harness/issues/62)) ([b4a1aa5](https://github.com/Rick1330/ibex-harness/commit/b4a1aa5883f5f7d5ac636a3908d79204dd8b1674))
* **proxy:** request ID generation and context correlation middleware (m1.2.6) ([#66](https://github.com/Rick1330/ibex-harness/issues/66)) ([b5653fb](https://github.com/Rick1330/ibex-harness/commit/b5653fb50d7442f03b25d9ffa307555ee68e5361))
* **proxy:** request normalization (m1.2.2) ([26a727e](https://github.com/Rick1330/ibex-harness/commit/26a727eed18765648d731e4825aac03d52c1da83))
* **web:** restore warm landing visuals site-wide ([#195](https://github.com/Rick1330/ibex-harness/issues/195)) ([45c1323](https://github.com/Rick1330/ibex-harness/commit/45c1323324fae328f68d128847e6186ca9985f2b))


### Bug Fixes

* **auth:** correct ListTokens keyset cursor pagination ([6563132](https://github.com/Rick1330/ibex-harness/commit/65631323d6d964b86e5ff09482f8d128df70e7cd))
* **bench:** deploy dashboard via GitHub Actions Pages ([#175](https://github.com/Rick1330/ibex-harness/issues/175)) ([970d80e](https://github.com/Rick1330/ibex-harness/commit/970d80e1389b603c3d7ccf4a9a62a92259f23696))
* **bench:** k6 v0.53 parsing, real proxy benches, and Matte Graphite dashboard ([bfc0a75](https://github.com/Rick1330/ibex-harness/commit/bfc0a75cf168bbc1f462b027ce1e94bdd19dff44))
* **bench:** pre-PR benchmark publish and static docs embed ([b953161](https://github.com/Rick1330/ibex-harness/commit/b953161761abfca666fadbfc36153bb89a7aac1a))
* **bench:** resolve baseline_sha from published history when schema unset ([#179](https://github.com/Rick1330/ibex-harness/issues/179)) ([461c8a2](https://github.com/Rick1330/ibex-harness/commit/461c8a2f921d2187ead0c4d25a5f58e3fbd80918))
* **bench:** secure benchmark bot integration and fix dispatch payload ([#178](https://github.com/Rick1330/ibex-harness/issues/178)) ([a33daca](https://github.com/Rick1330/ibex-harness/commit/a33daca1743b6351d14857830baa0894aa8f2ecf))
* **bench:** show sub-ms stage latencies and validate go microbench data ([#184](https://github.com/Rick1330/ibex-harness/issues/184)) ([fdd0caa](https://github.com/Rick1330/ibex-harness/commit/fdd0caa527344ff8e40b27b1fc36052b3a37936d))
* **bench:** unblock k6 export and CI load profile ([#173](https://github.com/Rick1330/ibex-harness/issues/173)) ([401ba71](https://github.com/Rick1330/ibex-harness/commit/401ba7139ba10fedc8ba21863fde0fcf2098a1c1))
* **ci:** allow .github markdown in repo layout guard ([6f00382](https://github.com/Rick1330/ibex-harness/commit/6f003829c8cdff40cc631b2629ea6347277fc1d6))
* **ci:** complete workflow hardening and Sonar review fixes ([#158](https://github.com/Rick1330/ibex-harness/issues/158)) ([20c4772](https://github.com/Rick1330/ibex-harness/commit/20c47725d6cdaafbdce494a3a3cca1c009ad871a))
* **ci:** correct codecov pin and gitleaks allowlist for test fixture ([bc62f73](https://github.com/Rick1330/ibex-harness/commit/bc62f73ace0a148748d65e08d8aa5ea810ee7708))
* **ci:** drop production HTTP smoke from docs deploy ([#148](https://github.com/Rick1330/ibex-harness/issues/148)) ([1629673](https://github.com/Rick1330/ibex-harness/commit/1629673f3274a9b08413a900d8d934326a29a97a))
* **ci:** exclude infra from handwritten coverage gate scope ([a41dd45](https://github.com/Rick1330/ibex-harness/commit/a41dd4590da7509fb966f73202271b55a79dcb3c))
* **ci:** harden version release workflow reporting ([#230](https://github.com/Rick1330/ibex-harness/issues/230)) ([41d80e9](https://github.com/Rick1330/ibex-harness/commit/41d80e937f47c96dfc580e4efbc1c735eef01a2c))
* **ci:** improve workflow visibility and standardize release flow ([#169](https://github.com/Rick1330/ibex-harness/issues/169)) ([22fc040](https://github.com/Rick1330/ibex-harness/commit/22fc040606dbc02f8bbd5d7251ca19041d33944f))
* **ci:** make codecov upload non-blocking and annotate integration grpc tests ([41c1384](https://github.com/Rick1330/ibex-harness/commit/41c13840df3012d57811de459530d654d194de28))
* **ci:** post semantic-pr-title on version release PRs ([#234](https://github.com/Rick1330/ibex-harness/issues/234)) ([ea3004c](https://github.com/Rick1330/ibex-harness/commit/ea3004c40d6a1720cb56a07dc53c617a3e62b062))
* **ci:** repair action SHAs, Scorecard permissions, and pin guard ([#167](https://github.com/Rick1330/ibex-harness/issues/167)) ([b53fc48](https://github.com/Rick1330/ibex-harness/commit/b53fc48487db8bb58166a66ed273c7205c574e18))
* **ci:** repair SBOM Grype install and OpenSSF scorecard gaps ([#213](https://github.com/Rick1330/ibex-harness/issues/213)) ([5a4ea4f](https://github.com/Rick1330/ibex-harness/commit/5a4ea4fcfef39a38d3305248d5b2802fbffb251a))
* **ci:** resolve release PR number from release-please pr JSON ([#236](https://github.com/Rick1330/ibex-harness/issues/236)) ([3d91716](https://github.com/Rick1330/ibex-harness/commit/3d91716c1a3bbb2e92f0f598d65d9c84647df087))
* **ci:** run gitleaks full-repo scan to avoid root-commit range error ([9766982](https://github.com/Rick1330/ibex-harness/commit/97669820457452057f734b3b46f017e9a7542878))
* **ci:** stabilize docker-publish and benchmark history ([#168](https://github.com/Rick1330/ibex-harness/issues/168)) ([4a78127](https://github.com/Rick1330/ibex-harness/commit/4a78127d3088fdb2e07186699183618051581c7e))
* **ci:** stabilize integration coverage and resolve lint/secrets ([5d9fdae](https://github.com/Rick1330/ibex-harness/commit/5d9fdae0e183247764e9fb88ef70996a2cad18da))
* **ci:** stabilize SEC4 rate-limit probe; sync CURRENT_STATE after [#92](https://github.com/Rick1330/ibex-harness/issues/92) ([#93](https://github.com/Rick1330/ibex-harness/issues/93)) ([c729453](https://github.com/Rick1330/ibex-harness/commit/c729453baa9900b0062c5e4aa6278981d80fcb04))
* **ci:** unblock proxy config tests, lower coverage gate to 80% ([17da8ed](https://github.com/Rick1330/ibex-harness/commit/17da8edb7db63a3abf3e2c192f1a8c5bdf5200f4))
* **ci:** use valid gocovmerge pseudo-version ([b90e25f](https://github.com/Rick1330/ibex-harness/commit/b90e25f5509fe84fb00ddd2eaaed07e866a9299b))
* **docker:** bump golang build image to 1.25.12 for CVE-2026-39822 ([#198](https://github.com/Rick1330/ibex-harness/issues/198)) ([657a142](https://github.com/Rick1330/ibex-harness/commit/657a14224b1b96d38360391707793f3d85444702))
* **docs:** deploy with Node 22 and pnpm wrangler on main ([#131](https://github.com/Rick1330/ibex-harness/issues/131)) ([82ed7a1](https://github.com/Rick1330/ibex-harness/commit/82ed7a1ae23f6b0994a274ac4e5b4b29636fa4d1))
* **docs:** hoisted pnpm for OpenNext Workers runtime ([#132](https://github.com/Rick1330/ibex-harness/issues/132)) ([b19f3a2](https://github.com/Rick1330/ibex-harness/commit/b19f3a2d6722f186627cd438af06618853a50c00))
* **docs:** move fumadocs CSS import before Tailwind directives ([#103](https://github.com/Rick1330/ibex-harness/issues/103)) ([e218db8](https://github.com/Rick1330/ibex-harness/commit/e218db89c4dffac04ce1f1e3a92da41c6f82866f))
* **docs:** repair Cmd+K search and cut over domain to Pages ([#144](https://github.com/Rick1330/ibex-harness/issues/144)) ([06d0336](https://github.com/Rick1330/ibex-harness/commit/06d03369fa8614ea002428e5a011ba2bbcfee463))
* **docs:** repair static export Cmd+K search on Pages ([#146](https://github.com/Rick1330/ibex-harness/issues/146)) ([4c669fe](https://github.com/Rick1330/ibex-harness/commit/4c669fe0e2522bbce56ed9247961394df4f5c89f))
* **docs:** restore 3-column layout broken by page-enter wrapper ([#119](https://github.com/Rick1330/ibex-harness/issues/119)) ([bca974d](https://github.com/Rick1330/ibex-harness/commit/bca974dabb2cab3a966fc3bbba533db16d3289a1))
* **docs:** route brand to marketing site and align cross-domain SEO ([#153](https://github.com/Rick1330/ibex-harness/issues/153)) ([8ec859f](https://github.com/Rick1330/ibex-harness/commit/8ec859f0400df2bd1ad6148a41c359ed42522253))
* **docs:** scan JS chunks in deploy smoke for search index URL ([#145](https://github.com/Rick1330/ibex-harness/issues/145)) ([0eba96d](https://github.com/Rick1330/ibex-harness/commit/0eba96d3bf85af8c9bc5e1e73b9d3bbb2be5f675))
* **docs:** serve search index as static public asset ([#142](https://github.com/Rick1330/ibex-harness/issues/142)) ([45028db](https://github.com/Rick1330/ibex-harness/commit/45028db7e100b5342de0c0b1f1b73eea56c6f002))
* **docs:** skip filesystem mtime on Cloudflare Workers ([#133](https://github.com/Rick1330/ibex-harness/issues/133)) ([ded5ccd](https://github.com/Rick1330/ibex-harness/commit/ded5ccdb41f14841c2012d571506aaf0e3de9fa4))
* **docs:** unblock deploy, order CI jobs, optimize nav logo ([#147](https://github.com/Rick1330/ibex-harness/issues/147)) ([61b0bda](https://github.com/Rick1330/ibex-harness/commit/61b0bda599d979d6010f3c9e3dacb8a4dfd569fe))
* **docs:** use static Orama search for Cloudflare Workers ([d131878](https://github.com/Rick1330/ibex-harness/commit/d131878cfcc87ee5520a7ec8178e128546f5b6fe))
* **docs:** wave 14 quality gates remediation (re-land [#137](https://github.com/Rick1330/ibex-harness/issues/137)) ([#139](https://github.com/Rick1330/ibex-harness/issues/139)) ([cc18484](https://github.com/Rick1330/ibex-harness/commit/cc1848434923ebeb9366884c4648c1d61c3612c1))
* **dx:** local dev smoke, db-seed on Windows, and migration repair (m1.4.1) ([60ace91](https://github.com/Rick1330/ibex-harness/commit/60ace9169215c7f32f229e9b802b2f9437e942c7))
* move integration helpers into repository_test; gofmt chat cases ([4de673c](https://github.com/Rick1330/ibex-harness/commit/4de673cc06bb21b470eb01b40105b2d255f81153))
* **proxy:** close burst probe bodies and serialize integration tests in CI ([cdcb647](https://github.com/Rick1330/ibex-harness/commit/cdcb64739a420159ac4ad7955b3379879b261b15))
* **release:** enforce pre-1.0 versioning standard ([c961e06](https://github.com/Rick1330/ibex-harness/commit/c961e06472f58462374085862c54c9438ba63d74))
* remove unused authMessageTestCases helper ([9a51b49](https://github.com/Rick1330/ibex-harness/commit/9a51b49f1e0750c1512278a5ca8154c3ceebfb96))
* remove unused field from uuid test cases ([196ec52](https://github.com/Rick1330/ibex-harness/commit/196ec52c42777497291abdea995d477c7470853c))
* **test:** remove hanging run test and cover config nil pointer redaction ([e5ffdc7](https://github.com/Rick1330/ibex-harness/commit/e5ffdc7adc879899955811d0e33848f9905fdce8))
* use full semgrep nosemgrep id for test gRPC servers ([aa16c8d](https://github.com/Rick1330/ibex-harness/commit/aa16c8dd6df28a667d93171ae70514a447c09b79))
* **web:** sanitize RSC prefetch txt files on static export ([#197](https://github.com/Rick1330/ibex-harness/issues/197)) ([775ad1f](https://github.com/Rick1330/ibex-harness/commit/775ad1f4d00fe82a0d112fbfa959a800e2f668ea))


### Performance Improvements

* **docs:** reduce CLS and enforce static doc pages ([#116](https://github.com/Rick1330/ibex-harness/issues/116)) ([c9031be](https://github.com/Rick1330/ibex-harness/commit/c9031befbceeb30349dc2014a3c2b31e0f6250dc))

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
