# Embedder service

Python FastAPI service owning the embedding contract, profile registry, readiness geometry validation, and backend selection. The deterministic CPU stub, TEI backend, and hosted backend are implemented; readiness depends on the selected profile’s external service and credentials.

## Backend matrix

| Profile | Backend | Status and prerequisites |
| --- | --- | --- |
| `cpu` | Deterministic stub | Local/test-safe; not a quality or production model claim |
| `gpu` | TEI HTTP backend | Requires reachable TEI base URL and matching model/dimension |
| `hosted` | Hosted API backend | Requires provider/base URL/API key and matching model/dimension |

Selection is implemented in `app/factory.py` and covered by the backend contract tests. See [ADR-0046](../../web/content/docs/adr/0046-embedder-interface-registry.mdx).

## Configuration

| Variable | Meaning |
| --- | --- |
| `IBEX_EMBEDDING_PROFILE` | `cpu`, `gpu`, or `hosted`; default `cpu` |
| `IBEX_EMBEDDING_DIM` | Expected vector dimension; must match backend |
| `IBEX_EMBEDDING_MODEL` | Model identifier; profile catalog default when unset |
| `IBEX_EMBEDDING_TEI_BASE_URL` | TEI HTTP origin for `gpu` |
| Hosted provider/base URL/key variables | Required for `hosted`; keep keys server-side and never log them |
| Cache settings | Optional embedding cache; preserve tenant/key isolation |

## Local run and tests

```bash
# from repository root
make test-embedder
cd services/embedder
uv sync --frozen --extra dev
.venv/bin/pytest -q
IBEX_EMBEDDING_PROFILE=cpu .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Probes are `/health` and `/ready`. A successful CPU readiness probe does not certify TEI/hosted reachability or production embedding quality.
