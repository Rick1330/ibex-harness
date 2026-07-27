# IBEX Harness — Changelog

All notable changes to IBEX Harness are documented in this file.

We follow:

- **Semantic Versioning** for platform release tags: `vMAJOR.MINOR.PATCH`
- **URL-based API versioning** for REST: `/v1`, `/v2`
- **Additive evolution** for protobuf contracts (breaking changes require new package versions)

Release notes are human-readable summaries of user-visible changes, security fixes, and migrations — not raw git logs. See [RELEASING.md](web/engineering/RELEASING.md) for the automated version release pipeline.

---

## [0.1.2](https://github.com/Rick1330/ibex-harness/compare/v0.1.1...v0.1.2) (2026-07-27)


### Features

* **clickhouse:** typed batch writer for llm_traces (m2.5.2) ([#381](https://github.com/Rick1330/ibex-harness/issues/381)) ([f883e79](https://github.com/Rick1330/ibex-harness/commit/f883e79d3ae12bbb9163812d3813499883188c8e))
* **db:** directives and directive_versions schema (m2.3.1) ([#356](https://github.com/Rick1330/ibex-harness/issues/356)) ([0a4f366](https://github.com/Rick1330/ibex-harness/commit/0a4f36693ff3e662898bfe3319923a2e2e6f3fc0))
* **db:** sessions and checkpoints schema (m2.4.1) ([#366](https://github.com/Rick1330/ibex-harness/issues/366)) ([cc85307](https://github.com/Rick1330/ibex-harness/commit/cc85307a8629bdf521d7eea0f4c3d006a45f6a6b))
* **infra:** clickhouse llm_traces table schema (m2.5.1) ([#378](https://github.com/Rick1330/ibex-harness/issues/378)) ([3536d1e](https://github.com/Rick1330/ibex-harness/commit/3536d1ee8646dabdd866f09d51964209f08eeec7))
* **proxy,auth:** token revocation propagation via Redis pub/sub (m2.2.2) ([#353](https://github.com/Rick1330/ibex-harness/issues/353)) ([3434a08](https://github.com/Rick1330/ibex-harness/commit/3434a0873042b4daf0c3bc1d0781e490d340fbb7))
* **proxy:** async trace emitter — ClickHouse integration in LLM handler (m2.5.3) ([#383](https://github.com/Rick1330/ibex-harness/issues/383)) ([95783d7](https://github.com/Rick1330/ibex-harness/commit/95783d74b302641e9ab5fc5f47a3634324b36b12))
* **proxy:** auth cache — bloom filter + in-process LRU for token validation (m2.2.1) ([#350](https://github.com/Rick1330/ibex-harness/issues/350)) ([fe8b3b0](https://github.com/Rick1330/ibex-harness/commit/fe8b3b076f875df3fbe097e57322ee68ded30cca))
* **proxy:** centralise provider error mapping to stable envelope (m2.1.5) ([#348](https://github.com/Rick1330/ibex-harness/issues/348)) ([086ad61](https://github.com/Rick1330/ibex-harness/commit/086ad61cca3f52a1828e358185a1af4f629d2f79))
* **proxy:** directive resolver with Redis cache and Postgres fallback (m2.3.2) ([#360](https://github.com/Rick1330/ibex-harness/issues/360)) ([2bf5dcb](https://github.com/Rick1330/ibex-harness/commit/2bf5dcb84f890bce001801ec32756a42d34d3448))
* **proxy:** idempotency-key Redis dedupe for provider retries (m2.1.6) ([#388](https://github.com/Rick1330/ibex-harness/issues/388)) ([985dc90](https://github.com/Rick1330/ibex-harness/commit/985dc9098a84355ee56060bdb1c0b347c11362ec))
* **proxy:** m2.1.3 OpenAI SSE streaming dual-write forwarder ([#342](https://github.com/Rick1330/ibex-harness/issues/342)) ([e94d3b0](https://github.com/Rick1330/ibex-harness/commit/e94d3b00c4552b18209f29e3fed8545c685b48b7))
* **proxy:** provider routing middleware — selects provider by model (m2.1.4) ([#345](https://github.com/Rick1330/ibex-harness/issues/345)) ([d38acab](https://github.com/Rick1330/ibex-harness/commit/d38acabed5d36fdfd8d9a07ee97675d4601c2c3e))
* **proxy:** session idle-timeout sweeper marks abandoned sessions (m2.4.4) ([#375](https://github.com/Rick1330/ibex-harness/issues/375)) ([6fe142c](https://github.com/Rick1330/ibex-harness/commit/6fe142c83779b83d29f2553d46c7c25a7963d54c))
* **proxy:** session lifecycle management in LLM request handler (m2.4.3) ([#372](https://github.com/Rick1330/ibex-harness/issues/372)) ([a754dc9](https://github.com/Rick1330/ibex-harness/commit/a754dc977450a5af66a7e096b7801ad6a8c81af3))
* **proxy:** session store — create, checkpoint, close (m2.4.2) ([#368](https://github.com/Rick1330/ibex-harness/issues/368)) ([67fa0da](https://github.com/Rick1330/ibex-harness/commit/67fa0da4118184d7e08fb42f4c551123781216ca))
* **proxy:** system prompt injection with configurable strategy (m2.3.3) ([#363](https://github.com/Rick1330/ibex-harness/issues/363)) ([fb43000](https://github.com/Rick1330/ibex-harness/commit/fb43000f221cb64d97be57c62c81bc9ed77ed937))


### Bug Fixes

* **ci:** changelog deploy, daily benches, faster profiles ([#294](https://github.com/Rick1330/ibex-harness/issues/294)) ([a431a49](https://github.com/Rick1330/ibex-harness/commit/a431a4941d094861db030535435071a0802e935d))
* **ci:** exclude CI-only lockfiles from Syft SBOM for Grype ([#324](https://github.com/Rick1330/ibex-harness/issues/324)) ([28bb255](https://github.com/Rick1330/ibex-harness/commit/28bb255169678dfd94f8b27dfe1a94119e81675d))
* **ci:** resolve SonarQube workflow security hotspots ([#320](https://github.com/Rick1330/ibex-harness/issues/320)) ([808799e](https://github.com/Rick1330/ibex-harness/commit/808799ef8217295d90a569b6c50ab99566a4898f))
* **deps:** override js-yaml to clear GHSA-52cp-r559-cp3m ([#311](https://github.com/Rick1330/ibex-harness/issues/311)) ([7206f73](https://github.com/Rick1330/ibex-harness/commit/7206f73f85c655d34d50906d381a4f3c817a3e11))
* **security:** grpc bump, CodeQL alignment, dependabot go-git ignore ([#326](https://github.com/Rick1330/ibex-harness/issues/326)) ([977685e](https://github.com/Rick1330/ibex-harness/commit/977685ec06c90bde6724821198d5de752ec9661c))
* **web:** show desktop theme segmented control on cold load ([#297](https://github.com/Rick1330/ibex-harness/issues/297)) ([c8f0ffa](https://github.com/Rick1330/ibex-harness/commit/c8f0ffa206d4cc62cd424492b6b59e1edcfdbcdc))

## [0.1.1](https://github.com/Rick1330/ibex-harness/compare/v0.1.0...v0.1.1) (2026-07-19)


### Features

* **web:** paper/ink landing, blog, changelog, and roadmap redesign ([#280](https://github.com/Rick1330/ibex-harness/issues/280)) ([62ebbea](https://github.com/Rick1330/ibex-harness/commit/62ebbeacc1b9b61787f1895464631dc93de6403c))
* **web:** redesign changelog page with curated release notes ([#243](https://github.com/Rick1330/ibex-harness/issues/243)) ([636bdd7](https://github.com/Rick1330/ibex-harness/commit/636bdd75f4050143362bae229cfbc939dd984b7b))


### Bug Fixes

* **ci:** repair Tagged Release workflow_dispatch startup ([#240](https://github.com/Rick1330/ibex-harness/issues/240)) ([3973c83](https://github.com/Rick1330/ibex-harness/commit/3973c839796f59370d36bcf95134f969e84af293))
* **ci:** resolve tagged release job outputs from step context ([#242](https://github.com/Rick1330/ibex-harness/issues/242)) ([86f7f82](https://github.com/Rick1330/ibex-harness/commit/86f7f8284c29d29e42ab941bcce4e4dab48309b7))
* **ci:** run version release on merge to create release tag ([#238](https://github.com/Rick1330/ibex-harness/issues/238)) ([b9cd249](https://github.com/Rick1330/ibex-harness/commit/b9cd249197c6d0cb940d9ce564b555d91d1c907c))
* **ci:** skip DCO on merge commits; strip CR in PR tracking ([#275](https://github.com/Rick1330/ibex-harness/issues/275)) ([71026a3](https://github.com/Rick1330/ibex-harness/commit/71026a38f18b09368cab9a57fc257f65951df051))
* **ci:** split tagged release docker job to fix workflow_dispatch ([#246](https://github.com/Rick1330/ibex-harness/issues/246)) ([0d47fac](https://github.com/Rick1330/ibex-harness/commit/0d47facdc17ac1761862b43b7bf4f45e4330a563))
* **ci:** stop Vitest hang from blocking web deploy ([#282](https://github.com/Rick1330/ibex-harness/issues/282)) ([2e57189](https://github.com/Rick1330/ibex-harness/commit/2e571898f674b8672c80c215f6aa73d3398ba283))
* **ci:** use cosign bundle format for SBOM signing ([#247](https://github.com/Rick1330/ibex-harness/issues/247)) ([769a998](https://github.com/Rick1330/ibex-harness/commit/769a9981c0f7aef705ba36dfc9911df0669544ff))
* **ci:** weekly bench publish, every-PR comments, cosign sigstore upload ([#248](https://github.com/Rick1330/ibex-harness/issues/248)) ([06c8e8c](https://github.com/Rick1330/ibex-harness/commit/06c8e8c7507ba4a183668e1df230de56704618af))
* **web:** restore landing marquee and fix mobile overflow ([#286](https://github.com/Rick1330/ibex-harness/issues/286)) ([3ebe885](https://github.com/Rick1330/ibex-harness/commit/3ebe8851351aab0af33606a737597e81043fff24))

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

- Idempotency-Key Redis dedupe for non-streaming chat (m2.1.6): optional `Idempotency-Key` header, `idempotency:{org_id}:{key}` claim/commit in `packages/idempotency`, replay on hit, `409 IDEMPOTENCY_KEY_REUSE` / `IDEMPOTENCY_IN_PROGRESS`, fail-open on Redis errors ([ADR-0035](web/content/docs/adr/0035-chat-idempotency-key.mdx))
- Proxy overhead latency benchmark (m2.6.1): real warm-path Go stage microbenches, `BenchmarkProxyChatOverhead` with mockllm, ADR-0034, auth/provider duration histograms, k6 `full` profile chat path (`K6_USE_CHAT=1`), pinned `baseline.json`
- In-process mock LLM provider (`packages/provider/mockllm`): `IBEX_LLM_MODE=mock` returns immediate OpenAI-shaped JSON (smoke/chat 200 without OpenAI)
- Async trace emitter (m2.5.3): proxy `assembleTrace` + post-response bounded-pool emit into ClickHouse `Writer` (success, incomplete stream, provider failure); auth/directive stage latency on context; never blocks LLM response on CH errors
- ClickHouse client (`packages/clickhouse`, m2.5.2): concurrent batched `Writer` for `ibex.llm_traces` (clickhouse-go/v2, defaults batch 500 / flush 200ms), flush metrics, optional proxy shutdown drain when `CLICKHOUSE_DSN` is set
- ClickHouse `ibex.llm_traces` schema (m2.5.1): golang-migrate runner under `infra/migrations/clickhouse`, 90-day TTL MergeTree, ADR-0033, compose-test ClickHouse, `make clickhouse-migrate`
- Session idle-timeout sweeper (m2.4.4): proxy ticker marks stale `active` sessions `abandoned` under service-account RLS with advisory-lock multi-replica safety, Redis cache invalidation, metrics `ibex_proxy_session_sweeper_*`, and partial index `idx_sessions_active_updated_at` (migration `000011`)
- Proxy session lifecycle (m2.4.3): resolve/mint `X-IBEX-Session-ID` as sticky `external_id` before LLM forward; Redis session-state cache; response header on stream + non-stream; async non-dropping `AppendCheckpoint` pool drained on shutdown
- Session store (`packages/session`): Postgres `GetOrCreate` / `AppendCheckpoint` / `Complete` with org RLS; proxy constructs store when `POSTGRES_DSN` is set; metrics `ibex_proxy_session_*` (milestone 2.4.2)
- Sessions and checkpoints schema (`ibex_core.sessions` + `checkpoints`): Phase 2 subset with FORCE RLS, composite tenant FKs, append-only checkpoints, and extraction index ([ADR-0032](web/content/docs/adr/0032-session-data-model.mdx); migration `000010`; milestone 2.4.1)
- System prompt injection (`packages/injection`): pure `Inject` for `system_first` / `system_append` / `user_prepend`; proxy applies resolved directive to `provider.Request.Messages` before `Complete` ([ADR-0031](web/content/docs/adr/0031-system-prompt-injection.mdx); milestone 2.3.3)
- Directive resolver (`packages/directive`): Redis cache keyed `{org_id}:directive:{agent_id}` with Postgres fallback and pub/sub invalidation on `directive_updates:{org_id}`; proxy middleware resolves after agent verify (content stashed on context for 2.3.3 injection); metrics `ibex_proxy_directive_*`
- Directive schema (`ibex_core.directives` + `directive_versions`): immutable versions with `active_version_id` pointer, org RLS, 32KB content cap ([ADR-0030](web/content/docs/adr/0030-directive-versioning.mdx); migration `000009`)
- Auth cache revoke hardening: tombstone installed before index removal; LRU lookup re-checks revocation before serving cached claims
- Token revocation propagation (`packages/revocation`): auth PUBLISH + proxy SUBSCRIBE on `ibex:token:revocations` with `token_id` events and `InvalidateByTokenID` ([ADR-0029](web/content/docs/adr/0029-token-revocation-propagation.mdx)); metrics `ibex_auth_revocation_publish_total`, `ibex_proxy_revocation_invalidate_total`
- Auth cache (`packages/authcache`): in-process invalid-token bloom + claims LRU for proxy `ValidateToken` ([ADR-0028](web/content/docs/adr/0028-auth-cache-design.mdx)); metrics `ibex_proxy_auth_cache_*`; header `X-IBEX-Auth-Cached` on LRU hits
- PR push hygiene Cursor rule (`.cursor/rules/32-pr-push-hygiene.mdc`) encoding #350 CI/merge lessons
- Provider error mapping (`provider.MapError` / `MapProviderError` → `apierror.Error`) with sanitized details and `Retry-After` on upstream 429 ([ADR-0026](web/content/docs/adr/0026-openai-client-design.mdx))
- Provider routing middleware (`ChatParse` + `ProviderRouting`) extracts model→provider lookup from the chat handler ([ADR-0025](web/content/docs/adr/0025-llm-provider-abstraction.mdx))
- OpenAI streaming SSE dual-write forwarder (`stream=true`) with `StreamAccumulator`, flush-per-event, and stream metrics ([ADR-0027](web/content/docs/adr/0027-streaming-dual-write.mdx))
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
