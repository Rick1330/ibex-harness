# Extraction quality gold set v1

Versioned gold set for Milestone **3.5.B.4** (ADR-0066). A future `v2/` can be
added without breaking baseline comparability.

## Review

| Field | Value |
| --- | --- |
| `reviewed_by` | Elshaday Mengesha |
| `reviewed_at` | 2026-09-03 |
| Notes | Synthetic hand-labeled conversations; labels checked against `VALID_LABELS` / `CATEGORY_HALF_LIFE_DAYS` taxonomy. Multi-label and supersession cases reviewed for temporal_kind correctness. |

## Size and distribution

| Signal | Count |
| --- | --- |
| Conversations | **125** (`>= 100`) |
| Expected memory rows | 130 |
| Primary category coverage | factual 33, procedural 25, preference 32, behavioral 27, episodic 23 (memory-label occurrences) |
| Multi-label memories | 10 |
| Supersession memories | 10 |

## Files

| File | Role |
| --- | --- |
| `conversations.jsonl` | `{conversation_id, turns:[{turn_index, role, content}]}` |
| `expected_memories.jsonl` | `{conversation_id, turn_index, expected:[ExtractedMemory], temporal_kinds:[]}` |
| `openai_cassettes.jsonl` | Deterministic provider `raw_json` per conversation |
| `cassette_manifest.json` | `prompt_sha256`, `schema_sha256`, file hashes, counts, `cassette_kind` |
| `baseline_results.json` | Per-provider metrics with `enforcement: ci \| manual` |

## CI vs manual (vLLM conflict → path a)

| Provider | Enforcement | How numbers are produced |
| --- | --- | --- |
| OpenAI `gpt-4o-mini` | **`ci`** | Cassette replay on PR/smoke/fast; optional live on weekly `full` when `OPENAI_API_KEY` is set |
| vLLM `Qwen2.5-14B-Instruct` | **`manual`** | Not CI-enforced (no GPU runner; mirrors 3.5.B.2). Refresh via runbook below and set `last_refreshed` |

Harness summaries always print `enforcement=` so manual/stale vLLM numbers cannot be mistaken for CI-gated scores.

## Cassette / cost policy

- **PR / smoke / fast:** replay `openai_cassettes.jsonl` only — **$0**, deterministic, no contributor API spend.
- **full (Sunday / dispatch):** if `OPENAI_API_KEY` is present, run live OpenAI; otherwise fall back to cassette and note the skip in the job log.
- **`cassette_kind`** (provenance stamp, not cryptographic proof of model output):
  - `oracle_aligned_expected_json` — each cassette embeds gold expected JSON so CI measures scoring + gate wiring with a perfect baseline.
  - `live_openai_recorded` — written by `EXTRACTION_EVAL_MODE=record` (live OpenAI).
- Contract hashes (fail-closed on cassette/smoke/fast unless `EXTRACTION_EVAL_ALLOW_PROMPT_DRIFT=1` locally — **never in CI**):
  - `prompt_sha256` = `sha256(EXTRACTION_SYSTEM_PROMPT_BATCH)`
  - `schema_sha256` = `sha256(canonical BatchExtractionResult.model_json_schema())`
- **Oracle + contract-change CI gate:** if `cassette_kind` is still `oracle_aligned_expected_json` and the PR touches `app/extraction/prompt_v2.py` or `app/extraction/schema.py`, CI fails unless the PR body contains `EXTRACTION_EVAL_ORACLE_OK=1` (reviewer-visible exception) or cassettes were re-recorded live (`cassette_kind=live_openai_recorded`). Hash bumps alone do not satisfy this gate.

### Re-record OpenAI cassettes

```bash
cd services/worker
export OPENAI_API_KEY=…   # budgeted; never commit
export EXTRACTION_EVAL_MODE=record
.venv/bin/python eval/run_eval.py --mode record
# Updates openai_cassettes.jsonl + cassette_manifest.json
# (sets cassette_kind=live_openai_recorded and refreshes prompt_sha256 + schema_sha256)
# Then re-run cassette eval, update baseline_results.json openai.metrics / last_refreshed
```

### Manual vLLM side-by-side

```bash
# After B.2 vLLM server is up (see services/worker/README.md § Manual vLLM verification)
export IBEX_WORKER_EXTRACTION_PROVIDER=vllm
export IBEX_WORKER_EXTRACTION_BASE_URL=http://127.0.0.1:8000/v1
cd services/worker
.venv/bin/python eval/run_eval.py --mode vllm
# Copy metrics into baseline_results.json providers.vllm.metrics
# Set enforcement=manual, last_refreshed=YYYY-MM-DD — do not flip enforcement to ci
```

## Adding cases

1. Append a conversation to `conversations.jsonl`.
2. Append matching expected rows (include `temporal_kinds`: `indefinite` or `supersession`).
3. Re-record or hand-author a cassette line for that `conversation_id`.
4. Re-run `run_eval.py --mode cassette` and refresh OpenAI baseline metrics if needed.
5. Keep category coverage balanced; document review in this README when labels change.

## Gate

`policy.max_regression_pp: 3.0` — absolute percentage points (not the ranking-quality relative %).
Only `enforcement: ci` provider blocks can fail CI. Proven by `eval/test_regression_gate.py`
(`main() == 1` on a 4pp synthetic drop).
