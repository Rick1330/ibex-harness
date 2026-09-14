# Designing a Composite-Score Memory-Assembly Debugging Panel

## Executive position

The panel should be a **rank-ordered, audit-ready table** for the production memory assembly, not a dashboard of competing visualizations. The authoritative final order must remain stable and unmistakable. Each included memory should expose its exact composite score, five weighted contributions, raw retrieval similarity, token cost, category-conditioned recency, provenance, and eligibility state without conflating those quantities. Excluded candidates should remain attached to the same assembly run, but in separately labeled groups for **minimum-relevance filtering** and **token-budget exclusion**. Latency and token accounting belong in an assembly-health strip, not in the quality score.

The proposed score contract is:

```text
composite_score =
    0.40 × relevance
  + 0.25 × recency
  + 0.20 × usefulness
  + 0.10 × confidence
  + 0.05 × access_frequency
```

All five inputs must be shown as raw input, normalized value, configured weight, and weighted contribution. The panel must label the composite as a heuristic or calibrated score according to the actual implementation. It must never call the composite a probability or an authority signal unless calibration evidence supports that terminology.[50]

The strongest prior art supports a table-plus-mark design: fixed-order horizontal contribution segments for cross-row comparison, numeric fields for exactness, an expandable score-provenance tree for audit, and a selected-item waterfall only where a real signed delta or baseline-to-final narrative exists. Elasticsearch and OpenSearch explanations establish the value of nested formula provenance but also warn that raw explanation trees are expensive and verbose.[1] [3] Algolia establishes the need to show rank criteria separately from any additive score because its documented ranking model is sequential tie-breaking rather than one scalar sum.[5] [7] LineUp establishes the value of weighted stacked bars, slope-like rank changes, exact values, alternative rankings, and saved comparison states for multi-attribute ranking.[63]

The report uses source labels and confidence deliberately. **Official product documentation** is treated as high confidence for the documented behavior of that product. **Academic HCI/visualization papers** are treated as high confidence for the studied interaction or perceptual principle, but not as proof that this exact product will produce the same outcome. **Published design teardowns** are treated as medium confidence for practical layout guidance. **Community writeups** are treated as medium confidence and are used to illustrate practitioner patterns rather than establish universal rules. Where a source is regulator, government, standards, or design-system documentation, it is identified precisely and its confidence is weighted for the claim being made.

## 1. Prior art for composite weighted scores

### 1.1 What prior art actually transfers

The panel is not a generic model-explanation surface. It has three simultaneous audiences: an operator who needs to know what was injected, an engineer who needs to know why an item outranked another, and an auditor who needs to reconstruct the exact assembly decision. Those audiences need different levels of detail. The transferable pattern is therefore not “show an explanation,” but **show a compact decision record with progressively deeper provenance**.

| Source or pattern | Source type and confidence | Transferable pattern | Limitation for this panel |
|---|---|---|---|
| Elasticsearch Explain API [1] and Elastic’s scoring writeup [2] | Official product documentation and official product technical writeup; high confidence | Nested `value`/`description`/`details` trees make factor-level score provenance inspectable | A raw tree is too verbose for comparing many memories; it is document-local |
| OpenSearch Explain API [3] | Official product documentation; high confidence | Expandable match status and recursive score details support audit-level explanation | OpenSearch warns that explanation is expensive; it should be on demand |
| OpenSearch hybrid-search explanation [4] | Official product documentation; high confidence | Separates raw vector score, normalization, and combined score, and recognizes result-set context | A single-document explanation cannot fully explain set-relative normalization |
| Algolia Ranking Info and ranking criteria [5] [7] | Official product documentation; high confidence | Shows criterion-specific metadata and makes ordered rank decisions inspectable | Sequential tie-breaking is not the same as this panel’s additive five-weight model |
| SHAP waterfall and force plots [8] [9] | Official product documentation; high confidence | Baseline-to-output narration, signed contributions, top-N display, and collapsed low-impact features | A fixed non-negative weighted sum is not a signed local attribution; default waterfall semantics would mislead |
| FICO category breakdown [11] | Official product documentation; high confidence | Familiar weighted-category score decomposition and local-factor framing | Its domain-specific score semantics and caveats do not transfer automatically |
| LIME [10] and the recommendation-explainability survey [12] | Academic HCI/visualization literature; high confidence | Match explanation scope to user task; use tables, feature views, stacked bars, and heatmaps for compare/debug tasks | Explanations remain scoped and local; they do not establish causal validity |
| Stacked-bar guidance [16] | Published design teardown; medium confidence | Fixed segment order and horizontal layout make totals and row-level comparison practical | Non-baseline segments are harder to compare precisely |
| Waterfall guidance [17] | Community writeup; medium confidence | Appropriate for a starting quantity plus signed changes to an ending quantity | It is not the primary view for five positive fixed weights |

The table should show **weighted contributions**, not raw component values, in the visible bar. A raw value answers “what was the feature?” A weighted contribution answers “how much did this feature contribute to the composite?” Both are necessary, but they are not interchangeable. A relevance value of `0.75` and a weighted relevance contribution of `0.30` must not occupy the same unlabeled visual channel.

The main list should use a fixed segment order matching the configured weights: **relevance, recency, usefulness, confidence, access frequency**. The legend, screen-reader labels, tooltips, and expanded formula must preserve that order. The bar must have a common 0–1 composite scale for the trace, while the adjacent numeric score remains the authoritative exact value. A stable scale is more important than making each row visually fill its own width.

### 1.2 Weighted score, raw similarity, and rank are different objects

The panel must expose three distinct quantities:

| Quantity | Meaning | Scope | Display rule |
|---|---|---|---|
| Raw retrieval similarity | The retriever’s native match signal, such as vector distance transformed by the retrieval engine or lexical relevance | Retrieval method and candidate set | Show as a separate labeled value with metric, direction, and transform when available |
| Composite score | The configured five-weight assembly score after normalization and category-conditioned transforms | Assembly configuration and candidate set | Show as exact score plus weighted-contribution bar |
| Authoritative final rank | The actual production injection order after eligibility and packing rules | Final assembly run | Show as a persistent rank badge and keep it stable under diagnostic sorting |

OpenSearch’s hybrid explanation is especially important here: normalization and combination depend on result-set context, so a normalized relevance value cannot be silently presented as raw similarity.[4] Google’s feature-attribution documentation likewise warns that local attributions are baseline-relative and instance-specific.[13] The panel should therefore state the normalization scope in the expanded view, for example: `Relevance normalized within this retrieval result set; raw vector score = 0.82; transform = 1 / (1 + distance)`.

### 1.3 Why the default is a table, not a chart-only score wall

A score wall optimizes overview but loses rank, identity, exact values, and eligibility state. A pure explanation tree optimizes auditability but makes cross-row comparison difficult. A chart-only design also makes it too easy to mistake a segment’s visual order for the production order. A rank-ordered table with bars supplies a stable row geometry, exact values, and a compact visual comparison. The recommendation-explainability survey supports choosing table-plus-quantitative-mark forms for identify, compare, and debug tasks.[12] Ranked-list research supports familiar position and length encodings rather than bubbles or packed areas for stable list comparison.[56]

The default list should therefore include:

1. `Rank` — the authoritative production injection order.
2. `Memory` — short label, stable ID, category, and provenance marker.
3. `Composite` — exact score and fixed-scale five-segment weighted-contribution bar.
4. `Raw similarity` — exact retrieval signal, separate from the composite.
5. `Tokens` — estimated or actual contribution to the assembly budget.
6. `State` — included, filtered, or budget-excluded status where applicable.

## 2. Rank-versus-similarity divergence

### 2.1 Divergence is a first-class debugging question

The most consequential failure mode is a memory with high retrieval similarity appearing below a lower-similarity memory after recency, usefulness, confidence, or access frequency are applied. The interface must not hide that movement. It should retain the authoritative final order while showing a **diagnostic raw-similarity position** as a secondary reference.

Each included row should show a small raw-similarity rank marker and a connector to its final-rank position. The connector is not an alternative ordering; it is an explanation of movement. An upward movement means the assembly promoted the memory relative to retrieval. A downward movement means the assembly demoted it. The row must still be read top-to-bottom in production order.

| Divergence question | Required evidence | Best default display |
|---|---|---|
| Why did memory A outrank memory B? | Rank gap, five contribution deltas, raw similarity, eligibility state | Pairwise diff drawer with aligned A/B columns and signed deltas |
| Why did a lower-similarity memory move up? | Raw-similarity position, final rank, component contributions | Connector from raw position to final rank plus contribution bar |
| Was the difference caused by retrieval or assembly? | Raw score provenance, normalization, category half-life, weights | Expanded score contract with separate retrieval and assembly sections |
| Did packing change the visible order? | Authoritative rank, packing order, token cost, residual budget | Separate `rank order` and `injection/packing order` labels |
| Is the ordering actually lexicographic? | Tie-break criteria and exact comparisons | Explicit rank policy, not an additive-bar interpretation |

Elasticsearch, OpenSearch, Solr, and Lucene all provide evidence trees that expose child factors and match/non-match states.[1] [3] [18] [19] Solr’s `explainOther` is particularly relevant as a precedent for comparing why another document ranks differently.[18] A published Lucidworks debugging example shows that a surprising rank difference can be isolated to term frequency and field normalization rather than an intuitive “better match” explanation.[20] These sources support a **difference-first** diagnostic, not a full dump of every factor for every row.

### 2.2 The pairwise diff

A pairwise diff opens on shift-click of two memories or from a `Why above this?` action. It uses fixed A/B columns, not two independent tooltips, so the operator does not have to remember values. The diff contains:

| Field | Memory A | Memory B | A minus B |
|---|---:|---:|---:|
| Authoritative final rank | 2 | 5 | `-3` positions |
| Raw similarity | 0.62 | 0.84 | `-0.22` |
| Relevance contribution | 0.248 | 0.336 | `-0.088` |
| Recency contribution | 0.240 | 0.100 | `+0.140` |
| Usefulness contribution | 0.160 | 0.120 | `+0.040` |
| Confidence contribution | 0.090 | 0.070 | `+0.020` |
| Access-frequency contribution | 0.030 | 0.020 | `+0.010` |
| Composite score | 0.768 | 0.646 | `+0.122` |
| Token cost | 84 | 190 | `-106` |
| Eligibility | Included | Included | — |

The explanatory sentence should be generated from the actual numbers: **“A outranks B because its recency, usefulness, confidence, and access-frequency gains outweigh B’s 0.088 relevance-contribution advantage.”** If packing also matters, the interface should state that separately: **“This score comparison does not determine token-budget admission.”**

Pairwise explanations fit the distinction among pointwise, pairwise, and listwise explanations in explainable information retrieval.[22] The SIGIR study of search explanations found that concise explanations can improve transparency, trust, and search efficiency.[21] Those findings justify a concise first explanation with an expandable full audit trail, not a paragraph of unexplained model language.

### 2.3 Small N and large N

For **small N, approximately 5–10 candidates**, display every included row with all five colored or patterned contribution segments, exact values, raw similarity, final rank, token cost, and visible rank-movement connectors. There is enough vertical space for direct comparison. The excluded groups can also show every candidate without virtualization.

For **medium N, approximately 9–30 candidates**, show the total five-segment bar for every row, but expand full component labels only for the top rows, the selected row, and the compared rows. Use virtualization only when row count or explanation payload makes rendering expensive.

For **large N, 50 or more candidates**, keep the authoritative rank column and exact composite column visible, use virtualized rows, and offer a diagnostic heatmap or component filter as a secondary view. The heatmap must retain row rank and memory identity; it must not replace the ranked table. Full score provenance remains on demand. Aggregate distribution summaries may show how many candidates were filtered, scored, packed, and excluded, but must not erase item-level evidence.

The display policy is therefore progressive rather than adaptive in semantics: the same evidence exists at every N, but its default density changes. The production order never changes because N becomes large.

## 3. Category-conditional metrics

### 3.1 Recency is a category-conditioned ranking signal, not truth decay

Recency must be shown as a model component and interpreted through the memory category. A factual memory, procedural instruction, preference, behavior, and episodic event do not share one meaningful freshness schedule. The panel should show **age**, **category**, **category-specific half-life**, and **age divided by half-life** alongside the normalized recency score.

A half-life should be called a half-life only when the implemented decay curve reaches `0.5` at that age. Search-engine decay documentation shows that decay depends on curve family and parameters such as origin, offset, scale, and decay.[59] [60] If the implementation uses a different curve or an arbitrary scale, the UI must expose the actual parameters and avoid implying a biological or hard-expiry interpretation.

| Category | Required contextual fields | Interpretation copy |
|---|---|---|
| Factual | As-of time, source/provenance, category half-life | “Low recency lowers freshness contribution; it does not prove the fact is incorrect.” |
| Procedural | Version, last validation, hard-expiry or revalidation rule | “Decay is a freshness signal; version or validation status controls operational validity.” |
| Preference | Observation age, evidence count, confidence | “This is an observed preference, not a guaranteed current preference.” |
| Behavioral | Event count, observation window, aggregation rule | “The score summarizes observed behavior in a defined window; it is not a trait claim.” |
| Episodic | Exact event time and neighboring session context | “Chronology is primary; old does not mean expired unless policy says so.” |

Google Trends documentation is a useful official-product precedent for bounded indices that require an explicit reference frame and denominator.[14] It supports the requirement to label the scope of normalized recency rather than present a bare number. Google Data Studio and Tableau documentation support labeled reference lines and bands for medians, percentiles, and ranges, but the panel must not label a cohort percentile band as a confidence interval.[57] [58]

### 3.2 Two recency views, not one overloaded axis

The expanded row should offer two explicit toggles:

- **Model contribution:** normalized recency on the common 0–1 component scale, used in the composite.
- **Category-relative age:** `age / half-life`, where `1.0` means one category half-life old.

An optional third view shows wall-clock age. These views must not switch axes silently. A same-category cohort median or percentile band may be overlaid only when the cohort definition and sample size are visible. Mixed-category bands are misleading because category-specific half-lives encode different policy expectations.

A recency row might read:

```text
Recency       0.72 contribution × 0.25 = 0.180
Category      procedural
Age           18 days
Half-life     30 days
Age / H       0.60 half-lives
Curve         exponential; offset 0; score = exp(-ln(2) × age/H)
```

The interface must state whether the timestamp is event time, ingestion time, or last update time. Temporal ambiguity is a debugging defect, not merely a tooltip detail. A recent ingestion of an old event must not be visually mistaken for recent evidence.

### 3.3 Recency must not masquerade as exclusion

A low recency contribution is not the same as a minimum-relevance failure. A recent but irrelevant memory may be filtered before composite scoring. An old but relevant memory may remain included with a low recency contribution. Exclusion must be explained in the eligibility section, while recency remains in the score section. This separation prevents the operator from treating a policy choice as a feature value.

The panel should test three adversarial cases in validation: an old factual memory that remains high-ranked, a recent low-relevance candidate that is filtered, and two memories with equal recency scores but different category half-lives. These cases reveal whether the UI preserves the semantic distinction.

## 4. Exclusion reasoning

### 4.1 The candidate funnel

Excluded candidates must stay in the assembly view, but they must not be blended into the included ranking. Use a compact funnel:

```text
Retrieved  →  Filtered  →  Scored  →  Ranked  →  Packed
  64             12          52         52         8
```

Each stage shows count, stage latency, and a click target that filters the candidate list. The groups are:

1. **Included** — scored, ranked, and packed into the final context.
2. **Filtered before scoring** — failed minimum relevance; composite score was not computed.
3. **Scored but excluded by token budget** — passed relevance, received a composite score and authoritative candidate rank, but did not fit the packing budget.

This distinction is directly supported by search-engine filter semantics: filter context is binary and does not affect scores, while scored query clauses affect relevance.[27] [29] It is also supported by CI and moderation interfaces that preserve visible skipped or removed states while exposing the causal condition or reason.[24] [25] [26] [31] [32]

### 4.2 Required row evidence by exclusion type

| Candidate state | Visible row | Expanded evidence | Must not imply |
|---|---|---|---|
| Included | Final rank, composite, contribution bar, raw similarity, token cost | Full score contract, recency context, provenance, packing position | That rank is the same as raw retrieval position |
| Filtered before scoring | Raw similarity, minimum-relevance threshold, comparison result, `Composite: not computed` | Retrieval query, metric direction, threshold policy, candidate timestamp | That it had a low composite score |
| Scored but token-budget excluded | Raw similarity, composite, authoritative candidate rank, token cost, cumulative usage, boundary marker | All five components, budget estimate/actual, packing heuristic, nearest included candidate | That it was irrelevant or never eligible |

Reason chips must contain text, not only color or icons. Use `Filtered · below minimum relevance` and `Scored · outside token budget`. A generic `Excluded` chip can appear as a grouping label but must not be the primary reason.

The budget-excluded row should show the exact boundary condition, for example: **“Eligible by relevance; ranked 7th; estimated 188 tokens; 124 tokens remaining when evaluated; not packed.”** If packing is greedy, say so. If it is an optimizer, show the objective and constraint version. Token cost belongs adjacent to score because it affects assembly admission, but it must remain semantically distinct from the quality score.

### 4.3 Stage latency and token allocation

The assembly-health strip should show wall-clock latency, stage durations, and token budget separately from memory quality. A parent total may not equal the sum of child stages when retrieval, scoring, and metadata fetches run in parallel. The stage strip should therefore show both **wall time** and, where useful, **summed child time**, with a tooltip explaining parallelism.

```text
Assembly  184 ms wall | 8 memories | 1,126 / 2,048 tokens used | 922 remaining
Retrieval  62 ms | Filtering 8 ms | Scoring 21 ms | Ranking 4 ms | Packing 89 ms
```

OpenTelemetry’s trace model provides the strongest official observability precedent for hierarchical spans, timestamps, attributes, and events.[34] Honeycomb, Grafana, OpenAI Agents SDK, and Elastic APM provide official product documentation for summary metadata, parent/child timing, token rollups, and selected-detail drilldown.[35] [36] [37] [38] Token accounting should state whether wrappers, serialization, and reserved prompt overhead are included. OpenAI Agents SDK and LangSmith document parent-level rollups with child breakdowns, supporting this separation of assembly total from per-memory cost.[39] [40]

### 4.4 Exclusion mockup

```text
EXCLUDED CANDIDATES  56 total
[12] Filtered · below minimum relevance     [44] Scored · outside token budget

Filtered before scoring
  —  “Old meeting note”       raw sim 0.31  threshold 0.45  composite not computed
  —  “Legacy preference”      raw sim 0.42  threshold 0.45  composite not computed

Scored but outside token budget
  #7  “Runbook: deploy API”   composite 0.701  raw sim 0.79  188 tok  boundary: 124 tok left
  #9  “Incident timeline”     composite 0.664  raw sim 0.76  241 tok  boundary: 124 tok left
```

The muted treatment is visual grouping only. The text and exact values remain available to assistive technologies, copying, and incident reports.

## 5. Layout and information architecture

### 5.1 The two-level disclosure model

The information architecture follows the overview–zoom/filter–details-on-demand mantra.[30] It also follows progressive disclosure guidance that common information should be visible initially while specialized explanation is revealed on request.[28] The panel should not exceed two disclosure levels: assembly overview and row/detail view. Carbon’s expandable-table guidance supports keeping collapsed rows useful and avoiding expand-all by default.[29] WAI-ARIA disclosure guidance requires explicit disclosure controls, state, keyboard behavior, and programmatic relationships.[41]

#### Assembly-level summary strip: mockup-level description

The summary strip occupies the full width above the table and remains pinned while the list scrolls. It contains five zones:

```text
┌ Assembly A-7F31  | production injection order | replay: exact ┐
│ 8 included   12 filtered   44 budget-excluded   1,126 / 2,048 tok │
│ 184 ms wall  |  retrieval 62  filter 8  score 21  pack 89 ms     │
│ Retrieved 64 ─ Filtered 12 ─ Scored 52 ─ Ranked 52 ─ Packed 8     │
│ Weights: R .40  Rec .25  U .20  C .10  Access .05  |  View: [table] │
└──────────────────────────────────────────────────────────────────┘
```

The first zone names the assembly ID, production-order status, and replay state. The second zone gives included/excluded counts and used/cap/remaining tokens. The third zone gives wall latency and a stage breakdown. The fourth zone is a clickable candidate funnel. The fifth zone discloses the five weights and makes the active view explicit. Latency is never rendered as another score segment. Token utilization is never rendered with the same semantic color scale as relevance.

#### Collapsed included row: mockup-level description

A collapsed row is one line on desktop and two compact lines on narrow screens. It is useful without expansion.

```text
┌ 1  [procedural] Deploy API runbook                  composite 0.768 ┐
│    weighted contributions: [relevance][recency][usefulness][conf][access]
│    raw similarity 0.62   84 tok   source: docs/runbook   age 18 d   ▸
└───────────────────────────────────────────────────────────────────────┘
```

The rank badge is visually first and textually first. The composite number is adjacent to the fixed-order contribution bar. Raw similarity is explicitly labeled and never substituted for rank. Category and provenance remain visible because they help the operator assess whether the score is semantically plausible. The disclosure button is separate from links or menus, uses `aria-expanded` and `aria-controls`, and supports Enter and Space.

For small N, the five segment labels may appear under the bar. For large N, the bar retains a legend and accessible text while labels move into the tooltip and expanded view. The list remains ordered by authoritative final rank in all modes.

#### Expanded row: mockup-level description

The expanded row opens below the selected row or in a synchronized side drawer on narrow screens. It is divided into four labeled blocks.

```text
┌ 1  Deploy API runbook                                      [Collapse]
│ SCORE CONTRACT                                             │
│ Component       raw     normalized  weight  contribution  │
│ Relevance       0.62    0.620       .40      0.248         │
│ Recency         0.72    0.720       .25      0.180         │
│ Usefulness      0.80    0.800       .20      0.160         │
│ Confidence      0.90    0.900       .10      0.090         │
│ Access freq.    0.60    0.600       .05      0.030         │
│ Composite                                      0.708       │
│                                                              │
│ RETRIEVAL PROVENANCE                                        │
│ raw vector similarity 0.62 | metric cosine | normalized within set
│                                                              │
│ RECENCY CONTEXT                                             │
│ category procedural | age 18 d | half-life 30 d | age/H 0.60
│ curve exponential | timestamp: last validated                 │
│                                                              │
│ ASSEMBLY EFFECT                                             │
│ 84 tokens | packed position 1 | source docs/runbook         │
│ [Why above #2] [Compare] [Copy JSON]                         │
└──────────────────────────────────────────────────────────────┘
```

The displayed composite in this example must equal the five contributions. The interface should surface a validation warning if weights do not sum to one, any input is clipped, or a default/null value was used. The example’s exact numbers are illustrative; production UI must use the trace’s actual values.

### 5.2 Layout comparison

| Candidate layout | Strength | Failure mode | Verdict |
|---|---|---|---|
| Ranked table with fixed contribution bars | Stable order, exact values, compact comparison, good for small and large N | Segment comparison is less precise away from the baseline | **Primary layout** |
| Full explanation tree per row | Audit depth and formula provenance | Too verbose and expensive for cross-row comparison | Expand-on-demand only |
| Waterfall for every row | Familiar contribution narrative | Implies signed baseline-to-output deltas; misrepresents five positive fixed weights | Use only for pairwise or counterfactual delta views |
| Heatmap of components | Dense large-N scan and component filtering | Weak identity, exactness, and causal narrative | Optional diagnostic view for N ≥ 50 |
| Scatterplot raw similarity versus composite | Reveals divergence and clusters | Does not show final order, exclusion, or token packing | Optional linked view |
| Treemap, bubbles, or packed areas | Visually compact | Poor position/length comparison and unstable row identity | Reject |

The table is the authoritative surface. Diagnostic views may be opened, but they must retain rank labels and a banner stating that their sort is not production order. The research on graphical perception supports common-scale position and length for comparison.[65] The design-system and government guidance supports explicit labels, context, non-color encodings, and a table equivalent.[61] [62]

## 6. Interactions

### 6.1 Sorting and authoritative order

The table opens sorted by **authoritative final rank**. This order is a production fact and must not be silently replaced. Diagnostic sorts may include composite score, raw similarity, recency contribution, token cost, category, or rank movement, but the interface must show a persistent banner such as `Diagnostic sort: raw similarity; production injection order remains in Rank column`.

Filtered rows must not be renumbered. If the operator filters to ranks 3, 7, and 9, those badges remain 3, 7, and 9. If the list is sorted by token cost, the production rank remains visible. This protects against the documented position-bias risk that viewers infer importance from whichever item appears first.[42]

The panel should distinguish **rank order** from **assembly order** when the packing algorithm changes insertion order, truncates content, or places a memory in a reserved slot. The labels must be exact rather than euphemistic: `Final rank`, `Packed position`, and `Context offset` are separate fields.

### 6.2 Tooltips and pinned details

Hover or keyboard focus may show a concise tooltip, but no essential explanation may depend on hover. The tooltip should contain the exact value, unit, formula, and scope:

```text
Recency contribution: 0.180
Normalized recency: 0.720 × weight 0.25
Category: procedural | half-life: 30 days | age: 18 days
```

Click pins the explanation in a popover or opens the expanded row. Tooltips should not contain paragraphs of prose, hidden assumptions, or unlabelled abbreviations. Tooltip research indicates that tooltip content affects correctness and that usage changes as people learn the interface.[43] Therefore the pinned view must repeat the information in a persistent, copyable form.

### 6.3 Selection, brushing, and linked views

Selecting a memory highlights its row in the contribution table, raw-similarity view, eligibility funnel, token-cost view, and latency context. This is a brushing-and-linking interaction: selection in one view identifies the same record in linked views.[23] Hover is transient; selected is persistent; compared is a separate state with a visible A/B marker.

The interface should support:

- click for one-memory inspection;
- Shift-click for two-memory comparison;
- `Why above this?` for the nearest higher-ranked or nearest competitor;
- a `Show excluded neighbors` action for candidates at the eligibility or budget boundary;
- a `Copy JSON` action for the exact decision record;
- stable deep links to the assembly ID, memory ID, and selected view.

### 6.4 The pairwise diff interaction

The pairwise drawer uses juxtaposition and explicit deltas rather than forcing mental subtraction between separate panels. It shows A and B in aligned columns, a signed delta column, and a sentence identifying the largest rank-relevant contributors. The drawer starts in **difference-first** mode: identical values are collapsed, while differences that explain the inversion are highlighted. A `Show all factors` control reveals the complete score contract and provenance tree.

A selected-memory waterfall is allowed inside this drawer only when the semantics are genuinely delta-based. Its sequence should be:

```text
raw similarity provenance → relevance delta → recency delta
→ usefulness delta → confidence delta → access-frequency delta
→ composite-score delta → rank outcome
```

This is not a production score waterfall. It is a signed A-minus-B narrative. SHAP’s baseline-to-output waterfall and force documentation are useful precedents for signed local contributions and collapsed low-impact details, but the UI must label the baseline and comparison explicitly.[8] [9]

### 6.5 What-if and simulation

The panel should offer a sandboxed `Simulate` mode, not editable production controls. The operator may vary weights, minimum relevance, token budget, half-life, or candidate removal. The result must show baseline versus preview, changed inputs, rank and eligibility deltas, and a `simulation only` banner. The production list must not change until the operator returns to the baseline or explicitly exports the simulation.

Counterfactual research supports actionable perturbations but also emphasizes feasibility, diversity, stability, and tradeoffs.[44] [45] For this reason, the panel should call these results **constrained score counterfactuals**, not causal explanations. A weight sweep should report rank-reversal thresholds where possible and indicate when a candidate is near a tie.

### 6.6 Accessibility and operational behavior

Every color-coded segment needs an accessible text label and a non-color distinction. The exact component table is the canonical alternative to the bar. Rows need visible focus, keyboard navigation, reduced-motion behavior, and programmatic disclosure state. Asynchronous stage updates must be announced as status messages without stealing focus.[41] [46] WCAG 2.2 supports programmatic structure, keyboard operation, focus visibility, contrast, reflow, and non-color status cues.[46]

## 7. What is missing

The panel’s largest gap is not another chart. It is a **replayable, integrity-checked decision record**. The operator needs to know not merely what the score was, but whether the score can be reconstructed after a model, index, tokenizer, schema, or policy change.

### 7.1 Replay and provenance contract

Every assembly should have an ID and replay manifest containing:

| Replay field | Why it matters |
|---|---|
| Query and candidate-snapshot digest | Establishes exactly which candidate set was considered |
| Embedding, index, retrieval, scorer, and code versions | Separates data changes from implementation changes |
| Exact five weights and category half-lives | Reconstructs the composite and recency transforms |
| Minimum-relevance threshold and token-budget policy | Reconstructs eligibility and packing decisions |
| Tokenizer and token-counting version | Prevents silent token-cost drift |
| Null/default/clipping behavior | Exposes hidden score substitutions |
| Tie-break and rank policy | Explains equal or near-equal scores |
| Event, ingestion, and assembly timestamps | Disambiguates temporal semantics |
| Clock, retry, timeout, and cache metadata | Explains stage latency and freshness anomalies |
| Code/container or build hash | Establishes the executing artifact |

CMU’s ML engineering guidance supports versioning data, pipeline code, models, infrastructure, and per-inference inputs and outputs.[47] NIST guidance supports origin/history tracking, log integrity, retention, synchronized clocks, validation, and message-digest checks.[48] [49] The UI should state replay status as `exact`, `semantic`, `best effort`, or `not replayable`, rather than implying reproducibility when the manifest is incomplete.

### 7.2 Score-contract and health diagnostics

The panel should flag weight-sum mismatch, nulls, out-of-range values, clipping, invalid half-lives, duplicate IDs, duplicate content, missing provenance, unavailable source content, index lag, cache age, schema mismatch, candidate-count discrepancy, and clock skew. It should distinguish source confidence, retrieval uncertainty, score uncertainty, and rank uncertainty. If uncertainty is not estimated, say `uncertainty not estimated`; do not show a decorative confidence badge.

Scikit-learn’s calibration documentation distinguishes calibrated probabilities from raw scores and recommends reliability diagrams for calibration assessment.[50] The composite should therefore carry an explicit semantic label: `heuristic composite`, `ordinal score`, or `calibrated probability`, according to evidence. FICO’s explanation precedent and CFPB guidance reinforce that explanations should identify the factors actually used and should not invent post-hoc reasons.[11] [52]

### 7.3 Token-budget packing diagnostics

Token budget is currently visible as total and per-row cost, but the panel should also expose the packing policy. For each candidate, record selection order, token cost, marginal utility, redundancy, residual budget, alternate fit, and rejection reason. A candidate can be high-quality but not fit; a candidate can fit but be redundant. Those are different operational facts.

Recent RAG research treats budgeted context selection as a constrained knapsack-style problem and highlights redundancy, information density, and greedy local-optimum behavior.[53] [54] The panel should show whether the production packer is greedy, heuristic, or optimizer-based, and should report regret or an approximate alternative only when such a comparison is actually computed.

### 7.4 Temporal diff and drift context

A single assembly can look correct while changing materially across time. Add a two-snapshot diff for candidate set, rank, composite, component values, half-lives, weights, retrieval index, model, cache/freshness, latency, token usage, and outcome. Drift signals should be annotated with the changed data and detector assumptions. Concept-drift literature supports this caution: a changing input population, detector, or metric may explain the apparent degradation.[55]

### 7.5 Testable acceptance criteria

The first usability evaluation should measure whether an operator can, without opening a second system:

1. identify the top production memory;
2. state the five reasons its composite is high;
3. explain why one memory outranked another;
4. find all candidates filtered by minimum relevance;
5. find all candidates rejected by token budget;
6. identify the slowest stage and distinguish wall time from summed child time;
7. identify the category half-life and timestamp semantics for recency;
8. export or deep-link the exact decision record.

The test should include small N and large N, equal scores with tie-breaks, high raw similarity but low final rank, old factual memory with strong score, recent low-relevance memory, and a parallel stage trace. It should also include keyboard-only and screen-reader verification. Human–AI trust research supports exposing uncertainty and failure states to calibrate trust rather than relying on confident visual language.[51]

## Final commitments

### Best pattern for weighted-score breakdown

**Commitment: a rank-ordered table with a fixed-order horizontal stacked contribution bar, exact numeric columns, and an expandable score-contract table.** This wins over a full explanation tree because it preserves cross-row comparison; it wins over a default waterfall because the five configured contributions are non-negative fixed terms, not signed changes from a meaningful baseline; and it wins over a score-only column because the operator can see both total and cause. The exact weights are relevance `.40`, recency `.25`, usefulness `.20`, confidence `.10`, and access frequency `.05`.

### Best pattern for rank-versus-similarity divergence

**Commitment: final-rank-first rows with a raw-similarity position connector and a selected-memory pairwise diff drawer.** This wins over a second independently sorted list because it preserves the authoritative production order; it wins over a scatterplot as the default because it keeps identity, eligibility, and tokens adjacent; and it wins over a per-row waterfall because the operator’s real question is often comparative: why did A outrank B? The connector shows movement, while the diff identifies the component delta that caused it.

### Best pattern for excluded-candidate reasoning

**Commitment: one same-run candidate funnel with two explicit excluded groups—`Filtered before scoring` and `Scored but excluded by token budget`—plus reason-bearing rows and expandable evidence.** This wins over hiding exclusions in a separate tab because the candidate remains causally attached to the assembly; it wins over a generic `Excluded` state because it distinguishes minimum relevance from budget admission; and it wins over folding exclusions into the ranked table because it does not falsely assign a final rank to an item that was never packed. The minimum-relevance row shows threshold comparison and `composite not computed`; the token-budget row shows composite, candidate rank, token cost, and budget boundary.

## References

[1]: https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-explain "Elasticsearch Explain API" — official product documentation; high confidence.

[2]: https://www.elastic.co/search-labs/blog/elasticsearch-scoring-and-explain-api "Understanding Elasticsearch scoring and the Explain API" — official product technical writeup; high confidence.

[3]: https://docs.opensearch.org/latest/api-reference/search-apis/explain/ "OpenSearch Explain API" — official product documentation; high confidence.

[4]: https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/explain/ "OpenSearch hybrid search explain" — official product documentation; high confidence.

[5]: https://www.algolia.com/doc/api-reference/api-parameters/getRankingInfo "Algolia getRankingInfo" — official product documentation; high confidence.

[7]: https://www.algolia.com/doc/guides/managing-results/relevance-overview/in-depth/ranking-criteria "Algolia ranking criteria" — official product documentation; high confidence.

[8]: https://shap.readthedocs.io/en/latest/example_notebooks/api_examples/plots/waterfall.html "SHAP waterfall plot" — official product documentation; high confidence.

[9]: https://shap.readthedocs.io/en/latest/generated/shap.plots.force.html "SHAP force plot" — official product documentation; high confidence.

[11]: https://www.myfico.com/credit-education/whats-in-your-credit-score "What’s in my FICO Scores?" — official product documentation; high confidence.

[12]: https://arxiv.org/html/2305.11755v3 "Visualization for Recommendation Explainability: A Survey and New Perspectives" — academic HCI/visualization paper; high confidence.

[13]: https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/forecasting-explanations "Feature attributions for forecasting explanations" — official product documentation; high confidence.

[14]: https://support.google.com/trends/answer/4365533?hl=en "FAQ about Google Trends data" — official product documentation; high confidence.

[18]: https://solr.apache.org/guide/solr/latest/query-guide/common-query-parameters.html "Apache Solr common query parameters" — official project documentation; high confidence.

[19]: https://lucene.apache.org/core/10_5_1/core/org/apache/lucene/search/Explanation.html "Apache Lucene Explanation class" — official API documentation; high confidence.

[20]: https://lucidworks.com/blog/debugging-search-application-relevance-issues "Debugging Search Application Relevance Issues" — published technical writeup; high confidence for the described example.

[21]: https://dl.acm.org/doi/10.1145/3397271.3401279 "Search Result Explanations Improve Efficiency and Trust" — academic HCI/visualization paper; high confidence.

[22]: https://arxiv.org/html/2211.02405 "Explainable Information Retrieval: A Survey" — academic HCI/visualization paper; high confidence.

[23]: https://cacm.acm.org/practice/interactive-dynamics-for-visual-analysis/ "Interactive Dynamics for Visual Analysis" — academic HCI/visualization research synthesis; high confidence.

[24]: https://docs.github.com/en/actions/using-jobs/using-conditions-to-control-job-execution "Using conditions to control job execution" — official product documentation; high confidence.

[25]: https://docs.github.com/en/actions/how-tos/monitor-workflows/view-job-condition-logs "Viewing job condition expression logs" — official product documentation; high confidence.

[26]: https://docs.gitlab.com/ci/pipelines/ "CI/CD pipelines" — official product documentation; high confidence.

[27]: https://docs.opensearch.org/latest/query-dsl/query-filter-context/ "Query and filter context" — official product documentation; high confidence.

[28]: https://www.nngroup.com/articles/progressive-disclosure/ "Progressive Disclosure" — published design teardown; medium confidence.

[29]: https://carbondesignsystem.com/components/data-table/usage/ "Data table usage" — official design-system documentation; high confidence.

[30]: https://data.europa.eu/apps/data-visualisation-guide/the-information-seeking-mantra "The information-seeking mantra" — official government visualization guidance; high confidence.

[31]: https://support.reddithelp.com/hc/en-us/articles/15484440494356-Moderation-Queue "Moderation Queue" — official product documentation; high confidence.

[32]: https://getstream.io/moderation/docs/node/content-moderation/review-queue/ "Review Queue" — official product documentation; high confidence.

[34]: https://opentelemetry.io/docs/concepts/signals/traces/ "Traces" — official observability documentation; high confidence.

[35]: https://docs.honeycomb.io/reference/honeycomb-ui/query/trace-waterfall "Trace Waterfall" — official product documentation; high confidence.

[36]: https://grafana.com/docs/grafana/latest/visualizations/simplified-exploration/traces/concepts/trace-structure/ "Trace structure" — official product documentation; high confidence.

[37]: https://openai.github.io/openai-agents-python/tracing/ "Tracing" — official SDK documentation; high confidence.

[38]: https://www.elastic.co/docs/solutions/observability/apm/transactions-ui "Transactions UI in Elastic APM" — official product documentation; high confidence.

[39]: https://openai.github.io/openai-agents-python/usage/ "Usage" — official SDK documentation; high confidence.

[40]: https://docs.langchain.com/langsmith/cost-tracking "Cost tracking" — official LLM observability documentation; high confidence.

[41]: https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/ "Disclosure (Show/Hide) Pattern" — official accessibility standard guidance; high confidence.

[42]: https://research.tudelft.nl/files/96007152/3404835.3462851.pdf "This Is Not What We Ordered: Exploring Why Biased Search Result Rankings Affect User Attitudes on Debated Topics" — academic HCI/visualization paper; high confidence.

[43]: https://link.springer.com/chapter/10.1007/978-3-319-58640-3_6 "Design of Tooltips for Data Fields: A Field Experiment of Logging Use of Tooltips and Data Correctness" — academic HCI/visualization paper; medium-high confidence.

[44]: https://arxiv.org/abs/1711.00399 "Counterfactual Explanations without Opening the Black Box" — academic HCI/visualization paper; high confidence.

[45]: https://dl.acm.org/doi/10.1145/3351095.3372850 "Explaining Machine Learning Classifiers through Diverse Counterfactual Explanations" — academic HCI/visualization paper; high confidence.

[46]: https://www.w3.org/TR/WCAG22/ "Web Content Accessibility Guidelines (WCAG) 2.2" — official accessibility standard; high confidence.

[47]: https://mlip-cmu.github.io/book/24-versioning-provenance-and-reproducibility.html "Versioning, Provenance, and Reproducibility" — academic ML engineering textbook chapter; high confidence.

[48]: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf "Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile" — official government technical guidance; high confidence.

[49]: https://nvlpubs.nist.gov/nistpubs/legacy/SP/nistspecialpublication800-92.Pdf "Guide to Computer Security Log Management" — official government technical guidance; high confidence.

[50]: https://scikit-learn.org/stable/modules/calibration.html "Probability calibration" — maintained technical documentation; high confidence for calibration concepts.

[51]: https://pmc.ncbi.nlm.nih.gov/articles/PMC11573890/ "Calibrating workers’ trust in intelligent automated systems" — academic HCI/visualization paper; high confidence.

[52]: https://www.consumerfinance.gov/compliance/circulars/circular-2022-03-adverse-action-notification-requirements-in-connection-with-credit-decisions-based-on-complex-algorithms/ "Consumer Financial Protection Circular 2022-03" — official regulator guidance; high confidence.

[53]: https://aclanthology.org/2026.findings-acl.1052/ "Self-Correcting RAG: Enhancing Faithfulness via MMKP Context Selection and NLI-Guided MCTS" — academic information-retrieval paper; medium-high confidence.

[54]: https://arxiv.org/html/2512.25052v1 "AdaGReS: Adaptive Greedy Context Selection via Redundancy-Aware Scoring for Token-Budgeted RAG" — research preprint; medium confidence.

[55]: https://www.sciencedirect.com/science/article/pii/S0950705122002854 "From concept drift to model degradation: An overview on performance-aware drift detectors" — academic HCI/visualization paper; high confidence.

[56]: https://dl.acm.org/doi/fullHtml/10.1145/3290605.3300422 "Ranked-List Visualization: A Graphical Perception Study" — academic HCI/visualization paper; high confidence.

[57]: https://docs.cloud.google.com/data-studio/add-reference-lines-and-reference-bands-to-charts "Add reference lines and reference bands to charts" — official product documentation; high confidence.

[58]: https://help.tableau.com/current/pro/desktop/en-us/reference_lines.htm "Reference Lines, Bands, Distributions, and Boxes" — official product documentation; high confidence.

[59]: https://docs.opensearch.org/latest/query-dsl/compound/function-score/ "Function score query" — official product documentation; high confidence.

[60]: https://www.elastic.co/docs/reference/query-languages/esql/functions-operators/search-functions/decay "ES|QL DECAY function" — official product documentation; high confidence.

[61]: https://designsystem.digital.gov/components/data-visualizations/ "Data visualizations" — official government design-system guidance; high confidence.

[62]: https://m2.material.io/design/communication/data-visualization.html "Data visualization" — official product design guidance; high confidence.

[63]: https://pmc.ncbi.nlm.nih.gov/articles/PMC4198697/ "LineUp: Visual Analysis of Multi-Attribute Rankings" — academic HCI/visualization paper; high confidence.

[65]: https://faculty.washington.edu/aragon/classes/hcde511/s12/readings/cleveland84.pdf "Graphical Perception: Theory, Experimentation, and Application to the Development of Graphical Methods" — academic HCI/visualization paper; high confidence for the perceptual principle.

[10]: https://arxiv.org/abs/1602.04938 "Why Should I Trust You? Explaining the Predictions of Any Classifier" — academic HCI/visualization paper; high confidence.

[16]: https://www.atlassian.com/data/charts/stacked-bar-chart-complete-guide "Stacked bar charts: a detailed breakdown" — published design teardown; medium confidence.

[17]: https://www.storytellingwithdata.com/blog/2011/11/waterfall-chart "The waterfall chart" — community writeup; medium confidence.
