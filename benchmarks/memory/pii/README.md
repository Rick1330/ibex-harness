# Memory PII microbench / recall (m3.C.1)

Scripts compare spaCy CNN models and measure structured-PII recall for the write-path
Presidio stage ([ADR-0054](../../../web/content/docs/adr/0054-memory-pii-presidio-in-process.mdx)).

```bash
cd services/memory
uv sync --frozen
uv run python ../../benchmarks/memory/pii/microbench_spacy_models.py
uv run python ../../benchmarks/memory/pii/recall_structured.py
```

Committed JSON artifacts are the source of truth for docs (latency share of the 200 ms write
budget; >95% structured recall gate).
