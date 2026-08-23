# Embedder service (Phase 2.5 Track D)

Python FastAPI service owning embedding inference. **G4.M1** ships the
`EmbeddingBackend` ABC, profile registry, deterministic stub, and `/health` +
`/ready` with startup geometry validation. TEI / hosted backends land in
G4.M2 / G4.M3 ([ADR-0046](../../web/content/docs/adr/0046-embedder-interface-registry.mdx)).

## Run tests

```bash
make test-embedder
# or:
cd services/embedder
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

## Run locally

```bash
export IBEX_EMBEDDING_PROFILE=cpu
uvicorn app.main:app --host 0.0.0.0 --port 8080 --app-dir services/embedder
```

## Env (M1)

| Variable | Meaning |
| --- | --- |
| `IBEX_EMBEDDING_PROFILE` | `cpu` \| `gpu` \| `hosted` (default `cpu`) |
| `IBEX_EMBEDDING_DIM` | Must match backend dimensions |
| `IBEX_EMBEDDING_MODEL` | Must match backend model id |

When dim/model env vars are unset, defaults come from the profile catalog.
