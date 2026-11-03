# IBEX Harness: GLiNER2.5-Decide and Lightweight Decision Models

**Date:** 2026-10-03
**Scope:** Evaluate Fastino/GLiNER2.5-Decide and related CPU-friendly models for IBEX memory, routing, context assembly, PII, safety, and policy-adjacent decisions.

## Verdict

IBEX should adopt a **lightweight decision-model capability**, but it should not make GLiNER2.5-Decide the universal default and must never use it as the security authority.

The best architecture is:

```text
Deterministic identity, tenant scope, policy, budget, and capability checks
  → authorized feature/context snapshot
  → optional lightweight decision model
  → calibrated decision or abstention
  → deterministic policy/executor
```

GLiNER2.5-Decide is a credible candidate for English schema-driven intent, routing, priority, moderation, handoff, and multi-label classification. It is not a general LLM, does not provide open-ended reasoning, and should not be expected to explain its decisions or authorize actions.

The vendor reports **167.3 ms p50 CPU latency** for a short request on a 48-vCPU Intel Xeon. That is materially incompatible with IBEX’s stated target of less than 20 ms added proxy p99 if placed synchronously in the Go proxy. The model belongs in a warmed Python/ONNX sidecar, context plane, worker, or shadow path unless IBEX proves otherwise with a full-path benchmark.

## What is verified about GLiNER2.5-Decide

Fastino describes GLiNER2.5-Decide as an English, Apache-2.0, locally runnable encoder classifier. It accepts a finite candidate label/schema set at call time, supports single- and multi-label decisions, emits no generated tokens, and targets operational decisions such as intent, routing, moderation, severity, urgency, spam, and handoff.[1] [2]

Its constrained interface supports typed questions, permitted answers, cardinality, examples, descriptions, implications, exclusions, and ordinal constraints. This makes it more expressive than a simple fixed classifier. However, a label and confidence score are not evidence. High-impact workflows still need source spans, provenance, deterministic checks, and human review where appropriate.

Fastino reports 60.1–60.2% exact-match accuracy on its own 17-domain `fast-decisions` suite and 167.3 ms batch-1 CPU p50 on a 48-vCPU Xeon for a 64-token, two-head/15-label workload.[2] [3] These figures are not independent IBEX results. The benchmark does not establish calibration, p95/p99 latency, cold-start behavior, concurrency, memory use, multilingual quality, adversarial robustness, or policy correctness.

There are also artifact uncertainties. The release describes 340M parameters, while Hugging Face metadata for the repository reports approximately 486M F32 parameters. The encoder configuration has 512 positions, while release material mentions a 1,024-token latency measurement. IBEX must size and benchmark the exact pinned artifact rather than repeating headline figures.[1] [4]

The safe conclusion is that GLiNER2.5-Decide is a **specialist structured decision model**, not a general-purpose reasoning model or permission system.

## Where it fits in IBEX

### Memory

IBEX should not keep one undifferentiated vector memory. Use typed stores and projections:

- **Working/session memory:** ordered conversation, active goal, pending tool state, approvals, and run state. Retrieve by exact thread/run key.
- **Episodic memory:** append-only records of what happened, attempts, outcomes, and feedback.
- **Semantic memory:** atomic facts with subject, scope, valid interval, source, confidence, and supersession.
- **Profile/preferences:** explicit or confirmed user, agent, project, or organization preferences with field-level provenance.
- **Procedural memory:** reviewed skills, procedures, templates, and code kept in governed source/configuration systems rather than unreviewed semantic memory.
- **Project/repository context:** files and instructions tied to repository, branch, commit, path, and line provenance.
- **Relational/temporal memory:** entities, relations, observation time, valid intervals, and supersession projections.
- **Tool/evidence memory:** tool identity, version, authorization, hashes, timestamps, outputs, and provenance.
- **Safety/negative memory:** scoped denied actions, failed checks, revoked approvals, and unsafe assumptions with expiry.
- **Checkpoints:** complete durable run state kept outside semantic retrieval and accessed by exact key.

GLiNER2.5-Decide or a smaller classifier can label candidate memories, estimate intent, route retrieval profiles, rank review queues, and suggest importance/freshness categories. It must not decide tenant visibility, deletion, retention, authorization, or whether an untrusted fact becomes policy.

The memory lifecycle should remain:

```text
authenticated source
  → deterministic validation and PII handling
  → candidate extraction/classification
  → exact deduplication
  → near-duplicate candidate search
  → deterministic temporal checks
  → model-assisted ambiguity handling
  → quarantine/review or active projection
  → provenance-bearing retrieval
```

The existing IBEX design is directionally correct: PII/quarantine, exact hash deduplication, vector near-duplicate discovery, temporal conflict/supersession, labels, and tenant/agent filters should remain authoritative. A model can assist ambiguous cases, but it cannot silently override them.

### Routing and context assembly

A lightweight model is useful after hard filtering. The safe order is:

1. Authenticate the caller and verify tenant, agent, resource, residency, and policy.
2. Check budget, idempotency, rate, concurrency, and required provider capabilities.
3. Estimate tokens and context fit deterministically.
4. Build a tenant-authorized feature snapshot.
5. Use a classifier for intent, priority, complexity, retrieval profile, or escalation hints.
6. Select only from allowlisted compatible deployments.
7. Record the decision and fallback path.

Possible uses include:

- Select hot-cache versus durable memory retrieval.
- Choose a bounded context-packing profile.
- Classify request complexity or likely modality.
- Route low-risk intent categories to a model family.
- Prioritize review or human handoff.
- Rank already-authorized memory candidates.
- Identify likely structured-output or tool-use requirements.

It should not calculate exact token counts, claim provider capabilities, authorize tools, widen retrieval scope, or select a deployment that violates policy. Provider capability manifests and tokenizers remain the source of truth.

### PII and safety

Keep the existing hybrid PII strategy. Deterministic recognizers, regular expressions, checksums, context rules, and Presidio-style recognizers should remain the first layer. A neural NER model can improve recall or provide a second opinion, but non-detection is not proof of absence.

GLiNER2-PII is a possible additional span detector, but its published evaluation is limited and its reported precision is low relative to the importance of preventing leaks. Any uncertain or high-impact detection should redact conservatively or quarantine. Never send raw sensitive memory to a remote inference service without an explicit processing policy.

Small classifiers can also scan untrusted memory, retrieved documents, tool results, and web content for prompt-injection-like patterns. This is defense in depth only. Adaptive attacks have bypassed prompt-injection defenses in published research. The actual protection remains typed trust separation, least privilege, sandboxing, exact tool authorization, and human approval.

### Policy-adjacent decisions

Use classifiers and NLI models to propose typed attributes such as likely intent, sensitivity, contradiction, missing fields, or review risk. Then pass those attributes to deterministic policy evaluation.

Do not use them as the sole source of:

- Authentication.
- Tenant or agent isolation.
- Authorization or ACLs.
- Budget admission.
- Data residency.
- Deletion or legal hold.
- Egress permission.
- Irreversible tool approval.
- Security identity.

A model timeout, malformed output, stale artifact, missing scope, or low confidence must produce **deny, quarantine, no-route, or human review** depending on the operation. It must never produce a broader allow.

## Alternatives

GLiNER2.5-Decide is not automatically the best model for every task.

- **fastText or character-ngram/linear classifiers:** best for stable, high-volume closed taxonomies where tiny size, low CPU cost, simple retraining, and predictable behavior matter more than zero-shot label descriptions.
- **GLiNER2.5-small:** a 74M English candidate for entity extraction and classification when a smaller transformer is acceptable; benchmark it locally because the public card does not provide IBEX-relevant latency or accuracy evidence.
- **GLiNER2.5-multi-Decide:** candidate for multilingual triage, but reported decision results are on an English suite. Validate language by language.
- **MiniLM or TinyBERT cross-encoders:** useful for reranking a small top-K evidence set after HNSW/full-text retrieval.
- **Small NLI models:** useful for bounded entailment/contradiction checks, but scores are not calibrated authorization probabilities and candidate fan-out increases cost.
- **Multilingual MiniLM embeddings:** useful for prototype or centroid routing and semantic fallback, but similarity is not classification confidence and is never authorization.
- **Presidio plus deterministic recognizers:** retain for PII because it provides a layered recognizer model rather than relying on one neural checkpoint.

IBEX should benchmark these models on the same task harness rather than choosing from parameter count or marketing claims.

## Integration contract

Create an internal, pure, side-effect-free `DecisionService` with protobuf/gRPC. Provide an OpenAPI/JSON adapter only at an external boundary.

The request should include:

- Verified tenant and agent identity.
- Purpose and decision taxonomy.
- Deadline and request ID.
- Feature snapshot ID and bounded typed features.
- Schema/label ontology hash.
- Model alias or approved deployment reference.
- Policy epoch and trace ID.

The response should include:

- Decision or labels.
- Raw scores and calibrated probabilities where available.
- Abstention flag and reason.
- Alternatives and evidence spans where applicable.
- Model name, revision, digest, tokenizer, and preprocessing hash.
- Feature schema and calibration version.
- Latency, cache status, and degradation reason.
- Evidence ID linking to the redacted decision record.

Maintain four separate identities:

1. Contract major version.
2. Model semantic version.
3. Immutable artifact SHA-256/signature.
4. Feature/preprocessing schema hash.

Postgres should own model registry, approval, rollout, and last-known-good state. Object storage should hold immutable model artifacts and evidence. Redis may cache only pure, tenant-namespaced features or results whose keys include tenant, policy epoch, model revision/digest, tokenizer, schema, skill versions, and every applicable agent, purpose, feature-snapshot, input, and visibility dimension that can affect the value. Values proven independent of tenant, policy, identity, and visibility—such as immutable model metadata addressed by digest—may be shared; all other values are scope-bound. Stale or cross-scope cache output must never grant access or widen visibility.

## CPU deployment

Run the model in a preloaded Python process or ONNX Runtime sidecar near the context/memory plane. Load the tokenizer, model, optimized artifact, and session during process startup. Readiness should remain false until a smoke inference succeeds.

Use one bounded session per process initially. Tune model threads, process count, CPU pinning, and concurrency together. Batch size one is safest for interactive memory and PII work. Micro-batching is appropriate only for asynchronous extraction and must have a strict queue-delay limit.

Benchmark:

- Cold startup and warm inference.
- 32, 64, 128, 256, and maximum supported token lengths.
- Batch sizes 1, 2, 4, and 8 where relevant.
- Concurrency from one to saturation.
- FP32 versus dynamic INT8 or other validated quantization.
- Target CPU families and container limits.
- RSS, peak RSS, CPU, queue time, p50, p95, p99, errors, and timeouts.
- Task quality, PII recall, calibration, and abstention coverage.

ONNX Runtime provides optimization and quantization mechanisms, but those features do not establish a universal latency or accuracy guarantee. Every optimized artifact needs numerical parity and workload validation.

## Rollout plan

1. **Benchmark:** compare fastText/linear, GLiNER2.5-small, GLiNER2.5-Decide, and multilingual alternatives on anonymized IBEX memory and routing data.
2. **Offline replay:** pin preprocessing, labels, thresholds, model digest, CPU profile, sequence limits, and expected outputs.
3. **Shadow:** run against the same authorized feature snapshot with no writes, tool calls, reservations, or policy effects.
4. **Low-risk canary:** use sticky organization/agent cohorts for reversible routing or triage only.
5. **Promotion:** require quality, calibration, tail latency, resource, and isolation gates. Keep policy-adjacent use advisory or deny-only until parity is proven.
6. **Re-evaluation:** repeat on model, tokenizer, schema, policy, corpus, runtime, or CPU changes.

A fallback state machine should be explicit:

- Security, scope, policy, budget-integrity, or artifact-integrity failure → deny or no-route.
- Optional model timeout → last-known-good verified model, deterministic rule, or abstain/review.
- Memory/context dependency failure → safe directive-only or verified hot-cache context.
- Low confidence or missing feature → abstain/review.
- Authoritative model-registry lookup unresolved: for provider routing or model selection, return no-route and do not select a deployment; for memory ranking or context enrichment, omit the advisory result and continue only with deterministic authorized ranking or directive-only context; for PII/safety classification, quarantine or conservatively redact; for extraction/learning writes, defer or dead-letter without writing a candidate; for policy-adjacent review, return deny or human review. Never use a stale registry/cache result to authorize, widen visibility, reserve budget, delete data, or execute a tool.

## References

[1]: https://huggingface.co/fastino/GLiNER2.5-Decide "Fastino GLiNER2.5-Decide model card"
[2]: https://fastino.ai/blog/gliner-2-5-decide-open-weight-decision-model "Fastino GLiNER2.5-Decide announcement"
[3]: https://huggingface.co/datasets/fastino/fast-decisions "Fastino fast-decisions benchmark"
[4]: https://huggingface.co/api/models/fastino/GLiNER2.5-Decide "Hugging Face GLiNER2.5-Decide artifact metadata"
