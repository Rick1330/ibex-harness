## What and Why

## Tracking issue

Closes #ISSUE_NUMBER

Link the issue in both directions: the issue body or a comment must reference this PR (e.g. `Implementation PR: #123`).

## How

## Testing

- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual verification (describe)
- [ ] If this PR changes `EXTRACTION_SYSTEM_PROMPT_BATCH` or the extraction output schema (`BatchExtractionResult` / `app/extraction/schema.py`), cassettes were re-recorded live (`EXTRACTION_EVAL_MODE=record`) and `cassette_manifest.json`'s `cassette_kind` / `prompt_sha256` / `schema_sha256` were updated in this same PR (or the PR body includes `EXTRACTION_EVAL_ORACLE_OK=1` with reviewer acknowledgment)

## Performance

## Security

## Migrations / Ops

## Docs

## Checklist (Definition of Done)

- [ ] Lint / CI passes
- [ ] No secrets in code, logs, or tests
- [ ] Multi-tenancy: org_id enforced where data is accessed
- [ ] Docs updated if behavior or contracts changed
