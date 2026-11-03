# LLM-Agent Trace Inspector: World-Class Memory-Assembly Panel

## Executive decision

The panel should use a **three-layer progressive-disclosure audit surface**: a pinned run summary, a comparative candidate matrix, and an exact selected-item trace. The matrix is the primary operator surface because it supports scanning, sorting, comparison, copying, and export. The selected-item trace is an Explain-style hierarchy that preserves computation lineage without forcing every operator to read a deep tree.

The design must keep four semantics separate: **score contribution**, **rank transition**, **resource cost**, and **selection outcome**. A similarity score is not a final rank, a recency multiplier is not causal importance, a budget exclusion is not irrelevance, and missing telemetry is not an empty result. This separation is the core safety rule for a high-stakes debugging product.

## 1. Evidence and design principles

### 1.1 Use exact trace data as the authority

Elasticsearch and OpenSearch expose structured explanation objects with a numeric value, description, match state, and recursively nested details [1] [2]. OpenSearch also separates subquery scores, normalization, and score combination in hybrid search [3]. These patterns are directly relevant to an operator debugging a weighted ranker.

**Recommendation.** Treat the deterministic production trace as authoritative. Use tables, diverging bars, waterfalls, rank lanes, and trees as views over that trace. Type every displayed value as one of `exact_trace`, `derived_metric`, `policy_parameter`, `measured_metric`, `estimate`, or `surrogate_attribution`.

### 1.2 Keep additive scoring separate from ranking and allocation

Algolia documents sequential ranking and tie-breaking rather than a single universally additive score [4]. Qdrant and Pinecone distinguish first-stage retrieval from reranking [14] [17] [20]. Elasticsearch’s Reciprocal Rank Fusion combines rank positions without requiring comparable score scales [18].

**Recommendation.** Use four adjacent lanes:

1. **Score:** raw values, transforms, weights, and contributions.
2. **Rank:** retrieval rank, rerank rank, final rank, and signed movement.
3. **Resources:** tokens, latency, reservations, truncation, and allocation.
4. **Outcome:** included, budget-excluded, filtered, failed, or unknown.

Do not use a score bar to represent a token constraint or an exclusion outcome unless the production formula explicitly models it as a score term.

### 1.3 Overview first, details on demand

The information-seeking pattern of overview, zoom/filter, and details on demand is appropriate here. Datadog’s trace view combines a critical trace header with navigable span and waterfall views [21]. Explanation APIs warn that deep explanations can be expensive [1] [2].

**Recommendation.** Make the first viewport useful without expansion. Pin the summary strip, show a stable row schema, and expand only selected rows or a small comparison set. Advertise hidden details with explicit labels such as `Show score calculation` or `Show exclusion arithmetic`; never hide the only explanation of an operator-critical decision behind hover.

## 2. Prior-art comparison

| Prior art | Strength | Limitation | Decision for ibex-harness |
|---|---|---|---|
| Elasticsearch/OpenSearch Explain | Exact nested computation lineage [1] [2] | Poor scanability across many candidates; expensive at scale | Use in selected-item detail, not as the default list |
| OpenSearch hybrid Explain | Shows normalization and score combination [3] | Does not make heterogeneous scores globally comparable | Show raw stage, normalization, formula, and combined value |
| Algolia ranking | Makes sequential/tie-break ranking explicit [4] | Not a general additive-score model | Keep rank transition separate from additive contribution |
| LineUp/TRIVEA | Interactive multi-attribute ranking and rank-change analysis [5] [6] | Slope views become dense for large lists | Use sortable matrix; reserve arrows/slope views for selected subsets |
| SHAP/LIME | Familiar local-attribution and waterfall vocabulary [7] [8] | Can be post-hoc, unstable, or inconsistent with execution | Use only for exact additive traces; label surrogates clearly |
| ViSFA/recommender explainability | Scalable aggregation and interactive mental-model building [9] [10] | Aggregation can hide rare failures | Add quantiles, strata, sample counts, and exemplar drill-down |
| FICO reason codes | Ordered plain-language reasons for individual outcomes [11] [12] | Reasons can oversimplify interactions | Show up to four ordered reason chips linked to exact trace nodes |
| Query-debugging research | Distinguishes filtering from ranking and “why not?” questions [16] | A flat list encourages invalid comparisons | Use mutually exclusive pipeline-status groups |
| LlamaIndex/Pinecone | Explicit token limits, reranking, and allocation [19] [20] | Resource cost is not semantic relevance | Make budget exclusion a first-class outcome |
| Datadog/OpenTelemetry | Trace hierarchy, phase timing, metadata, and sampling [21] [23] [24] | Telemetry can be sampled, delayed, or redacted | Display completeness and provenance beside metrics |

## 3. Recommended visualization grammar

| Debugging question | Primary encoding | Required labels | Avoid |
|---|---|---|---|
| Why did the score arise? | Component table, signed bars, selected-item waterfall | Raw value, transform, weight, contribution, formula, version | One opaque composite bar |
| Why is this rank? | Rank lane with retrieval/final ranks and signed delta | Rank stage, tie rule, `Δrank` | Treating rank as similarity |
| Why was it omitted? | Outcome badge plus budget ledger and displacement chain | Status, reason code, capacity at decision | Missing row or zero score |
| How did freshness matter? | Category-conditioned decay curve | Category, age, half-life, multiplier, evaluation time | Universal “freshness” score |
| Where did time/tokens go? | Stage ledger or small waterfall with numeric table | Phase, duration, tokens, measured/estimated | One unexplained total |
| How do two items differ? | Aligned two-column diff and delta column | Shared scale, delta, driver | Radar chart or independent scales |

## 4. Assembly-level summary strip

Keep the strip pinned above the candidate list. A concrete layout is:

```text
MEMORY ASSEMBLY | Included 8/42 | Budget 5,120/8,192 tokens
Retrieval 82 ms · rerank 146 ms · pack 9 ms · generation 1.8 s
Selected 8 · budget-excluded 6 · filtered before score 25 · failed 3
Final-rank moves 3 · Trace v17 · sampled: no · warning: 2 late spans
```

The strip must answer selection, budget, latency, and evidence-completeness questions before any row is opened. Show ratios as numerator/denominator. Use warning states only for actionable conditions such as budget pressure, stale data, missing spans, redaction, or limited replayability. Datadog’s trace header and OpenAI’s latency guidance support separating identity, duration, input tokens, output tokens, and request phases [21] [22].

## 5. Candidate matrix and row mockups

### 5.1 Collapsed row: comparison surface

```text
[✓] #03 episodic/task-state “User is preparing the migration plan…”
    retrieval #08 → final #03  Δrank +5  cosine 0.812  score 0.734
    age 4.2 h · retention 0.88 · 420 tokens · allocated 420 · 38 ms
    WHY: +recency | +semantic | included in context
```

The collapsed row shows inclusion state, category, short title or redacted excerpt, retrieval rank, final rank, score, similarity, age, token count, allocation, and a concise reason. Original rank remains visible even when the operator sorts by another field.

### 5.2 Expanded row: evidence surface

```text
Identity
  Memory ID · source · tenant/case · created · last used · trace/span ID
Stage values
  retrieval rank 8 · raw cosine 0.812 · rerank score 0.67 · final rank 3
Score calculation
  semantic 0.812 × 0.60 = 0.4872
  recency 0.882 × 0.25 = 0.2205
  confidence 0.92 × 0.10 = 0.0920
  weighted total = 0.8012; displayed score = 0.734 after configured transform
Freshness
  category episodic · age 4.2 h · half-life 24 h · offset 0 · base 0.5
  retention = 2^(-age/half-life) = 0.885 · evaluated at timestamp T
Resources
  estimated 420 tokens · realized 398 · allocated 420
  retrieval 14 ms · rerank 20 ms · formatting 4 ms
Why / policy
  reason IDs · formula version · policy version · raw JSON · copy trace
```

The exact formula must be the production formula. The UI must preserve unrounded internal values and expose rounded numbers only as display derivatives. Use an Explain-style tree for deeper nested calculations, but keep the component table as the numerical authority.

## 6. Rank-versus-similarity divergence

Make the default table contain separate, sortable columns:

| Candidate | Retrieval rank | Similarity | Final rank | Δrank | Driver | Outcome |
|---|---:|---:|---:|---:|---|---|
| A | 8 | 0.81 | 3 | +5 | recency + reranker | included |
| B | 2 | 0.89 | 11 | −9 | category decay + diversity | budget-excluded |

Call the metric `cosine`, `dot product`, `BM25`, or `cross-encoder score`, not generically `relevance`. Score normalization research warns that score scales may be incompatible, while Qdrant documents metric-specific semantics [14] [15].

When a row is selected, open a mini-trace:

```text
retrieval order #8 → final order #3
+0.18 rank lift from category recency
+0.07 from reranker
−0.02 from duplicate/diversity adjustment
Budget selection uses final rank: included
```

Use a signed text delta as the primary scan signal. Use an annotated arrow only for the selected row or a filtered divergence subset. Numeric rank and delta remain authoritative.

## 7. Category-dependent recency and half-life

Show a normalized retention value together with its interpretation:

```text
Retention 0.50   episodic · half-life 24 h · age 24 h
formula R=2^(-age/half-life) · offset 0 h · base 0.5 · evaluated 2026-09-13 16:00Z
```

Milvus documents exponential-decay parameters and the meaning of the half-life scale [13]. FICO’s explanation model illustrates why broad policy weights are not the same as instance-level impact [11] [12].

The default row must show category, half-life, age, and retention. The expanded inspector should show a decay curve with age on the x-axis and multiplier on the y-axis, one line per category, with the selected memory marked. Add a policy-version link and warnings for missing timestamps, clock skew, stale evaluation time, or changed category configuration.

Do not call the multiplier “importance.” It is a configured transform. If values are not semantically comparable across categories, label them `category-relative`.

## 8. Excluded-candidate reasoning

Use four mutually exclusive, collapsible groups:

1. **Included in context:** scored, selected, and allocated.
2. **Scored but budget-excluded:** scored and ranked, then lost during allocation.
3. **Filtered before scoring:** failed scope, schema, policy, deduplication, hard threshold, or availability checks.
4. **Evaluation failed or unavailable:** timeout, missing embedding, index/provider error, or missing telemetry.

This separation follows explainable-ranking and query-debugging work that distinguishes filtering from ranking and “why did it appear?” from “why did it not?” [16]. Elasticsearch also separates matched status from score explanation [1].

A budget-excluded row should look like:

```text
[×] scored, budget-excluded   final rank #06   score 0.691
    estimated 1,240 tokens · remaining at decision 900 · allocated 0
    reason: budget overflow after 5 items
    counterfactual: included if budget +340 tokens
    displaced by: #07 180 tokens; #09 260 tokens; reserve 400 tokens
```

Filtered candidates must show `score: not evaluated`, not zero. Failed candidates must show missingness and failure state. Keep redacted snippets by default where content is sensitive; expose arithmetic before revealing full text.

## 9. Sorting, precision, and interaction design

### Sorting

Provide one explicit diagnostic sort control with final rank, retrieval rank, stage-specific similarity, weighted score, recency contribution, token cost, latency, and allocation. Show active key and direction. Preserve original rank. Offer named presets **Why selected** and **Most similar** rather than a hidden switch between incomparable orders. Interactive-dynamics research supports sorting as a central analytical operation but warns that hidden or confusing controls introduce errors [28].

### Exact values and tooltips

Decision-critical values remain in the row. Hover and keyboard focus may open a short exact-value card with raw value, normalization, weight, contribution, units, and rounding. Enter/click pins the card and opens a detail drawer. Never put the only exclusion explanation or action inside a hover tooltip; Nielsen Norman Group specifically warns against hiding vital information in transient UI [27]. Escape or copy all displayed values as text/JSON.

### Display-only component toggles

Allow operators to hide or show score contribution, recency, similarity, category, token cost, latency, and reason. The control must state `Display only; ranking unchanged`. Any control that changes computation must be separate, require an explicit recompute, show assumptions, and produce a diff.

### Counterfactuals

A `What if?` action forks the observed run and changes one declared variable: half-life, score weight, token budget, cutoff, top-k, or one memory. Show observed and simulated states side by side with score delta, rank delta, inclusion changes, token changes, and latency estimates. Mark every result `simulated`, list assumptions, preserve the observed trace, and disable side effects by default. Counterfactual visualization research supports improved interpretation but also reports additional inspection time and the risk of over-interpreting hypothetical results [29].

### Pairwise diff

Pin exactly two memories and align fields on a shared scale:

| Field | Candidate A | Candidate B | Delta / driver |
|---|---:|---:|---|
| Retrieval similarity | 0.81 | 0.89 | B +0.08 |
| Recency retention | 0.88 | 0.42 | A +0.46 |
| Final weighted score | 0.734 | 0.691 | A +0.043 |
| Retrieval rank → final rank | 8 → 3 | 2 → 11 | A favored by recency |
| Tokens / allocation | 420 / 420 | 1,240 / 0 | B displaced by capacity |
| Outcome | included | budget-excluded | final rank plus cost |

Start with six to ten diagnostic rows. Highlight material differences with text, shape, and a signed delta. Do not use radar charts or independent scales.

## 10. Large-N behavior

| Candidate count | Default view | Detail path |
|---:|---|---|
| 1–20 | Detailed sortable rows, selected waterfalls, recency curves | Expand multiple rows and compare two |
| 21–200 | Component heatmap, rank distribution, outliers, grouped exclusions | Select a row for exact trace |
| >200 | Quantiles, histograms, category summaries, latency distributions, stratified samples | Inspect exemplars by rank, category, reason, and latency percentile |

Virtualize lists, paginate raw payloads, stream summaries before details, and cache immutable spans. Aggregate views must show sample size, quantiles, completeness, and an `inspect exemplars` path. Sampling should be stratified by rank, category, inclusion state, exclusion reason, and latency percentile. ViSFA demonstrates compact interactive summaries at large scale [9].

## 11. Information architecture and trace semantics

The assembly panel is a child operation in the trace, not a detached diagnostic card. The header shows parent operation, span and trace IDs, start/end time, duration, status, sampling state, and replayability. Nested phases are retrieval, embedding if instrumented, reranking, recency transform, packing, serialization, model queue/TTFT if available, and generation. OpenTelemetry’s span model provides the correct parent-child structure [23].

Recommended order:

1. Pinned summary strip.
2. Included candidate list.
3. Collapsed scored-but-budget-excluded group.
4. Collapsed filtered-before-score group.
5. Collapsed failed/unknown group.
6. Selected-item drawer with waterfall or stage table, recency curve, Explain tree, raw JSON, and copy/export.
7. Optional pairwise and counterfactual modes that never mutate the observed trace.

## 12. Accessibility and precision

Accessibility must be an investigation mode, not an afterthought. Provide landmark headings, a concise textual summary, keyboard navigation, sortable/filterable tables, a textual event timeline, and synchronized selected-row state. Each row header is a disclosure target with `aria-expanded` and `aria-controls`; expansion supports Enter and Space; focus is restored after updates.

Do not rely on color. Pair inclusion, rank movement, errors, redaction, and uncertainty with text, icons, shapes, or position. Provide `Expand all`, `Collapse all`, `Copy evidence`, and downloadable CSV/JSON/trace bundle controls. Screen-reader research emphasizes overview, orientation, targeted navigation, and hypothesis testing [31] [32].

## 13. Privacy, security, and governance

Treat prompts, retrieved documents, tool arguments, outputs, and trace metadata as sensitive and potentially hostile. Redact before persistence where feasible. Enforce tenant and case authorization. Show effective identity and permissions in the header. Log every reveal, export, replay, and counterfactual. Render retrieved or external text inert: do not execute links, HTML, code, or tool calls from the inspector.

Maintain separate sanitized and privileged raw views. Use short retention for privileged payloads. Display redaction gaps instead of implying completeness. OWASP identifies prompt injection risks including sensitive-data disclosure and unauthorized function invocation [37]. Grafana documents that redaction may not cover all responses, streaming chunks, or model-thinking blocks [36].

## 14. Empty, partial, and failure states

| State | Visible treatment |
|---|---|
| No candidates retrieved | Show `retrieved 0`, query, index snapshot, and cutoff |
| Filtered before scoring | Show count, predicates, and reason codes |
| Retrieved but excluded | Show score/rank and allocation reason |
| Loading | Show current phase; never infer zero |
| Partial/late spans | Show last event time, missing phases, and ingestion lag |
| Unsampled | Show `trace unsampled` and unavailable fields |
| Context truncated | Show configured window, requested, retained, and dropped tokens |
| Provider/tool timeout | Show failure code, phase, elapsed time, and retry semantics |
| Redacted/unauthorized | Explain that evidence is hidden, not absent |
| Evaluation failed | Mark score/allocation `not evaluated` |

OpenTelemetry notes that head sampling may miss errors, while tail sampling can retain errors or high-latency traces at greater cost [24]. OpenAI documents that input, output, and reasoning tokens compete for the same context window [38]. The UI must distinguish `not retrieved`, `retrieved but excluded`, `unknown because telemetry is missing`, and `truncated by context`.

## 15. Reproducibility and implementation contract

Persist an immutable run manifest containing prompt/template identity, model/provider version, sampling parameters, tool and retrieval inputs/outputs, embedding and index version, candidate set, score formula, category half-lives, allocator policy, code/environment identifiers, timestamps, and redaction/sampling state. Provide replay and provenance diff.

Every candidate should carry stable identifiers and typed fields:

```text
run_id, trace_id, span_id, candidate_id, stage, status,
retrieval_rank, retrieval_metric, retrieval_score, rerank_score, final_rank,
score_terms[], formula_version, policy_version, category, age, half_life,
recency_factor, token_estimate, token_realized, token_allocated,
remaining_budget_at_decision, reason_code, counterfactual,
latency_by_phase[], completeness, redaction_state
```

Move expensive decomposition off the UI thread. Virtualize lists and paginate raw payloads. Show ingestion lag, dropped-span count, sampling policy, late events, and whether time is wall-clock, queue, provider, tool, or client-side. OpenTelemetry and Langfuse support this provenance-first direction [23] [33] [34].

## 16. Acceptance criteria

The panel is not world-class until an operator can answer these questions without reading raw logs:

- What was selected, and how many tokens were used?
- What was the raw retrieval metric and final rank?
- Why did rank and similarity diverge?
- What exact category half-life and policy version were applied?
- Was the candidate filtered, scored but budget-excluded, included, or unevaluable?
- Which candidates displaced an omitted memory?
- Which phase consumed time and tokens?
- Is the evidence exact, estimated, sampled, delayed, redacted, or simulated?
- Can the operator compare two candidates and copy the evidence?
- Can a keyboard and screen-reader user perform the same investigation?

## 17. Final committed recommendations

### Best pattern for weighted-score breakdown
Use a **selected-item additive waterfall backed by an expandable Explain-style tree and exact component table**. The waterfall provides directional scanability, the table provides numerical fidelity, and the tree preserves computation lineage. For non-additive, lexicographic, fused, or gated rankers, use a stage table instead of a waterfall.

### Best pattern for rank-versus-similarity divergence
Use a **sortable audit matrix with separate retrieval rank, metric-specific similarity, final rank, and signed `Δrank`, plus a selected-row annotated base-to-final mini-trace**. The matrix is authoritative for comparison; the mini-trace explains one divergence without filling every row with arrows.

### Best pattern for excluded-candidate reasoning
Use **four mutually exclusive collapsible pipeline-status groups—Included, Scored but budget-excluded, Filtered before scoring, and Failed/unknown—linked by stable candidate identity to one unified audit timeline**. Show score and displacement arithmetic only for scored candidates, predicate failures for pre-score candidates, and explicit missingness for failures.

## References

[1]: https://www.elastic.co/docs/api/doc/elasticsearch/operation-explain "Elasticsearch: Explain a document match result"
[2]: https://docs.opensearch.org/latest/api-reference/search-apis/explain/ "OpenSearch: Explain API"
[3]: https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/explain/ "OpenSearch: Hybrid search Explain"
[4]: https://www.algolia.com/doc/api-reference/api-parameters/ranking/ "Algolia: Ranking parameter"
[5]: https://pmc.ncbi.nlm.nih.gov/articles/PMC4198697/ "LineUp: Visual Analysis of Multi-Attribute Rankings"
[6]: https://arxiv.org/html/2308.14622v1 "TRIVEA: Transparent Ranking Interpretation using Visual Analytics"
[7]: https://shap.readthedocs.io/en/latest/example_notebooks/api_examples/plots/waterfall.html "SHAP: Waterfall plot documentation"
[8]: https://arxiv.org/abs/1602.04938 "Why Should I Trust You? Explaining the Predictions of Any Classifier (LIME)"
[9]: https://arxiv.org/html/2001.08379v2 "ViSFA: Interactive Visualization for Explaining Feature Attribution"
[10]: https://arxiv.org/html/2305.11755v3 "Visualization for Recommendation Explainability"
[11]: https://www.myfico.com/credit-education/blog/reason-codes "FICO: Credit score reason codes"
[12]: https://www.myfico.com/credit-education/whats-in-your-credit-score "FICO: What's in my FICO Scores?"
[13]: https://milvus.io/docs/exponential-decay.md "Milvus: Exponential Decay"
[14]: https://qdrant.tech/course/essentials/day-1/distance-metrics/ "Qdrant Essentials: Distance Metrics"
[15]: https://www.ccs.neu.edu/home/jaa/papers/MontagueAs01b.pdf "Relevance Score Normalization for Metasearch"
[16]: https://homes.cs.washington.edu/~leibatt/static/papers/gathani_debugging_CHI_2020.pdf "Debugging Database Queries: A Survey"
[17]: https://qdrant.tech/documentation/search-precision/reranking-semantic-search/ "Qdrant: Reranking Semantic Search"
[18]: https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion "Elasticsearch: Reciprocal Rank Fusion"
[19]: https://developers.llamaindex.ai/typescript/framework/modules/data/memory/ "LlamaIndex: Memory"
[20]: https://www.pinecone.io/learn/series/rag/rerankers/ "Pinecone: Rerankers and Two-Stage Retrieval"
[21]: https://docs.datadoghq.com/tracing/trace_explorer/trace_view/ "Datadog: Trace View"
[22]: https://developers.openai.com/api/docs/guides/latency-optimization "OpenAI: Latency Optimization"
[23]: https://opentelemetry.io/docs/concepts/signals/traces/ "OpenTelemetry: Traces"
[24]: https://opentelemetry.io/docs/concepts/sampling/ "OpenTelemetry: Sampling"
[25]: https://carbondesignsystem.com/components/accordion/usage/ "Carbon Design System: Accordion"
[26]: https://design.va.gov/components/accordion/ "VA Design System: Accordion"
[27]: https://www.nngroup.com/articles/tooltip-guidelines/ "Nielsen Norman Group: Tooltip Guidelines"
[28]: https://homes.cs.washington.edu/~jheer/files/interactive-dynamics.pdf "Interactive Dynamics for Visual Analysis"
[29]: https://arxiv.org/html/2401.08822v1 "Counterfactual Visualization to Support Visual Causal Inference"
[30]: https://ceur-ws.org/Vol-4073/BEHAIV2025_CRV_6.pdf "Comparing Visual Tools for Pairwise Comparisons"
[31]: https://vis.csail.mit.edu/pubs/rich-screen-reader-vis-experiences/ "Rich Screen Reader Experiences for Accessible Data Visualization"
[32]: https://dl.acm.org/doi/full/10.1145/3557899 "Accessibility of Data Visualizations for Screen Reader Users"
[33]: https://opentelemetry.io/blog/2024/llm-observability/ "OpenTelemetry: LLM Observability"
[34]: https://langfuse.com/docs/observability/overview "Langfuse: Observability and Application Tracing"
[35]: https://dl.acm.org/doi/fullHtml/10.1145/3589806.3600039 "Integrated Reproducibility with Self-describing ML Models"
[36]: https://grafana.com/docs/grafana-cloud/observe-and-act/agent-observability/privacy-and-security/pii-and-secrets-redaction/ "Grafana: PII and Secrets Redaction"
[37]: https://genai.owasp.org/llmrisk/llm01-prompt-injection/ "OWASP LLM01:2025 Prompt Injection"
[38]: https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them "OpenAI: Understanding and Counting Tokens"
