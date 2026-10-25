# Memory PII microbench / recall (m3.C.1)

Scripts compare spaCy CNN models and measure structured-PII recall for the write-path
Presidio stage ([ADR-0054](../../../engineering/adr/0054-memory-pii-presidio-in-process.md)).

```bash
cd services/memory
uv sync --frozen
uv run python ../../benchmarks/memory/pii/microbench_spacy_models.py
uv run python ../../benchmarks/memory/pii/recall_structured.py
```

Committed JSON artifacts are the source of truth for docs (latency share of the 200 ms write
budget; >95% structured recall gate).

## CI recall gate

The `memory-test` CI job runs the harness via `infra/scripts/memory-test-ci.sh`.
Recall must be >0.95; a regression exits 1 and fails the gate.

Contributors maintain the seeded synthetic `FIXTURES` in `recall_structured.py`
through pull requests; never use live tenant data. Re-validate the fixture totals
and expected hit counts in `test_pii_recall_gate.py` whenever fixtures change.

Use `--output PATH` to write results elsewhere. Without it, the harness rewrites
`recall_structured.json` beside the script; the committed JSON is the docs baseline.
For safety the resolved path must end in `.json` and sit inside the script's
directory or the system temp directory; anything else exits with an error.
