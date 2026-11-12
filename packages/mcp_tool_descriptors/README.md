# mcp_tool_descriptors (Python)

Shared **contract gate** for a published MCP tool surface (W5.5 / P0-14). The
deployable MCP surfaces live in `services/mcp-operator` and `services/mcp-memory`;
this package owns the record format, the drift rules, and the CLI that both
services run, so the two gates cannot drift apart.

## What it owns

- **Hash rule** (`hashing.py`) — SHA-256 over the title-free canonical JSON form
  of a schema or description. Pydantic derives `title` from a class or function
  name, so titles are dropped before hashing; a *property* named `title` keeps
  its own schema.
- **Surface contract** (`record.py`) — `Surface(service, publish)`: the server
  name plus an async callable returning every advertised `(tool, declared
  version)` pair. The record schema id, the single recorded stability (`beta`),
  and the row shape live here too.
- **Comparison** (`checks.py`) — `check()` (default, never writes) and
  `update()` (the only writer), with one rule per failure code:
  `missing-tool`, `stale-tool`, `schema-drift`, `description-drift`,
  `deprecated-tool`, `stability-drift`, `version-drift`, `undeclared-version`,
  `duplicate-tool`, `invalid-record`, `invalid-field`, `invalid-descriptor`,
  `missing-descriptor`, `unreadable-descriptor`, `schema-mismatch`. A differing
  `generator` is a warning, not a failure.
- **Path confinement** (`paths.py`) — a caller-supplied `--path` is refused for a
  `..` segment, for resolving outside the allow-root (the working directory, or
  `IBEX_MCP_DESCRIPTOR_ALLOW_ROOT` / `--allow-root`), and for an existing target
  that is not a regular file. A refusal exits 2 and touches nothing.
- **Atomic write** (`writer.py`) — same-directory temporary file, `fsync`,
  `os.replace`, so an interrupted run cannot truncate the record.
- **CLI** (`cli.py`) — `--check` (default) / `--update` / `--path` /
  `--allow-root`, with exit codes 0 (match), 1 (drift) and 2 (refused path).

## Consumers

`services/mcp-operator` (`budget.get`, `evidence.query`, `run.get`,
`session.get`) and `services/mcp-memory` (`get_memory_lineage`,
`record_feedback`, `search_memory`, `write_memory`). Each keeps a thin
`app/descriptors.py` that builds its own FastMCP server and points at its own
committed `mcp_tools.json`; everything else is here.

## Tests

The negative matrix lives here and runs against a synthetic surface, so it does
not need a service, a database, or an access token.

```bash
cd packages/mcp_tool_descriptors
uv sync --frozen --extra dev
.venv/bin/ruff check src tests
.venv/bin/pytest -q --cov=src/mcp_tool_descriptors --cov-report=term-missing
```
