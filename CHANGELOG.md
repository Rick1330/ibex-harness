# IBEX Harness — Changelog

All notable changes to IBEX Harness are documented in this file.

We follow:

- **Semantic Versioning** for platform release tags: `vMAJOR.MINOR.PATCH`
- **URL-based API versioning** for REST: `/v1`, `/v2`
- **Additive evolution** for protobuf contracts (breaking changes require new package versions)

Release notes are human-readable summaries of user-visible changes, security fixes, and migrations — not raw git logs. See [RELEASING.md](engineering/RELEASING.md) for the automated version release pipeline.

---

## [0.1.11](https://github.com/Rick1330/ibex-harness/compare/v0.1.10...v0.1.11) (2026-11-22)


### Features

* **console:** design the sessions surface, and stop describing pages in their own header ([26b6081](https://github.com/Rick1330/ibex-harness/commit/26b60811e2cb6013d139205b353e75a569aa6b84))
* **smoke:** make v1-smoke prove the chat path, and stop reporting a skip as a pass ([4ba2bfe](https://github.com/Rick1330/ibex-harness/commit/4ba2bfeb0bce4d29cd398132163805c745048aeb))
* **stage3:** run the v1 profile smoke as a CI gate, and fail when the published status surfaces disagree ([d7ff50b](https://github.com/Rick1330/ibex-harness/commit/d7ff50b6c2d1c770e2d372c2797aaeddf1785cf4))


### Bug Fixes

* **build:** remove the no-op package upgrade and record the base digests ([48bca51](https://github.com/Rick1330/ibex-harness/commit/48bca51792fb7ba62883332d2a3adc7875fe9213))
* **console:** a trace-only refusal says which remedy it needs ([7d7b50c](https://github.com/Rick1330/ibex-harness/commit/7d7b50c224f3fd66815ebc8ff959c864472b2b12))
* **console:** an abandoned session is not a completed one ([14cc6de](https://github.com/Rick1330/ibex-harness/commit/14cc6de0ca5abcb7fafcab21c0b59cbb03649928))
* **console:** keep the health snapshot's own read time, at the value ([b8d5e6d](https://github.com/Rick1330/ibex-harness/commit/b8d5e6d4199332ba6abea8a9575ad258d45e10f8))
* **console:** let the mobile disclosure scroll, and test it at phone size ([6d88f78](https://github.com/Rick1330/ibex-harness/commit/6d88f78b97bc13a37fa0b36b7cb5f45a746ef17e))
* **console:** offer the sign-in the page asks for, and a way to sign out ([6df9eed](https://github.com/Rick1330/ibex-harness/commit/6df9eed58c38a8dfd79cd324ad0062d7c45f3aa2))
* **console:** the extraction pointer is an index, not a count — stop printing it as a percentage ([57f3576](https://github.com/Rick1330/ibex-harness/commit/57f35760173dbca824bb023c9f6ebbeb2ebbc668))
* **gates:** stop the PR tracking check calling an existing link missing after a failed re-read ([d600129](https://github.com/Rick1330/ibex-harness/commit/d6001297e58ab54b44b3318cac8887295f1c771b))
* **gates:** stop reporting a missing reference when the issue could not be read ([3180f80](https://github.com/Rick1330/ibex-harness/commit/3180f806a92e0d9395dbf98ab507cede91758428))
* **memory:** a forget must clear the cache it wrote, and prove it ([347b4cc](https://github.com/Rick1330/ibex-harness/commit/347b4cc6651240432e3cc16e57c449faab83c361))
* **memory:** a late create can no longer undo a forget, and the retry tells transient from permanent ([c189cf0](https://github.com/Rick1330/ibex-harness/commit/c189cf098fce7fa87640c9d6be18d4942ab4a550))
* **memory:** the purge records the address it is about to erase, and the archive recheck pays from the job budget ([458dd8c](https://github.com/Rick1330/ibex-harness/commit/458dd8c9b97c1d07017e7b49bcbf8c12bd11ed47))
* **memory:** the purge saga's own evidence settles a purged row, and a reappeared copy is deleted ([e825a23](https://github.com/Rick1330/ibex-harness/commit/e825a23285b32a6cfe22feb56fb1d8a244ea8dfd))
* **migrations:** hold the table before the rollback guard reads it ([7f5b9b0](https://github.com/Rick1330/ibex-harness/commit/7f5b9b0eaae8a42f16588cdb5bbb7c7986a5f0ce))
* **proxy:** give the extraction enqueue client its own connection pool ([3b604a3](https://github.com/Rick1330/ibex-harness/commit/3b604a3b41514908a4b9d99542be54f555b33a65))
* **proxy:** the context hop was asleep, not slow ([6f7ae55](https://github.com/Rick1330/ibex-harness/commit/6f7ae55095bff57b52543f78de131392b611d85e))
* **redact:** close a disclosure regression and a quadratic scan ([6a67381](https://github.com/Rick1330/ibex-harness/commit/6a6738126c70ac07be8ce3237791750063aa3178))
* **release:** an exhausted budget is not evidence of absence, and failed lookups back off ([a2f06a0](https://github.com/Rick1330/ibex-harness/commit/a2f06a0ea1877faa9ba58e4db9b590dafb3fa270))
* **release:** back off on a sustained failure, not on a lifetime count ([899ab17](https://github.com/Rick1330/ibex-harness/commit/899ab173dc1f7d4bda12be1850ffa27f98916738))
* **release:** wait long enough for the smoke evidence, and stop inventing its absence ([14dc5dc](https://github.com/Rick1330/ibex-harness/commit/14dc5dc6bb188b884f9db4d89fd727d853bd20ff))
* **smoke:** reject a non-positive attempt budget, and filter an unfixable advisory ([86098ba](https://github.com/Rick1330/ibex-harness/commit/86098baef3e77056547429e38096119057b3df3b))
* **smoke:** require the chat check to prove context assembly did not degrade ([a79e060](https://github.com/Rick1330/ibex-harness/commit/a79e060feaa2c32c0c5b9e58c1e505f0210130ea))
* **stage3:** make the v1 smoke complete the chat path, and record only a passing CI run as release evidence ([030869d](https://github.com/Rick1330/ibex-harness/commit/030869d783f1d0faf3cb644ad1882e19745468dd))
* **stage3:** keep the Redis password out of the container's command line, and scan the Python lockfiles for CVEs ([f9a58e5](https://github.com/Rick1330/ibex-harness/commit/f9a58e5fd99a26c4825727cac709ece53c789376))
* **stage3:** refuse a Redis password that disagrees with the env file, and serialise the bootstrap first-run guard ([c41cc09](https://github.com/Rick1330/ibex-harness/commit/c41cc09fe67ef77b228a0263346a92e3ba1bf1e8))
* **stage3:** keep a generated PAT out of test logs, and refuse a dated waiver ([2e8d930](https://github.com/Rick1330/ibex-harness/commit/2e8d930edbcfd33466858052cf59ff556111d0f7))
* **stage3:** stop the claims check ignoring rendered props, and the log filter leaking a quoted secret ([863b533](https://github.com/Rick1330/ibex-harness/commit/863b53316a7b45b58f260a83c2163ea0ec46bd0d))
* **stage3:** make the claims check read quoted attributes and character references, and scope a denial to its clause ([7df3020](https://github.com/Rick1330/ibex-harness/commit/7df302008169acfc3d75dfca6ddfde3446f5df9e))
* **stage3:** rebuild images when only .dockerignore changes, and stop a gate rule that enforces nothing from reporting success ([2ad84f7](https://github.com/Rick1330/ibex-harness/commit/2ad84f79dd26cf6c60d073ea5c350288b1da4559))
* **stage3:** parse Vue templates with the compiler, and dump redacted profile logs when the smoke fails ([ba72e98](https://github.com/Rick1330/ibex-harness/commit/ba72e989d51aaf7f0c31654f7fae3f34aea7ed23))
* **v1-profile:** a shared label for the backup config, and lazy operands in dotenv ([fca8673](https://github.com/Rick1330/ibex-harness/commit/fca86736bd7c8391f49e7f4dbf9dc10488a40fc7))
* **v1-profile:** the six hardening items an audit left open, two of them hazards ([69e77a5](https://github.com/Rick1330/ibex-harness/commit/69e77a538b296cda90328227d4db8cf8e756be12))
* **v1-smoke:** distinguish a cold start from a broken assembly path ([d77b15f](https://github.com/Rick1330/ibex-harness/commit/d77b15fdec5316d6a28f05b5de4e195d942ce4e1))
* **worker:** a failure the worker observed may replace its own proof, and Redis refusals are permanent ([bf08008](https://github.com/Rick1330/ibex-harness/commit/bf08008cf392875906e8582ba23cb5a578867158))
* **worker:** an erasure receipt records the addresses it proved ([7af7450](https://github.com/Rick1330/ibex-harness/commit/7af7450ea3e25dd3949471e48542865ceda524ed))

## [0.1.10](https://github.com/Rick1330/ibex-harness/compare/v0.1.9...v0.1.10) (2026-11-17)


### Features

* **api:** add tenant-scoped operator agents read model ([#1051](https://github.com/Rick1330/ibex-harness/issues/1051)) ([d23f661](https://github.com/Rick1330/ibex-harness/commit/d23f6616159caeaa158198d27b6c988f817f78dc))
* **api:** add the metadata-only operator memories read model ([#1070](https://github.com/Rick1330/ibex-harness/issues/1070)) ([249e503](https://github.com/Rick1330/ibex-harness/commit/249e503a266ed8e300f9412046d4a4e21a9cc99d))
* **api:** add the metadata-only operator sessions read model ([#1074](https://github.com/Rick1330/ibex-harness/issues/1074)) ([b25ab94](https://github.com/Rick1330/ibex-harness/commit/b25ab949c2b3075ac4d26489d358dda8972970b0))
* **api:** emit Deprecation and Sunset from the record ([4018032](https://github.com/Rick1330/ibex-harness/commit/4018032439459ae2bdc9324a93f683457622212f))
* **api:** enforce the permissions the routes already claimed ([91e6335](https://github.com/Rick1330/ibex-harness/commit/91e6335668b555878b6cddd1a44da55e7147c6ad))
* **auth:** pin ibex_app for tenant queries and call the token definer ([#1172](https://github.com/Rick1330/ibex-harness/issues/1172)) ([82e4c93](https://github.com/Rick1330/ibex-harness/commit/82e4c93256eb0a4cb3260ea1e8fd5687d259ce9a))
* **auth:** serve AuthService over TLS with a per-install CA ([669c788](https://github.com/Rick1330/ibex-harness/commit/669c7888cf578b3535f49112a8cad16ce5521dfb)), closes [#1143](https://github.com/Rick1330/ibex-harness/issues/1143)
* **bench:** fail when a published artifact cannot support its claim ([2f6fb8a](https://github.com/Rick1330/ibex-harness/commit/2f6fb8a3788fd308e2daf86648e9e54946b7ba5b))
* **bench:** gate the mode comparison on a declared outcome ([7317ae3](https://github.com/Rick1330/ibex-harness/commit/7317ae3ac0eefd9b53f5b5569f6ba681f485eea6))
* **bench:** generate and commit the gold-set v2 corpus (5.C.1b part 2) ([#1116](https://github.com/Rick1330/ibex-harness/issues/1116)) ([d893324](https://github.com/Rick1330/ibex-harness/commit/d893324303b8014cea855d6d0307c94b13b9b9b9))
* **bench:** graded embedding geometry and gold-set v2 validator (5.C.1b part 1) ([#1112](https://github.com/Rick1330/ibex-harness/issues/1112)) ([665fefe](https://github.com/Rick1330/ibex-harness/commit/665fefeaeec1d342ba054046c70e080425d6c52e))
* **bench:** multi-mode retrieval configs and point-based gate (5.C.2 part 1) ([#1122](https://github.com/Rick1330/ibex-harness/issues/1122)) ([5455e90](https://github.com/Rick1330/ibex-harness/commit/5455e909b2089974bef7f1d9a4c9fd41cc9ceee4))
* **bench:** record provenance on every published benchmark run ([d1a7dd5](https://github.com/Rick1330/ibex-harness/commit/d1a7dd5b279e7acb7889df36ac65dece95e0c074))
* **bench:** run every retrieval mode, and gate it against a measured baseline ([eef5ea8](https://github.com/Rick1330/ibex-harness/commit/eef5ea89d0b396e84f98e8f3694e243f0dd33819))
* **bench:** seed gold-set v2 (graded vectors and pending conflicts) ([#1120](https://github.com/Rick1330/ibex-harness/issues/1120)) ([70f5479](https://github.com/Rick1330/ibex-harness/commit/70f5479f57463413a4cee6e8dd6a07cd2ab768fd))
* **budget:** add durable reservation ledger for chat admission (GAP-006) ([#1001](https://github.com/Rick1330/ibex-harness/issues/1001)) ([f05eadb](https://github.com/Rick1330/ibex-harness/commit/f05eadb3176ce9bd22a82065d0266d1ee0ecab7b))
* **build:** add context and console images ([8991fc2](https://github.com/Rick1330/ibex-harness/commit/8991fc2f8d0d401f84feadde858fdc9b316b37bf)), closes [#1143](https://github.com/Rick1330/ibex-harness/issues/1143)
* **console:** make the agents surface live ([#1059](https://github.com/Rick1330/ibex-harness/issues/1059)) ([f6c19ac](https://github.com/Rick1330/ibex-harness/commit/f6c19ac568ca0a1f88def3dac1259eb3640cf7de))
* **console:** make the sessions surface live ([#1076](https://github.com/Rick1330/ibex-harness/issues/1076)) ([a8c1056](https://github.com/Rick1330/ibex-harness/commit/a8c1056d9a4bed22e34432ea2d8c0f2821b36a92))
* **console:** scope the operator console to the memory/context lifecycle ([#1049](https://github.com/Rick1330/ibex-harness/issues/1049)) ([eb6480a](https://github.com/Rick1330/ibex-harness/commit/eb6480ab47ed1f02f20b1076e6befe0318a2c25e))
* **context:** add contextAssembly stub artifact, scheduled stub gate and site registry ([#1025](https://github.com/Rick1330/ibex-harness/issues/1025)) ([e48c510](https://github.com/Rick1330/ibex-harness/commit/e48c5106d28b99a16650e1c6b534bad8e8df2269))
* **context:** authenticate callers and bind tenant authority to the principal ([#1131](https://github.com/Rick1330/ibex-harness/issues/1131)) ([5a03246](https://github.com/Rick1330/ibex-harness/commit/5a032466c001854052d437de96bdd7d0617b8034))
* **contracts:** gate the OpenAPI contract, deprecation windows and MCP descriptors ([#1194](https://github.com/Rick1330/ibex-harness/issues/1194)) ([a1be8b7](https://github.com/Rick1330/ibex-harness/commit/a1be8b79011c2dd85969b75763d69380e7ad5fa8))
* **contracts:** register every rpc and tool, and stop naming contracts that do not exist ([c846fd8](https://github.com/Rick1330/ibex-harness/commit/c846fd8beea760b578842267105a6018cfaaf4c9))
* **db:** remove the forgeable service-account bypass (P0-06 foundation) ([#1168](https://github.com/Rick1330/ibex-harness/issues/1168)) ([d730ee7](https://github.com/Rick1330/ibex-harness/commit/d730ee7bafee45488f8d1f7483e58b3245682321))
* **deploy:** assemble and evidence the v1-single-node profile ([#1147](https://github.com/Rick1330/ibex-harness/issues/1147)) ([89acc09](https://github.com/Rick1330/ibex-harness/commit/89acc096ee9cf46d8bdfae6559064991e9d9c4d0))
* **erasure:** make a memory forget erase its copies, not just its row ([4f839e1](https://github.com/Rick1330/ibex-harness/commit/4f839e1f4fe12b2bbebea646420d26c24edf918c))
* **evidence:** add ClickHouse relay sink pilot ([#968](https://github.com/Rick1330/ibex-harness/issues/968)) ([e633e48](https://github.com/Rick1330/ibex-harness/commit/e633e48983da4bb21f552343e89632172270cb1a))
* **evidence:** add session producer safety and typed acknowledgements ([#985](https://github.com/Rick1330/ibex-harness/issues/985)) ([1e2b346](https://github.com/Rick1330/ibex-harness/commit/1e2b3468647d295861f17fa0fc76c3786b1d1353))
* **evidence:** enforce producer proof and acknowledgement profiles ([#975](https://github.com/Rick1330/ibex-harness/issues/975)) ([07c3693](https://github.com/Rick1330/ibex-harness/commit/07c369343a8878409787196a465c105a0e76922a))
* **evidence:** use jcs-v1 payload digests ([#976](https://github.com/Rick1330/ibex-harness/issues/976)) ([e8fe8f1](https://github.com/Rick1330/ibex-harness/commit/e8fe8f1a84124bbc3a58770ef1da4de3f38876ff))
* **gates:** require step-up for org deletion and enforce retention windows ([3778902](https://github.com/Rick1330/ibex-harness/commit/3778902a0b100fb94128dc12e0cfa9ca2f1155bf))
* **idempotency:** add durable ledger for session termination ([#987](https://github.com/Rick1330/ibex-harness/issues/987)) ([7e4cfa2](https://github.com/Rick1330/ibex-harness/commit/7e4cfa210cc7ca00b967247a33f7e32204a5ee58))
* **idempotency:** extend durable ledger to remaining mutating paths ([#989](https://github.com/Rick1330/ibex-harness/issues/989)) ([e35d71b](https://github.com/Rick1330/ibex-harness/commit/e35d71b2e3c0c9ee04c833d0aab0057a19bdf49b))
* **idempotency:** fence remaining worker enqueue path ([#991](https://github.com/Rick1330/ibex-harness/issues/991)) ([4b50551](https://github.com/Rick1330/ibex-harness/commit/4b50551ca109886e0f94048ef3d1ca03bd672f82))
* **mcp:** add read-only operator gateway with policy enforcement (GAP-009) ([#1014](https://github.com/Rick1330/ibex-harness/issues/1014)) ([076f531](https://github.com/Rick1330/ibex-harness/commit/076f5311009243386ea2d8b3059fd708c282d962))
* **memory:** add provisional revision-fenced lifecycle and forget semantics ([#996](https://github.com/Rick1330/ibex-harness/issues/996)) ([57b3ece](https://github.com/Rick1330/ibex-harness/commit/57b3ece55ff21eda3b564e2fd38bf7052dc88279))
* **memory:** fuse parallel sparse and dense retrieval with RRF ([#1097](https://github.com/Rick1330/ibex-harness/issues/1097)) ([af5b74e](https://github.com/Rick1330/ibex-harness/commit/af5b74e91e3a45ed23eddca923679a1f9bd361f6))
* **memory:** graph lineage traversal and unresolved-conflict suppression (5.B.1–5.B.3) ([#1102](https://github.com/Rick1330/ibex-harness/issues/1102)) ([72848b2](https://github.com/Rick1330/ibex-harness/commit/72848b212184faed27071dec00f9c5804b61ab09))
* **memory:** initialize OpenTelemetry and instrument dependency calls ([#1129](https://github.com/Rick1330/ibex-harness/issues/1129)) ([8e17a04](https://github.com/Rick1330/ibex-harness/commit/8e17a044a4f2f302f8936d1bc6e28231745d6b31))
* **memory:** make unresolved-conflict suppression switchable ([#1124](https://github.com/Rick1330/ibex-harness/issues/1124)) ([7605b3e](https://github.com/Rick1330/ibex-harness/commit/7605b3e9e92ad22c3339b5625af226153047b7c9))
* **memory:** record, fence, and document the embedding identity (W10.3) ([742c10f](https://github.com/Rick1330/ibex-harness/commit/742c10fa7acd862e80cbd5cf8be4344be4df461c))
* **memory:** rerank the fused window with a cross-encoder ([#1099](https://github.com/Rick1330/ibex-harness/issues/1099)) ([6bbd538](https://github.com/Rick1330/ibex-harness/commit/6bbd5385e2deceece386d5d71bfdb4cbd9780a46))
* **memory:** retrieval-quality and agreement metrics (5.C.1a) ([#1108](https://github.com/Rick1330/ibex-harness/issues/1108)) ([664f4eb](https://github.com/Rick1330/ibex-harness/commit/664f4eb0853b7840bcc5b964c01c1ed26aa4aa2e))
* **memory:** unify idempotency on the shared PostgreSQL ledger (GAP-001) ([#1007](https://github.com/Rick1330/ibex-harness/issues/1007)) ([358dfa6](https://github.com/Rick1330/ibex-harness/commit/358dfa6fd55d5eee8611cf33a99a7d6b5afce99e))
* **observability:** make the ratified SLO measurable, alertable and honest ([#1198](https://github.com/Rick1330/ibex-harness/issues/1198)) ([100e5b4](https://github.com/Rick1330/ibex-harness/commit/100e5b42effb10224a69dfe2472f1d66abcd666e))
* **operator:** expose memory lineage in the memories read model ([#1095](https://github.com/Rick1330/ibex-harness/issues/1095)) ([78bfa12](https://github.com/Rick1330/ibex-harness/commit/78bfa12cd17ea08ea49f34a57fedbb5bac042833))
* **operator:** make the Directives surface live with operator.directives.versions.v1 ([#1089](https://github.com/Rick1330/ibex-harness/issues/1089)) ([9a628de](https://github.com/Rick1330/ibex-harness/commit/9a628de65812e7cda75141da13de965f0a613188))
* **operator:** make the Evidence surface live with operator.evidence.summary.v1 ([#1087](https://github.com/Rick1330/ibex-harness/issues/1087)) ([bcb7e8f](https://github.com/Rick1330/ibex-harness/commit/bcb7e8f80d3ae6431ccd54580b3eacd3091d6a4e))
* **operator:** make the Evidence tombstones tab live with operator.evidence.deletions.v1 ([#1092](https://github.com/Rick1330/ibex-harness/issues/1092)) ([98129b4](https://github.com/Rick1330/ibex-harness/commit/98129b4a601672bcf9f3ddb3739400d78e3d9e25))
* **ops:** make readiness, alerting and recovery evidence real (Stage 2) ([151261b](https://github.com/Rick1330/ibex-harness/commit/151261b9d9aa4671fd1218c4c702bfd7caf75f38))
* **proxy:** add additive PrincipalContext context seam ([#960](https://github.com/Rick1330/ibex-harness/issues/960)) ([ecefef0](https://github.com/Rick1330/ibex-harness/commit/ecefef00570618924f9cbdede7ff3c79d94c4742))
* **proxy:** add fail-closed policy snapshot runtime (GAP-002) ([#998](https://github.com/Rick1330/ibex-harness/issues/998)) ([745d3c2](https://github.com/Rick1330/ibex-harness/commit/745d3c28bd370c25de99b9752dc3a086d0f52158))
* **proxy:** add fail-closed Responses capability slice ([#994](https://github.com/Rick1330/ibex-harness/issues/994)) ([df4ba9a](https://github.com/Rick1330/ibex-harness/commit/df4ba9a96f6256b68b147d67ef8e8edca06edb18))
* **proxy:** emit deprecation headers for proxy routes ([b65f734](https://github.com/Rick1330/ibex-harness/commit/b65f7345d4ca35ce75942a44fd3c3a8e3b5a2293))
* **recovery:** make PITR evidence producible and honest ([d1afc53](https://github.com/Rick1330/ibex-harness/commit/d1afc534ffffd3ba84da9af438ee2e84996abfd5))
* register REST routes, add route-level tenant negatives, deliver alerts ([#1192](https://github.com/Rick1330/ibex-harness/issues/1192)) ([4e95511](https://github.com/Rick1330/ibex-harness/commit/4e95511a1d15ca52fcf95d257fbce8885e645cff))
* **relay:** add evidence relay daemon with PostgreSQL fence checker ([#1003](https://github.com/Rick1330/ibex-harness/issues/1003)) ([2dbe076](https://github.com/Rick1330/ibex-harness/commit/2dbe0765b5519e21c5523f4bcfa67f4b8e09819a))
* **release:** add the memory-context bundle and manifest status ([#1065](https://github.com/Rick1330/ibex-harness/issues/1065)) ([75eb90b](https://github.com/Rick1330/ibex-harness/commit/75eb90bc9926b2dbbc5bada38fbbe2fe4dd2efed))
* **release:** close stage 4 — console login, backup/PITR, error-path fixes ([5b6820a](https://github.com/Rick1330/ibex-harness/commit/5b6820aec49700b043da72af0e24ca2673a6a4a8))
* **release:** publish a digest-pinned release manifest ([#1057](https://github.com/Rick1330/ibex-harness/issues/1057)) ([34d750a](https://github.com/Rick1330/ibex-harness/commit/34d750abb693eae2e86052a309378e031f82844b))
* **release:** publish console by removing npm from the runtime image ([78926fd](https://github.com/Rick1330/ibex-harness/commit/78926fd9aa0c750138ae01b7c36748ae35c6f831))
* **release:** publish what the profile runs, and bind an SBOM to each image ([3342206](https://github.com/Rick1330/ibex-harness/commit/3342206c3f6a006ec654c0f15856056029552a9d))
* **security:** harden memory validity and protected MCP limits ([#936](https://github.com/Rick1330/ibex-harness/issues/936)) ([125fde3](https://github.com/Rick1330/ibex-harness/commit/125fde3da214649f319cb54e5f87b96f2ed3575c))
* **site:** rebuild public site on Nuxt 4 + Docus and move engineering docs ([#1029](https://github.com/Rick1330/ibex-harness/issues/1029)) ([72f706b](https://github.com/Rick1330/ibex-harness/commit/72f706b3982516bcc38378dde55d696ffa056171))
* **tenancy:** make the multi-tenant claim true ([6059212](https://github.com/Rick1330/ibex-harness/commit/6059212f62e6cda787dd72bdbbeb4af3e10b831f))
* **tenancy:** provision the capability logins, add the auth login and the bootstrap definers ([#1188](https://github.com/Rick1330/ibex-harness/issues/1188)) ([64ef661](https://github.com/Rick1330/ibex-harness/commit/64ef6619bbbf0eccaba3c7dd8e6b8e89812453d0))
* **w3:** erasure, deletion cascade, and memory tenancy ([#1152](https://github.com/Rick1330/ibex-harness/issues/1152)) ([df15390](https://github.com/Rick1330/ibex-harness/commit/df15390d613422d5d3898b823ee09a34d857c8ec))


### Bug Fixes

* **api,memory:** decouple metadata reads and revert the forget gate ([1e96926](https://github.com/Rick1330/ibex-harness/commit/1e9692675ec4511ee7302ff50c8db198b52889e8))
* **api,proxy:** ship the deprecation record and agree on what a proxy path is ([a0849f7](https://github.com/Rick1330/ibex-harness/commit/a0849f7744e2fd979fb2214da167180c67955bd3))
* **bench:** bind provenance to its corpus and close the review findings ([67770cc](https://github.com/Rick1330/ibex-harness/commit/67770cc2cef14359135b4d16081eec4991c0cb8c))
* **bench:** close the second review round and the scanner findings ([9fc1da4](https://github.com/Rick1330/ibex-harness/commit/9fc1da466b12a79b4e46baa923ec52047f2b0095))
* **benchmarks:** confine pii recall --output to safe directories ([#1041](https://github.com/Rick1330/ibex-harness/issues/1041)) ([1699fa2](https://github.com/Rick1330/ibex-harness/commit/1699fa2a6810f470fb029f6b1da0b62c283db953))
* **bench:** refuse contradictory identity and decode literal escapes ([df0582e](https://github.com/Rick1330/ibex-harness/commit/df0582e98c939199e4c9753e282451ee8883ada8))
* **ci:** align web smoke search-index limit with extract default ([#937](https://github.com/Rick1330/ibex-harness/issues/937)) ([7298e5e](https://github.com/Rick1330/ibex-harness/commit/7298e5ee7982b926630566c88830c99650c8eb37))
* **ci:** allowlist bundle-smoke idempotency keys in gitleaks ([efd5ad4](https://github.com/Rick1330/ibex-harness/commit/efd5ad46937fc4902a807ad0e15efa6e515f1761))
* **ci:** generate protos for the bundle, pin the base SHA, and retry pin lookups ([5d3619e](https://github.com/Rick1330/ibex-harness/commit/5d3619ece3683db0d2a796a6cd87770eae251e15))
* **ci:** narrow the bundle-smoke gitleaks allowlist ([1f1865a](https://github.com/Rick1330/ibex-harness/commit/1f1865a36a0e7f45ccdc07d2fe28cb0088fae8e1))
* **ci:** restore a green main (ISO-MCP error text, JTI marker TTL) ([#1106](https://github.com/Rick1330/ibex-harness/issues/1106)) ([f3bd085](https://github.com/Rick1330/ibex-harness/commit/f3bd085fd408fe9df278f4fd3b2af3f4117566ab))
* **ci:** stop reporting a GitHub API outage as a missing tracked issue ([#1110](https://github.com/Rick1330/ibex-harness/issues/1110)) ([03dec3f](https://github.com/Rick1330/ibex-harness/commit/03dec3f5fb5f61ec94f52afdf0fbf46523a64c96))
* **clickhouse:** separate migration and native test DSNs ([#982](https://github.com/Rick1330/ibex-harness/issues/982)) ([356baf1](https://github.com/Rick1330/ibex-harness/commit/356baf1d4f19585049e3e943ca07313a1e106c33))
* close the scanner findings and revert the migration isolation ([b39d5a6](https://github.com/Rick1330/ibex-harness/commit/b39d5a6ef63e2a2072eefceac353522e2044ad66))
* close the second review round, the advisory, and the scanner hotspots ([966c23c](https://github.com/Rick1330/ibex-harness/commit/966c23cc0e15465a2831d9c2a011509adda4989a))
* close the Stage 2 review round ([c017c9d](https://github.com/Rick1330/ibex-harness/commit/c017c9d5ce9214d3500037385ac6f68ab5a485a7))
* **config:** strip the AuthService CA before the required check ([ebe0131](https://github.com/Rick1330/ibex-harness/commit/ebe01311b57dcb2e99f33ea7354fdbe64d4f1652)), closes [#1143](https://github.com/Rick1330/ibex-harness/issues/1143)
* **console,api:** address the delayed Greptile findings from [#1070](https://github.com/Rick1330/ibex-harness/issues/1070), [#1072](https://github.com/Rick1330/ibex-harness/issues/1072), [#1074](https://github.com/Rick1330/ibex-harness/issues/1074), [#1076](https://github.com/Rick1330/ibex-harness/issues/1076) ([#1081](https://github.com/Rick1330/ibex-harness/issues/1081)) ([ccb88fc](https://github.com/Rick1330/ibex-harness/commit/ccb88fcffa614a063b1f34a6c07b595076470203))
* **console,backup:** close the third review round ([e11e8bf](https://github.com/Rick1330/ibex-harness/commit/e11e8bf967595eeacb9c0c0eb6002e9aa3978aa6))
* **console,backup:** make the refresh path work in production ([abeb638](https://github.com/Rick1330/ibex-harness/commit/abeb63848d388df3a62e699cd74afa92c1eace4f))
* **console,infra:** persist SSR refresh cookies and use a numeric image user ([7c0c7ff](https://github.com/Rick1330/ibex-harness/commit/7c0c7ff45c3580d35c09bf5f3fe2074023e6c88d))
* **console:** give every live surface its own clock ([#1093](https://github.com/Rick1330/ibex-harness/issues/1093)) ([0e07eaa](https://github.com/Rick1330/ibex-harness/commit/0e07eaa3ee76f0b89151528c4480951285fe4123))
* **data,docs:** catch escaped-literal DDL, lease run databases, correct the record ([7cd975b](https://github.com/Rick1330/ibex-harness/commit/7cd975b2d38875b9b032c9bd4df994e45683e0ca))
* **deps,console,backup:** patch the OpenTelemetry advisories and close round four ([d80dd54](https://github.com/Rick1330/ibex-harness/commit/d80dd54fc48472c7c0c59840a848a81e763ec82e))
* **deps:** bump Go modules flagged by govulncheck and Trivy ([7fff1a5](https://github.com/Rick1330/ibex-harness/commit/7fff1a5c1042d98ec2b4b4f9207d02537a3234fa))
* **deps:** bump x/net in the license-tools module ([404a13c](https://github.com/Rick1330/ibex-harness/commit/404a13cd0e8a1b14c9421b849cce985b73c7a5bd))
* **deps:** clear the OSV and Go toolchain advisories blocking CI ([#1176](https://github.com/Rick1330/ibex-harness/issues/1176)) ([a716e84](https://github.com/Rick1330/ibex-harness/commit/a716e84b9999a9d75384d0d9089997f378a23d0a))
* **deps:** resolve the disclosed @hono/node-server advisories ([b52cfed](https://github.com/Rick1330/ibex-harness/commit/b52cfed3660b9eb20d2eeb8f4e734d672bb99f1f))
* **deps:** resolve the disclosed hono advisories ([3c7532c](https://github.com/Rick1330/ibex-harness/commit/3c7532cdb3626d4b5dad11028e58667b909082a1))
* **docker:** upgrade zlib and musl in the Go runtime images ([c9d5e14](https://github.com/Rick1330/ibex-harness/commit/c9d5e1418e4e279bd01b451c67ecdf6e99b210f9))
* **drill:** add the missing case defaults and clear the scanner findings ([5145d8f](https://github.com/Rick1330/ibex-harness/commit/5145d8f2b5b6e9ba5ad8e45311cfe4c3cde2ca90))
* **erasure:** close the review findings and the complexity they added ([b697814](https://github.com/Rick1330/ibex-harness/commit/b697814dcb557a13c06802ca70c396c010e8f61c))
* **g0:** constrain memory conflict mode and evidence relay ([#943](https://github.com/Rick1330/ibex-harness/issues/943)) ([1934456](https://github.com/Rick1330/ibex-harness/commit/1934456860046b2f6322d7c09554d119c36fb433))
* **gates:** close the eight review findings, including a false claim ([7307a5b](https://github.com/Rick1330/ibex-harness/commit/7307a5b7ed18ebe1f74667e953c15d38b5872d3a))
* **gates:** close the validator disagreement and the script-trigger class ([e5bc9a8](https://github.com/Rick1330/ibex-harness/commit/e5bc9a8b8ea0889884fac3b91e0a8cec216f2144))
* harden G0 principal, idempotency, and fail-closed runtime controls ([#934](https://github.com/Rick1330/ibex-harness/issues/934)) ([393c8b7](https://github.com/Rick1330/ibex-harness/commit/393c8b7d24787531e8b9c522b22b3b258c4d8cff))
* **infra:** close host-network environment automation gaps ([#956](https://github.com/Rick1330/ibex-harness/issues/956)) ([3f2ceb1](https://github.com/Rick1330/ibex-harness/commit/3f2ceb10fdff919206f86ffc78ecd4f4605b4475))
* **lint:** split the CA validators and legacy TLS probe ([2693997](https://github.com/Rick1330/ibex-harness/commit/269399708d50472261401cfcf7aff05bb21aedfc)), closes [#1143](https://github.com/Rick1330/ibex-harness/issues/1143)
* **mcp:** scope the pylint disable with a disable/enable pair ([cb2fcd4](https://github.com/Rick1330/ibex-harness/commit/cb2fcd45b8c410b27a6473f6bf7686f17516db25))
* **memory:** fence historical conflict candidates by agent (GAP-007) ([#950](https://github.com/Rick1330/ibex-harness/issues/950)) ([a464300](https://github.com/Rick1330/ibex-harness/commit/a464300ac362be03e15d0df3f00d40161028cd29))
* **memory:** fence historical search capability ([#977](https://github.com/Rick1330/ibex-harness/issues/977)) ([b573043](https://github.com/Rick1330/ibex-harness/commit/b5730432d8e6bb5f92c814f5f560c8aad0fcbf72))
* **memory:** frame memories as data, quarantine injection, and gate the chat route ([#1196](https://github.com/Rick1330/ibex-harness/issues/1196)) ([4268200](https://github.com/Rick1330/ibex-harness/commit/4268200bf006391e9f6bdf4e3dfdeb70752530f9))
* **memory:** make the revision part of the identity and correct the runbook ([708a42d](https://github.com/Rick1330/ibex-harness/commit/708a42d6fd9ea7c3486362439c4fa409ecf1393c))
* **memory:** split the rerank window at the TEI client batch limit ([#1104](https://github.com/Rick1330/ibex-harness/issues/1104)) ([9dea3a0](https://github.com/Rick1330/ibex-harness/commit/9dea3a0e8a275a366814d7a6e596966a1915a69f))
* **migrations:** build the test values in SQL instead of in Go ([8102968](https://github.com/Rick1330/ibex-harness/commit/81029686455f49aff3dd9dc0e1566ac1cb631ab8))
* **migrations:** clear the scanner findings on the rehearsal tests ([64c5a98](https://github.com/Rick1330/ibex-harness/commit/64c5a9855c2ab8a1e736692ae4aaa1592fb62572))
* **observability:** keep exception text out of spans and logs (P0-18) ([#1166](https://github.com/Rick1330/ibex-harness/issues/1166)) ([4ab866b](https://github.com/Rick1330/ibex-harness/commit/4ab866b5f2419e21682a0ec08d8cd9bf213db5a8))
* **pitr:** close eleven review findings, four of them false claims ([de8243f](https://github.com/Rick1330/ibex-harness/commit/de8243fec0165d568a0c47dd2b9a27649d6845f9))
* **pitr:** derive the RPO from the restored frontier, not from archiver counters ([e704a9e](https://github.com/Rick1330/ibex-harness/commit/e704a9e0201435622b372c6d73a2774b9c1f1b02))
* **pitr:** make the evidence honest, and mark the old artefact superseded ([3aac4df](https://github.com/Rick1330/ibex-harness/commit/3aac4dfe3cf4d4c357b168a9eb8b5f819ee2792c))
* **pitr:** measure the replay fact on the cluster that was restored ([f5ea88d](https://github.com/Rick1330/ibex-harness/commit/f5ea88d4ea8c5596f8a90fdc53e102a60a34d843))
* **proxy:** pin three tenant reads that fail open under RLS ([#1183](https://github.com/Rick1330/ibex-harness/issues/1183)) ([51e971a](https://github.com/Rick1330/ibex-harness/commit/51e971a11e40cb51653d671f2e85d249379499d5))
* **quality:** hoist the flagged arguments and scope the pylint disable ([92a6d38](https://github.com/Rick1330/ibex-harness/commit/92a6d38de6dc0e99888916a2907f4ab037611bde))
* **quality:** suppress the Codacy false positives at the call site, not by file ([b5c9368](https://github.com/Rick1330/ibex-harness/commit/b5c93686481035f7f8dd878bcdf5b4f3893aa7f9))
* **relay:** suppress DL3025 for the healthcheck CMD only ([fb16a19](https://github.com/Rick1330/ibex-harness/commit/fb16a190d8ba31efbfddf9910055c0d851da8311))
* **release:** close the review findings on stage 4 ([a8df57a](https://github.com/Rick1330/ibex-harness/commit/a8df57ad53ac02267d6e02f3d0d04ab471f4be54))
* **release:** contain the validator's CLI paths and fail closed on an unknown option ([f9b1562](https://github.com/Rick1330/ibex-harness/commit/f9b1562bcbed589ff36671bb85856059edf49aca))
* **release:** fail a tag release that publishes nothing ([b758089](https://github.com/Rick1330/ibex-harness/commit/b7580893478c9823afa08352b8e26c9a0623d99f))
* **release:** follow IBEX_PORT, cover the console inputs, and stop publishing console ([ba8626d](https://github.com/Rick1330/ibex-harness/commit/ba8626dbaa7019a813cca573db0315d964bcec54))
* **repo:** match local-only files at any depth and cover the guard ([563f229](https://github.com/Rick1330/ibex-harness/commit/563f229db2b50034fb1a9acad9741ff424a38f2a))
* **review:** address CodeScene, Codacy and Greptile findings ([fca3c80](https://github.com/Rick1330/ibex-harness/commit/fca3c8091d6de00a435acd40f7cb2b6fa8894102)), closes [#1143](https://github.com/Rick1330/ibex-harness/issues/1143)
* **review:** repair the automated CodeRabbit changes ([0f4f400](https://github.com/Rick1330/ibex-harness/commit/0f4f400fe544d35499d7874662724244154934aa)), closes [#1143](https://github.com/Rick1330/ibex-harness/issues/1143)
* **scanners:** close the open Sonar, Codacy and CPD findings ([5b9ed56](https://github.com/Rick1330/ibex-harness/commit/5b9ed565023016049dd5ebee74417c1c68164564))
* **scripts:** drop the unused edge SAN capture ([b6588bb](https://github.com/Rick1330/ibex-harness/commit/b6588bbef3e0501b72909e2d894a3da6c627b10c)), closes [#1143](https://github.com/Rick1330/ibex-harness/issues/1143)
* **security:** require AuthService CA outside development, harden TLS certificate repair and key access, and honor Console healthcheck ports ([59fcd3f](https://github.com/Rick1330/ibex-harness/commit/59fcd3fdfd8bd5ee5103c2b30daa78ba07777d0c))
* **site:** bound mermaid load and render with a visible error deadline ([#1040](https://github.com/Rick1330/ibex-harness/issues/1040)) ([aa5a0f2](https://github.com/Rick1330/ibex-harness/commit/aa5a0f22237484b8702c33de66c99a05a68891ff))
* **tenancy:** repair the stacks and findings the PR exposed ([cf90667](https://github.com/Rick1330/ibex-harness/commit/cf906672d6b3ec694cc83cc7ca73ee09317ce09d))
* **tenancy:** share the capability assertion and close the remaining findings ([05a1e46](https://github.com/Rick1330/ibex-harness/commit/05a1e468f93df32170a78e6bcfec0b44e5a62bfb))
* **tests:** annotate the drill test's subprocess use ([39c7d77](https://github.com/Rick1330/ibex-harness/commit/39c7d775f4b858ac14682813fd49af12df55b0b3))
* **test:** satisfy the new-code scanner findings ([df7234f](https://github.com/Rick1330/ibex-harness/commit/df7234fe5523d710df7010fd602cb8cbc7b8f5c0)), closes [#1143](https://github.com/Rick1330/ibex-harness/issues/1143)
* **tests:** build the receipt key from a UUID, not a concatenation ([9bd92d1](https://github.com/Rick1330/ibex-harness/commit/9bd92d1df9d61bdbd98b0998d8b61e8394e64575))
* **tests:** remove SQL concatenation and the duplicate upload preamble ([dda56fa](https://github.com/Rick1330/ibex-harness/commit/dda56fafc2f76925dfe1b3fff2d6a22cae2498b9))
* **worker:** pin tenant paths and assume ibex_purge in the erasure saga ([#1184](https://github.com/Rick1330/ibex-harness/issues/1184)) ([843ff46](https://github.com/Rick1330/ibex-harness/commit/843ff46c174e650a9dae31a66e6ce648146fb871))
* **worker:** route the expired-lease sweep through its definer ([#1170](https://github.com/Rick1330/ibex-harness/issues/1170)) ([ac325f8](https://github.com/Rick1330/ibex-harness/commit/ac325f8ade2aa99db2c1df4cc4dbe2c24c4b511c)), closes [#1167](https://github.com/Rick1330/ibex-harness/issues/1167)


### Performance Improvements

* **bench:** add blocking Go benchmark gate and ratify proxy SLO (GAP-004) ([#1018](https://github.com/Rick1330/ibex-harness/issues/1018)) ([cd5bc3b](https://github.com/Rick1330/ibex-harness/commit/cd5bc3b64c7d0a530a7846c72ba424750d8021d7))
* **db:** index the operator list keys and checkpoint join ([#1072](https://github.com/Rick1330/ibex-harness/issues/1072)) ([aca0faf](https://github.com/Rick1330/ibex-harness/commit/aca0faf65b4df75b03b1900230aa12a51005b644))

## [0.1.9](https://github.com/Rick1330/ibex-harness/compare/v0.1.8...v0.1.9) (2026-10-04)


### Features

* **4.D.2:** certify Explore provenance and metadata Trace Inspector contract ([#911](https://github.com/Rick1330/ibex-harness/issues/911)) ([2411f73](https://github.com/Rick1330/ibex-harness/commit/2411f73910e80cd80aefdf22edfab9b8fcde05c5))
* **api:** mount operator metadata read authorization ([#893](https://github.com/Rick1330/ibex-harness/issues/893)) ([a041ed3](https://github.com/Rick1330/ibex-harness/commit/a041ed302bfc7966d94b6ce175fec655ced5263c))
* **auth:** complete 4.P.1 operator session lifecycle and mounted authorization assurance ([#900](https://github.com/Rick1330/ibex-harness/issues/900)) ([0f087d2](https://github.com/Rick1330/ibex-harness/commit/0f087d297dd9a6c1ccfd06ea138e022bb511b69a))
* **console:** add metadata-only D2 trace inspector ([#908](https://github.com/Rick1330/ibex-harness/issues/908)) ([e4525e3](https://github.com/Rick1330/ibex-harness/commit/e4525e3e8ee89de68ea156ec06b94190582ccf5b))
* **console:** connect authenticated tenant-scoped D1 overview (4.D.1) ([#906](https://github.com/Rick1330/ibex-harness/issues/906)) ([fc8735c](https://github.com/Rick1330/ibex-harness/commit/fc8735c3494a391dc5ddf9046cdede12bd38c9c0))
* **console:** enforce fail-closed preview boundary ([#892](https://github.com/Rick1330/ibex-harness/issues/892)) ([dbc82db](https://github.com/Rick1330/ibex-harness/commit/dbc82db9c45604c07f187967b9a083df592bd6d7))
* **operator-web:** transplant dashboard mock into Track D foundation ([#887](https://github.com/Rick1330/ibex-harness/issues/887)) ([4136bda](https://github.com/Rick1330/ibex-harness/commit/4136bda71c0f10b8faead4420ad02d680cbef348))


### Bug Fixes

* **pre-track-d:** close runtime assurance and e2e readiness gaps ([#903](https://github.com/Rick1330/ibex-harness/issues/903)) ([671b219](https://github.com/Rick1330/ibex-harness/commit/671b219fda2c32014e6849c87d7dafaff0ce1ab7))
* **proxy:** enforce fail-closed pre-track-d readiness controls ([#897](https://github.com/Rick1330/ibex-harness/issues/897)) ([df657fd](https://github.com/Rick1330/ibex-harness/commit/df657fd2436b6d7646b9c491b429a23634d22750))

## [0.1.8](https://github.com/Rick1330/ibex-harness/compare/v0.1.7...v0.1.8) (2026-09-20)


### Features

* **4.P.1:** partial Gate G1 — fail-closed policy, SecretUse, SSRF (F4-015–018) ([#845](https://github.com/Rick1330/ibex-harness/issues/845)) ([3ead9de](https://github.com/Rick1330/ibex-harness/commit/3ead9decde3b3be2c1bbaa1e91fb95f94b2a386d))
* **4.P.2:** canonical evidence plane and durable publication ([#848](https://github.com/Rick1330/ibex-harness/issues/848)) ([7ca25e6](https://github.com/Rick1330/ibex-harness/commit/7ca25e67791f266a3507af02aa4f69647f90b5c1))
* **4.P.3:** privacy, Retention, Deletion & Audit Governance ([#852](https://github.com/Rick1330/ibex-harness/issues/852)) ([9228c91](https://github.com/Rick1330/ibex-harness/commit/9228c91bc0a4dca7a569b51bf5bbb84fd25d066c))
* **4.P.4:** hybrid usage ledger and fail-closed spend caps ([#860](https://github.com/Rick1330/ibex-harness/issues/860)) ([9e177ac](https://github.com/Rick1330/ibex-harness/commit/9e177aca5db8e88fa8f38fd96e53667f5c20dd8e))
* **4.p.5:** production platform, recovery and supply chain ([#870](https://github.com/Rick1330/ibex-harness/issues/870)) ([eae9cf9](https://github.com/Rick1330/ibex-harness/commit/eae9cf9603f8943112e2cc421a09e9f3f5de8445))
* **api:** 4.P.0 operator runtime topology & environment contract ([#840](https://github.com/Rick1330/ibex-harness/issues/840)) ([f230bda](https://github.com/Rick1330/ibex-harness/commit/f230bdab077a96f96da5c7be45c99c034e217088))

## [0.1.7](https://github.com/Rick1330/ibex-harness/compare/v0.1.6...v0.1.7) (2026-09-14)


### Features

* **api:** add FastAPI management-plane skeleton with auth and error envelope (m4.A.1) ([#780](https://github.com/Rick1330/ibex-harness/issues/780)) ([f93cb7a](https://github.com/Rick1330/ibex-harness/commit/f93cb7ad6637a1d9df4d5eec36fcc8bfa39a160f))
* **api:** agent management API with default provider/model fields (m4.A.3) ([#791](https://github.com/Rick1330/ibex-harness/issues/791)) ([9919931](https://github.com/Rick1330/ibex-harness/commit/9919931eca016cb22fdf1253e5cd29ee870b0163))
* **api:** org-scoped provider credential management with envelope encryption (m4.A.5) ([#801](https://github.com/Rick1330/ibex-harness/issues/801)) ([93fed0e](https://github.com/Rick1330/ibex-harness/commit/93fed0e605a3da67e23ea66b746cd1cf3d11acae))
* **api:** organization and user management API with suspension propagation (m4.A.2) ([#785](https://github.com/Rick1330/ibex-harness/issues/785)) ([6028a2f](https://github.com/Rick1330/ibex-harness/commit/6028a2f71fc649c640ccf8ed2a3d2c528748f887))
* **api:** PAT management API with scoped permissions and gRPC revocation (m4.A.4) ([#797](https://github.com/Rick1330/ibex-harness/issues/797)) ([e2661d2](https://github.com/Rick1330/ibex-harness/commit/e2661d2ffafda08cc300feadbd1209a876de9a4b))
* **api:** rate limit configuration API with hot-path reload (m4.B.2) ([#808](https://github.com/Rick1330/ibex-harness/issues/808)) ([ad90879](https://github.com/Rick1330/ibex-harness/commit/ad90879619be411d64dfd86a46f86355f6acc256))
* **proxy,api:** per-org model routing policy (m4.C.2) ([#817](https://github.com/Rick1330/ibex-harness/issues/817)) ([26a071e](https://github.com/Rick1330/ibex-harness/commit/26a071eda60b00519e11d0e61b0cbf4e1c1e1023))
* **proxy,api:** provider fallback routing (m4.C.4) ([#822](https://github.com/Rick1330/ibex-harness/issues/822)) ([358baf3](https://github.com/Rick1330/ibex-harness/commit/358baf33d136c8c253e5cc10f2ce8afc52dc5ca6))
* **proxy:** atomic Lua hierarchical rate limiter agent→org→global (m4.B.1) ([#805](https://github.com/Rick1330/ibex-harness/issues/805)) ([cb7f1e1](https://github.com/Rick1330/ibex-harness/commit/cb7f1e14b17942813f084ee39074e4d00f488f0f))
* **proxy:** rolling error-rate circuit breaker per provider (m4.C.3) ([#820](https://github.com/Rick1330/ibex-harness/issues/820)) ([082d97d](https://github.com/Rick1330/ibex-harness/commit/082d97d3dae81afff259bf30f108d97126cddc13))


### Bug Fixes

* **api:** close 4.A.1 verification gaps (envelope, logs, CI) ([#782](https://github.com/Rick1330/ibex-harness/issues/782)) ([f0d922f](https://github.com/Rick1330/ibex-harness/commit/f0d922fe27c0335d01098f469253be733158fde4))
* **ci:** repair tagged release SBOM upload and docker caller perms ([#776](https://github.com/Rick1330/ibex-harness/issues/776)) ([2a91205](https://github.com/Rick1330/ibex-harness/commit/2a91205d899da115f2d6e9f11bea864938ee8e8d))
* **ci:** configure release-please signoff and harden DCO workflow env binding


### Documentation

* **roadmap:** redesign Phase 4 operator platform milestones (Track P/D/E) ([#831](https://github.com/Rick1330/ibex-harness/issues/831)) ([e00a167](https://github.com/Rick1330/ibex-harness/commit/e00a1678a9e8acbe86e7fc70a51c75465e2d9c71))

## [0.1.6](https://github.com/Rick1330/ibex-harness/compare/v0.1.5...v0.1.6) (2026-09-09)


### Features

* **context:** assemble context gRPC with L0-L2 degradation (m3.5.C.6) ([#712](https://github.com/Rick1330/ibex-harness/issues/712)) ([22267de](https://github.com/Rick1330/ibex-harness/commit/22267de5d396e791ba022c409f6c7ddfd097d354))
* **context:** context formatter with locked ordering and session nonce (m3.5.C.5) ([#707](https://github.com/Rick1330/ibex-harness/issues/707)) ([c780834](https://github.com/Rick1330/ibex-harness/commit/c78083463f1afe8234b6d025fa5b2412024fc49a))
* **context:** packer v2 — bounded DP knapsack (m3.5.C.4) ([#706](https://github.com/Rick1330/ibex-harness/issues/706)) ([621947d](https://github.com/Rick1330/ibex-harness/commit/621947d274607eab68d248a7ce09a1de59c16f35))
* **context:** parallel retrieval orchestration with three-way concurrency (m3.5.C.2) ([#696](https://github.com/Rick1330/ibex-harness/issues/696)) ([649fb61](https://github.com/Rick1330/ibex-harness/commit/649fb61aadbb87067eaf93ea4e8d7e123d4074c7))
* **context:** token budget calculator via generate-and-diff catalog (m3.5.C.1) ([#691](https://github.com/Rick1330/ibex-harness/issues/691)) ([c60091e](https://github.com/Rick1330/ibex-harness/commit/c60091ead883520882d574973f98772864ac5da4))
* **e2e:** 3.5.F.1 learning-loop suite on compose-test ([#752](https://github.com/Rick1330/ibex-harness/issues/752)) ([8a32047](https://github.com/Rick1330/ibex-harness/commit/8a320474103c7579b71efb9f893d0c9b6fcbfce0))
* **mcp-memory:** 3.5.E.2 search_memory and write_memory via memory HTTP ([#734](https://github.com/Rick1330/ibex-harness/issues/734)) ([96e7647](https://github.com/Rick1330/ibex-harness/commit/96e7647aaf54c19e55db652fd2f2d06d426f3b59))
* **mcp-memory:** 3.5.E.4 rate limit, auth breaker, audit gap-fill ([#749](https://github.com/Rick1330/ibex-harness/issues/749)) ([2087b7f](https://github.com/Rick1330/ibex-harness/commit/2087b7f542756db1ae2901ac4cec2d68ec8f8d2b))
* **mcp-memory:** deepen 3.5.E.1 protocol conformance coverage ([#730](https://github.com/Rick1330/ibex-harness/issues/730)) ([fbc5d85](https://github.com/Rick1330/ibex-harness/commit/fbc5d8567f52be4b581e8262dbe913e3e8879ba2))
* **memory:** 3.5.E.3 record_feedback via ledger + MCP/REST ([#746](https://github.com/Rick1330/ibex-harness/issues/746)) ([0fd9b3e](https://github.com/Rick1330/ibex-harness/commit/0fd9b3e849bddb857340d21b369e77c088ec4099))
* **memory:** relevance-gated composite scoring (m3.5.C.3) ([#704](https://github.com/Rick1330/ibex-harness/issues/704)) ([38a52b8](https://github.com/Rick1330/ibex-harness/commit/38a52b868d2fa4eac7c81567651ecabf494a53f7))
* **proxy:** embed ibex JSON metadata via response pipeline (m3.5.D.3) ([#719](https://github.com/Rick1330/ibex-harness/issues/719)) ([01b677a](https://github.com/Rick1330/ibex-harness/commit/01b677a8454d131d6f1dc612e6d11acfb8d45b2f))
* **proxy:** fail-open Go contextclient for AssembleContext (m3.5.D.1) ([#715](https://github.com/Rick1330/ibex-harness/issues/715)) ([f2b8e30](https://github.com/Rick1330/ibex-harness/commit/f2b8e30d3a78248a249b72b0094b5bfa5389c6f4))
* **proxy:** terminate sessions and enqueue extraction (m3.5.D.4) ([#721](https://github.com/Rick1330/ibex-harness/issues/721)) ([49f9e25](https://github.com/Rick1330/ibex-harness/commit/49f9e251b17ae58c03b83474f653aa7991672b5b))
* **proxy:** wire Assemble into dispatchProviderCompletion (m3.5.D.2) ([#717](https://github.com/Rick1330/ibex-harness/issues/717)) ([d6ada1e](https://github.com/Rick1330/ibex-harness/commit/d6ada1ea1519e2bf3251b9d339a131d3a8030d5e))
* **security:** 3.5.F.2 cross-tenant ISO-MCP isolation matrix ([#759](https://github.com/Rick1330/ibex-harness/issues/759)) ([ae0272d](https://github.com/Rick1330/ibex-harness/commit/ae0272d64580eda6c10b2b63bcdf769d24720f21))
* **web:** benchmarks suite UI parity and nested nav ([#700](https://github.com/Rick1330/ibex-harness/issues/700)) ([ad63f87](https://github.com/Rick1330/ibex-harness/commit/ad63f87bfcaec0617fd1a3dd9c6d691808770a37))
* **worker:** cost-tiered provider-agnostic extraction execution (m3.5.B.2) ([#684](https://github.com/Rick1330/ibex-harness/issues/684)) ([9dcefa8](https://github.com/Rick1330/ibex-harness/commit/9dcefa8d475ac52f7b7a6994d5643608bb5222bf))
* **worker:** extraction prompt v2 and structured output schema (m3.5.B.1) ([#680](https://github.com/Rick1330/ibex-harness/issues/680)) ([078d837](https://github.com/Rick1330/ibex-harness/commit/078d837de2d4ffcd269e67187e673980cd58e722))
* **worker:** extraction quality evaluation harness with gold-set (m3.5.B.4) ([#689](https://github.com/Rick1330/ibex-harness/issues/689)) ([7ac8595](https://github.com/Rick1330/ibex-harness/commit/7ac8595c21577438b63bfd7b660a1955f6b0c5b5))
* **worker:** incremental turn tracking and idempotency for batch extraction (m3.5.B.3) ([#686](https://github.com/Rick1330/ibex-harness/issues/686)) ([d14407d](https://github.com/Rick1330/ibex-harness/commit/d14407d3b7fbd914d0ce42a2f1b892a157700da5))


### Bug Fixes

* **ci:** restore tagged release docker permissions and workflow_call secrets ([#677](https://github.com/Rick1330/ibex-harness/issues/677)) ([e869eb9](https://github.com/Rick1330/ibex-harness/commit/e869eb912a36afe436863efc73f2ada4f856dc04))
* **ci:** scheduled Integration Race + weekly HNSW 1M reliability ([#743](https://github.com/Rick1330/ibex-harness/issues/743)) ([5c54aab](https://github.com/Rick1330/ibex-harness/commit/5c54aabefb12ad70d999e40bdbc3b8ff91af1885))
* **ci:** scope memory-integration to memory path filter ([#694](https://github.com/Rick1330/ibex-harness/issues/694)) ([47cc66e](https://github.com/Rick1330/ibex-harness/commit/47cc66e5ba0d7473c8caddc3122e0254e7e7cfce))
* **context:** close C.4/C.5 packer and formatter follow-up gaps ([#710](https://github.com/Rick1330/ibex-harness/issues/710)) ([4d479ad](https://github.com/Rick1330/ibex-harness/commit/4d479ad76aaf62285d5abf1c690d616e6ee9ee8f))

## [0.1.5](https://github.com/Rick1330/ibex-harness/compare/v0.1.4...v0.1.5) (2026-09-02)


### Features

* **memory:** add pgvector store with per-tx ef_search (m3.2.1) ([#599](https://github.com/Rick1330/ibex-harness/issues/599)) ([502d889](https://github.com/Rick1330/ibex-harness/commit/502d88948b92721e83f19c6601abcbfbb38173e0))
* **memory:** add pii detect/redact stage with Presidio (m3.c.1) ([#604](https://github.com/Rick1330/ibex-harness/issues/604)) ([9f45f82](https://github.com/Rick1330/ibex-harness/commit/9f45f8284f13be4a662d1c485281d6b151e581a2))
* **memory:** bootstrap service + scoring v2 (m3.2.1) ([#597](https://github.com/Rick1330/ibex-harness/issues/597)) ([7e1451a](https://github.com/Rick1330/ibex-harness/commit/7e1451a17d16f896a8d0a6969c24981a12088906))
* **memory:** content and near-duplicate detection (m3.c.2) ([#614](https://github.com/Rick1330/ibex-harness/issues/614)) ([0e85abe](https://github.com/Rick1330/ibex-harness/commit/0e85abecdc54621f951f5f9817b36e92117a57c2))
* **memory:** embed client, HNSW benches, and ADR-0053 (m3.2.1 PR-C) ([#600](https://github.com/Rick1330/ibex-harness/issues/600)) ([7f3f95d](https://github.com/Rick1330/ibex-harness/commit/7f3f95d90006e85e7f0f5f7ec7cc535f4ee560a9))
* **memory:** milestone 3.E.1 security integration suite ([#643](https://github.com/Rick1330/ibex-harness/issues/643)) ([f167d46](https://github.com/Rick1330/ibex-harness/commit/f167d4607d6ef97df71fda1b91cba9916841e862))
* **memory:** milestone 3.E.3 retrieval-quality benchmark sign-off ([#654](https://github.com/Rick1330/ibex-harness/issues/654)) ([b57e9a5](https://github.com/Rick1330/ibex-harness/commit/b57e9a567d6b5a189a446401c2e77f8c40103d1a))
* **memory:** multi-label memory classification write path (m3.C.4) ([#629](https://github.com/Rick1330/ibex-harness/issues/629)) ([e97eec0](https://github.com/Rick1330/ibex-harness/commit/e97eec0d344e7e08188ad270af7f5589d0245b65))
* **memory:** redis hot-cache read consumer and top-50 trim (m3.D.3) ([#640](https://github.com/Rick1330/ibex-harness/issues/640)) ([8119233](https://github.com/Rick1330/ibex-harness/commit/81192338e347cf2628d3350d875e14ad4cb75a65))
* **memory:** schema v2 expand — HNSW, quality columns (m3.1.1) ([#595](https://github.com/Rick1330/ibex-harness/issues/595)) ([06d8b74](https://github.com/Rick1330/ibex-harness/commit/06d8b74f461d47ce2fd645344df462dff2bbb87a))
* **memory:** semantic search read path with HNSW and GIN fallback (m3.D.1) ([#633](https://github.com/Rick1330/ibex-harness/issues/633)) ([194cb74](https://github.com/Rick1330/ibex-harness/commit/194cb74111e3ac732c83bde1a9563b2b94b7bea7))
* **memory:** temporal-interval-aware conflict detection (m3.c.3) ([#618](https://github.com/Rick1330/ibex-harness/issues/618)) ([6e5fd99](https://github.com/Rick1330/ibex-harness/commit/6e5fd9971ce3e4a77bba3b7e7367f0a3a1d98e1d))
* **memory:** wire composite scoring into search ranking (m3.D.2) ([#636](https://github.com/Rick1330/ibex-harness/issues/636)) ([675c733](https://github.com/Rick1330/ibex-harness/commit/675c7333fd6d3dacc01b16a114a05268a6a1b6e3))
* **memory:** write-path persistence and orchestration (m3.c.5) ([#625](https://github.com/Rick1330/ibex-harness/issues/625)) ([26ea098](https://github.com/Rick1330/ibex-harness/commit/26ea098e8fb66ded03b445b68e611df1acbfa260))
* **worker:** Celery worker skeleton with Redis broker and task routing (m3.5.A.1) ([4a6793b](https://github.com/Rick1330/ibex-harness/commit/4a6793b3081ac102fb5a601117a23e81a6e59dc4))
* **worker:** task observability and dead-letter handling (m3.5.A.2) ([#673](https://github.com/Rick1330/ibex-harness/issues/673)) ([e426b46](https://github.com/Rick1330/ibex-harness/commit/e426b464b18044aedba7e5595b9a1320d56a8400))


### Bug Fixes

* **ci:** remediate CVE-2026-56854 and close Scorecard security alerts ([#670](https://github.com/Rick1330/ibex-harness/issues/670)) ([39e4cff](https://github.com/Rick1330/ibex-harness/commit/39e4cffb0718fe165b92087b6f7dd29b581c6f26))

## [0.1.4](https://github.com/Rick1330/ibex-harness/compare/v0.1.3...v0.1.4) (2026-08-25)


### Features

* **db:** memory_labels multi-label join table (m2.5.G5.M2) ([#586](https://github.com/Rick1330/ibex-harness/issues/586)) ([28cdfe0](https://github.com/Rick1330/ibex-harness/commit/28cdfe09f5977cc2b2f4d3c6c858c730c1967052))
* **db:** temporal validity foundation on memories (m2.5.G5.M1) ([#581](https://github.com/Rick1330/ibex-harness/issues/581)) ([8bf93e3](https://github.com/Rick1330/ibex-harness/commit/8bf93e3782321cb5bf0e16b6f89bfc5d33032a51))
* **embedder:** add tei gpu embedding backend ([#561](https://github.com/Rick1330/ibex-harness/issues/561)) ([04f24f5](https://github.com/Rick1330/ibex-harness/commit/04f24f5457e2b1ebdfa0734c99e1ce9f770351f9))
* **embedder:** hosted-API embedding backend (OpenAI default, Cohere alternate) (m2.5.G4.M3) ([#576](https://github.com/Rick1330/ibex-harness/issues/576)) ([671212b](https://github.com/Rick1330/ibex-harness/commit/671212bbfc72bff03e9e6aa4bcb2e97ae20f19d3))
* **embedder:** interface registry and Python ABC (m2.5.G4.M1) ([#557](https://github.com/Rick1330/ibex-harness/issues/557)) ([640afed](https://github.com/Rick1330/ibex-harness/commit/640afed54c7eced8a11ade25745496a80108ed90))
* **embedder:** redis content-hash embedding cache (m2.5.G4.M4) ([#579](https://github.com/Rick1330/ibex-harness/issues/579)) ([a395502](https://github.com/Rick1330/ibex-harness/commit/a395502132eb4b987be07f1d41aedd61adfd4fbd))
* **mcp:** mcp server skeleton with stub tools and auth boundary (m2.5.G6.M1) ([#590](https://github.com/Rick1330/ibex-harness/issues/590)) ([50d161a](https://github.com/Rick1330/ibex-harness/commit/50d161af80b1faa8986880dd9d703a23e5fc9d84))
* **obs:** phase 2.5 exit gate with local LGTM stack (m2.5.G7) ([#592](https://github.com/Rick1330/ibex-harness/issues/592)) ([e66e359](https://github.com/Rick1330/ibex-harness/commit/e66e359e8ef6629ef5eebf903b2b5e0cebbc5df1))
* **proxy:** add model capability registry for per-model context and features (m2.5.G1.M2) ([#541](https://github.com/Rick1330/ibex-harness/issues/541)) ([3eb3ee5](https://github.com/Rick1330/ibex-harness/commit/3eb3ee599f240042b1ed4fbe7734cd43427c7161))
* **proxy:** anthropic provider adapter (2.5.G1.M1) ([#538](https://github.com/Rick1330/ibex-harness/issues/538)) ([65a6360](https://github.com/Rick1330/ibex-harness/commit/65a636006395f65aabab88c002209113e4c51f54))
* **proxy:** non-streaming response pipeline seam (m2.5.G3.M1) ([#551](https://github.com/Rick1330/ibex-harness/issues/551)) ([60c23b8](https://github.com/Rick1330/ibex-harness/commit/60c23b8d5b8637bebb88b5410a36ea9c3ad87482))
* **proxy:** openaicompatible adapter for self-hosted LLM backends (m2.5.G1.M3) ([#544](https://github.com/Rick1330/ibex-harness/issues/544)) ([033cb62](https://github.com/Rick1330/ibex-harness/commit/033cb62d805726827b2cd1782baa3e4182e6663a))
* **schema:** memory_relationships graph foundation (m2.5.G5.M3) ([#588](https://github.com/Rick1330/ibex-harness/issues/588)) ([80c8dae](https://github.com/Rick1330/ibex-harness/commit/80c8dae8bab4912b8a18a3c6d1a383982ef27dce))
* **tokenizer:** per-family token counting registry (m2.5.G2.M1) ([#548](https://github.com/Rick1330/ibex-harness/issues/548)) ([6a08719](https://github.com/Rick1330/ibex-harness/commit/6a08719ab53d360ae5d5797cf917afa725cf448b))

## [0.1.3](https://github.com/Rick1330/ibex-harness/compare/v0.1.2...v0.1.3) (2026-08-09)


### Bug Fixes

* **auth:** equalize ValidateToken miss cost and rate-limit peers ([#445](https://github.com/Rick1330/ibex-harness/issues/445)) ([7fcab0a](https://github.com/Rick1330/ibex-harness/commit/7fcab0a8023711cc7677d150e682d0aa679b3c55))
* **auth:** require CreateToken agent_id/user_id same-org bind ([#440](https://github.com/Rick1330/ibex-harness/issues/440)) ([790caba](https://github.com/Rick1330/ibex-harness/commit/790caba922a10da9ba3d75dfa0ad8e875ac2645a))
* **auth:** require CreateToken permissions subset of caller ([#437](https://github.com/Rick1330/ibex-harness/issues/437)) ([f9b8f3c](https://github.com/Rick1330/ibex-harness/commit/f9b8f3cb871a7ae5a8f01091fa218235d21baad9))
* **ci:** unblock semantic-pr-title on release PRs ([#404](https://github.com/Rick1330/ibex-harness/issues/404)) ([7e93d5f](https://github.com/Rick1330/ibex-harness/commit/7e93d5f31708975e010f0a44924bd0b42e903480))
* **db:** enforce composite org FKs on token subjects ([#443](https://github.com/Rick1330/ibex-harness/issues/443)) ([f8e9ea8](https://github.com/Rick1330/ibex-harness/commit/f8e9ea8ca0741c42c48d3557faf4085e5f608917))

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

- Idempotency-Key Redis dedupe for non-streaming chat (m2.1.6): optional `Idempotency-Key` header, `idempotency:{org_id}:{key}` claim/commit in `packages/idempotency`, replay on hit, `409 IDEMPOTENCY_KEY_REUSE` / `IDEMPOTENCY_IN_PROGRESS`, fail-open on Redis errors ([ADR-0035](engineering/adr/0035-chat-idempotency-key.md))
- Proxy overhead latency benchmark (m2.6.1): real warm-path Go stage microbenches, `BenchmarkProxyChatOverhead` with mockllm, ADR-0034, auth/provider duration histograms, k6 `full` profile chat path (`K6_USE_CHAT=1`), pinned `baseline.json`
- In-process mock LLM provider (`packages/provider/mockllm`): `IBEX_LLM_MODE=mock` returns immediate OpenAI-shaped JSON (smoke/chat 200 without OpenAI)
- Async trace emitter (m2.5.3): proxy `assembleTrace` + post-response bounded-pool emit into ClickHouse `Writer` (success, incomplete stream, provider failure); auth/directive stage latency on context; never blocks LLM response on CH errors
- ClickHouse client (`packages/clickhouse`, m2.5.2): concurrent batched `Writer` for `ibex.llm_traces` (clickhouse-go/v2, defaults batch 500 / flush 200ms), flush metrics, optional proxy shutdown drain when `CLICKHOUSE_DSN` is set
- ClickHouse `ibex.llm_traces` schema (m2.5.1): golang-migrate runner under `infra/migrations/clickhouse`, 90-day TTL MergeTree, ADR-0033, compose-test ClickHouse, `make clickhouse-migrate`
- Session idle-timeout sweeper (m2.4.4): proxy ticker marks stale `active` sessions `abandoned` under service-account RLS with advisory-lock multi-replica safety, Redis cache invalidation, metrics `ibex_proxy_session_sweeper_*`, and partial index `idx_sessions_active_updated_at` (migration `000011`)
- Proxy session lifecycle (m2.4.3): resolve/mint `X-IBEX-Session-ID` as sticky `external_id` before LLM forward; Redis session-state cache; response header on stream + non-stream; async non-dropping `AppendCheckpoint` pool drained on shutdown
- Session store (`packages/session`): Postgres `GetOrCreate` / `AppendCheckpoint` / `Complete` with org RLS; proxy constructs store when `POSTGRES_DSN` is set; metrics `ibex_proxy_session_*` (milestone 2.4.2)
- Sessions and checkpoints schema (`ibex_core.sessions` + `checkpoints`): Phase 2 subset with FORCE RLS, composite tenant FKs, append-only checkpoints, and extraction index ([ADR-0032](engineering/adr/0032-session-data-model.md); migration `000010`; milestone 2.4.1)
- System prompt injection (`packages/injection`): pure `Inject` for `system_first` / `system_append` / `user_prepend`; proxy applies resolved directive to `provider.Request.Messages` before `Complete` ([ADR-0031](engineering/adr/0031-system-prompt-injection.md); milestone 2.3.3)
- Directive resolver (`packages/directive`): Redis cache keyed `{org_id}:directive:{agent_id}` with Postgres fallback and pub/sub invalidation on `directive_updates:{org_id}`; proxy middleware resolves after agent verify (content stashed on context for 2.3.3 injection); metrics `ibex_proxy_directive_*`
- Directive schema (`ibex_core.directives` + `directive_versions`): immutable versions with `active_version_id` pointer, org RLS, 32KB content cap ([ADR-0030](engineering/adr/0030-directive-versioning.md); migration `000009`)
- Auth cache revoke hardening: tombstone installed before index removal; LRU lookup re-checks revocation before serving cached claims
- Token revocation propagation (`packages/revocation`): auth PUBLISH + proxy SUBSCRIBE on `ibex:token:revocations` with `token_id` events and `InvalidateByTokenID` ([ADR-0029](engineering/adr/0029-token-revocation-propagation.md)); metrics `ibex_auth_revocation_publish_total`, `ibex_proxy_revocation_invalidate_total`
- Auth cache (`packages/authcache`): in-process invalid-token bloom + claims LRU for proxy `ValidateToken` ([ADR-0028](engineering/adr/0028-auth-cache-design.md)); metrics `ibex_proxy_auth_cache_*`; header `X-IBEX-Auth-Cached` on LRU hits
- PR push hygiene guidance (see [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md)) encoding #350 CI/merge lessons
- Provider error mapping (`provider.MapError` / `MapProviderError` → `apierror.Error`) with sanitized details and `Retry-After` on upstream 429 ([ADR-0026](engineering/adr/0026-openai-client-design.md))
- Provider routing middleware (`ChatParse` + `ProviderRouting`) extracts model→provider lookup from the chat handler ([ADR-0025](engineering/adr/0025-llm-provider-abstraction.md))
- OpenAI streaming SSE dual-write forwarder (`stream=true`) with `StreamAccumulator`, flush-per-event, and stream metrics ([ADR-0027](engineering/adr/0027-streaming-dual-write.md))
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
