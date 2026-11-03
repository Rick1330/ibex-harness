# Architecture v2 References and Standards

**Status:** `specified`; references inform the design but do not prove IBEX implementation or compliance.

## Contracts and interoperability

- [Protocol Buffers](https://protobuf.dev/overview/) and [Buf breaking checks](https://buf.build/docs/breaking/) — internal contract evolution.
- [gRPC core concepts](https://grpc.io/docs/what-is-grpc/core-concepts/) — deadlines, metadata, cancellation, and status.
- [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0) — external REST description.
- [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457) — HTTP error-model reference.
- [Model Context Protocol](https://modelcontextprotocol.io/specification/latest) — tools, resources, transports, and authorization boundaries.
- [OpenTelemetry](https://opentelemetry.io/docs/specs/semconv/) — telemetry correlation conventions.

## Security and governance

- [NIST ABAC SP 800-162](https://csrc.nist.gov/pubs/sp/800/162/upd2/final) — subject/object/action/environment policy concepts.
- [NIST Zero Trust SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final) — continuous verification and least implicit trust.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
- [OWASP LLM Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html).
- [OWASP SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
- [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html).
- [W3C PROV-DM](https://www.w3.org/TR/prov-dm/) — provenance vocabulary.

## Reliability and operations

- [Google SRE SLOs](https://sre.google/sre-book/service-level-objectives/) — SLI/SLO/error-budget discipline.
- [Kubernetes probe semantics](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/).
- [PostgreSQL backup](https://www.postgresql.org/docs/current/backup.html), [Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/), and [ClickHouse backup](https://clickhouse.com/docs/operations/backup).
- [NIST SP 800-61](https://csrc.nist.gov/pubs/sp/800/61/r2/final) — incident handling.

## Memory and decision models

- [CoALA memory architecture](https://arxiv.org/html/2309.02427v3), [LoCoMo](https://aclanthology.org/2024.acl-long.747/), and [MemoryAgentBench](https://proceedings.iclr.cc/paper_files/paper/2026/hash/fd1eff9dd295df50a41f2521942fa31d-Abstract-Conference.html) — memory taxonomy and evaluation context.
- [Fastino GLiNER2.5-Decide](https://huggingface.co/fastino/GLiNER2.5-Decide), [release announcement](https://fastino.ai/blog/gliner-2-5-decide-open-weight-decision-model), and [artifact metadata](https://huggingface.co/api/models/fastino/GLiNER2.5-Decide) — candidate model facts and uncertainties.
- [ONNX Runtime quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) and [threading](https://onnxruntime.ai/docs/performance/tune-performance/threading.html) — deployment references, not portable SLOs.
- [Scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html) — reliability/calibration methodology.
- [Microsoft Presidio](https://microsoft.github.io/presidio/) — layered PII detection reference; not a guarantee of complete detection.
- [fastText](https://github.com/facebookresearch/fastText) — small closed-taxonomy classifier alternative.

External references are reviewed before implementation decisions and must be pinned to the applicable version or date when behavior is release-sensitive.
