# ibex-async-db (Python)

Shared libpq → asyncpg URL translation and TLS `connect_args` for IBEX Python
services using SQLAlchemy + asyncpg.

Consumers: `services/worker`, `services/memory`.

## Layout

```text
packages/ibex_async_db/
  pyproject.toml
  README.md
  src/
    ibex_async_db/          # import ibex_async_db
      __init__.py
      url.py
  tests/
    test_url.py
```

## Install (local monorepo)

Both consumers pin the package via path dependency in `pyproject.toml`:

```toml
[tool.uv.sources]
ibex-async-db = { path = "../../packages/ibex_async_db" }
```

CI and Docker images build a wheel with `infra/scripts/build-ibex-async-db-wheel.sh`
(or inline `uv build --wheel` in each service Dockerfile) and install
`ibex-async-db==0.1.0` from `/wheels`.

## Usage

```python
from ibex_async_db import parse_async_database_url, normalize_async_database_url

target = parse_async_database_url(
    "postgresql://user:pass@localhost:5432/ibex?sslmode=disable"
)
# target.url -> postgresql+asyncpg://... (libpq SSL params stripped)
# target.connect_args -> {"ssl": False}

engine = create_async_engine(target.url, connect_args=dict(target.connect_args))
```

`normalize_async_database_url(url)` returns only the cleaned asyncpg SQLAlchemy URL.

## SSL policy

- `sslmode` is removed from the URL and mapped to `connect_args["ssl"]`.
- `prefer` is allowed only for local hosts (`127.0.0.1`, `localhost`, `::1`).
- `allow` is passed through for asyncpg two-attempt behavior.
- Verified modes (`require`, `verify-ca`, `verify-full`) use TLS 1.2+ with hostname checks.
- `sslcrl` is rejected (Python 3.12 `ssl` module has no CRL loader API).
