# ibex-async-db (Python)

Shared libpq → asyncpg URL translation and TLS `connect_args` for IBEX Python
services using SQLAlchemy + asyncpg.

Consumers: `services/worker`, `services/memory`, `services/api`, `services/mcp-operator`.

## Layout

```text
packages/ibex_async_db/
  pyproject.toml
  README.md
  src/
    ibex_async_db/          # import ibex_async_db
      __init__.py
      url.py                # libpq → asyncpg URL + SSL connect_args
      capability_login.py   # shared startup capability-login assertion
  tests/
    test_url.py
    test_capability_login.py
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
from sqlalchemy.ext.asyncio import create_async_engine

from ibex_async_db import parse_async_database_url, normalize_async_database_url

target = parse_async_database_url(
    "postgresql://user:pass@localhost:5432/ibex?sslmode=disable"
)
# target.url -> postgresql+asyncpg://... (libpq SSL params stripped)
# target.connect_args -> {"ssl": False}

engine = create_async_engine(target.url, connect_args=dict(target.connect_args))
```

`normalize_async_database_url(url)` returns only the cleaned asyncpg SQLAlchemy URL.

## Capability-login assertion

`ibex_async_db.capability_login` holds the one implementation of the startup
check that a service pool connects as its capability login, not the RLS-bypassing
owner and not a superuser. Each service wraps it with its own expected login and
error label:

```python
from ibex_async_db.capability_login import assert_capability_login

await assert_capability_login(engine, expected_login="ibex_runtime", service_label="api")
```

The module imports SQLAlchemy; every consumer already depends on it.

## SSL policy

- `sslmode` is removed from the URL and mapped to `connect_args["ssl"]`.
- `prefer` is allowed only for local hosts (`127.0.0.1`, `localhost`, `::1`).
- `allow` is passed through for asyncpg two-attempt behavior.
- Verified modes (`require`, `verify-ca`, `verify-full`) use TLS 1.2+ with hostname checks.
- `sslcrl` is rejected: Python 3.12 can load CRLs on an `SSLContext` in application code, but this parser does not map `sslcrl` query parameters to `connect_args["ssl"]` — use a custom `SSLContext` instead of a DSN `sslcrl` param.
