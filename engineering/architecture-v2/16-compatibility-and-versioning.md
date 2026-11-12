# Compatibility and Versioning

**Status:** `specified` policy. The windows below are the policy of record. Nothing is deprecated as of
2026-11-12, so [`contracts/deprecations.json`](contracts/deprecations.json) ships with an empty `entries` array.

## Supported-surface discipline

Declare support separately for OpenAI-compatible Chat Completions, a lossless Responses subset, native Anthropic Messages, MCP Streamable HTTP, optional stdio, provider adapters, SDKs, and framework integrations. Hosted Claude Code, Codex, Cursor, or Copilot paths that bypass IBEX are not governed by IBEX and must be documented as such.

For each client/framework record version, transport, configuration, identity mapping, tested features, known limitations, diagnostics, and last verification. Repository integration is not support evidence.

## Version axes

Contract major, protobuf package/service, REST `/v1`, MCP protocol/tool schema, provider adapter, model deployment, tokenizer, event schema, database migration, SDK/CLI, and feature flag are independent version axes. Record all relevant versions in evidence.

## Change policy

Every breaking change requires ADR, migration, deprecation notice, support window, compatibility fixtures, rollback/roll-forward plan, and current-state update. Additive changes still require examples, generated artifacts, and tests.

## Deprecation policy

A deprecation is a dated promise, not an intention. It is recorded once, in one file, and the window it promises is
measured from that record.

### Support windows

The window is `sunset_date - notice_date` in whole days, and it must be at least the minimum for the contract's
compatibility class:

| Surface | How the contract is identified | `stable` window | `beta` window |
|---|---|---|---|
| REST | `contract_id` row in [`contracts/rest-route-registry.json`](contracts/rest-route-registry.json) | 180 days | 31 days |
| gRPC method | `<package>.<Service>/<Method>` in `packages/proto/proto` | 180 days | 31 days |
| MCP tool schema | tool `name` in `services/mcp-operator/mcp_tools.json` or `services/mcp-memory/mcp_tools.json` | 180 days | 31 days |

The same window applies to all three surfaces. The surface changes how the contract is identified and which registry
proves it exists, not how long a consumer has to migrate. The middle column names the identity an entry records; only
the REST and MCP rows resolve against a committed registry that the check reads, which
[What the check proves, and what it does not](#what-the-check-proves-and-what-it-does-not) states explicitly.

`internal` rows in the REST registry are operational routes, not public contracts, and are not recorded as
deprecations. A contract promoted from `beta` to `stable` needs a fresh notice if its recorded sunset is less than 180
days after its notice date: the class at notice time is the class the window is measured against.

### Announcement headers

A REST deprecation is announced on the wire with standard headers, not vendor headers:

| Header | Standard | Value |
|---|---|---|
| `Deprecation` | RFC 9745 | an RFC 9651 Date naming the notice time, e.g. `@1798761600` |
| `Sunset` | RFC 8594 | an HTTP-date naming the removal date, e.g. `Mon, 01 Jun 2026 00:00:00 GMT` |
| `Link` | `deprecation` relation (RFC 9745) and `successor-version` (RFC 5829) | `<migration-doc-url>; rel="deprecation"` and `<successor-url>; rel="successor-version"` |

`Deprecation` is a structured field whose value is a Date; RFC 8594's `Sunset` uses an HTTP-date, and a response's
`Sunset` timestamp must not be earlier than its `Deprecation` timestamp. The former `X-IBEX-Deprecation`,
`X-IBEX-Deprecation-Date`, `X-IBEX-Sunset-Date`, and `X-IBEX-Successor` headers are retired and must not be emitted.

This table is the policy, not an implementation record: no middleware or interceptor in `services/` emits `Deprecation`,
`Sunset`, or `Link` today. `headers_implemented` is the switch that keeps a `rest` entry from reaching
`status: announced` before an emitter ships, and [Deliberately out of scope](#deliberately-out-of-scope) records the
gap.

gRPC methods have no standard deprecation response header, and MCP defines none for a tool. For those surfaces the
committed record below is the notice of record; the method comment or tool description names the successor. No HTTP
header claim is made for them.

### The record

[`contracts/deprecations.json`](contracts/deprecations.json) is the committed record. It has schema
`ibex.deprecations.v1` and an `entries` array; each entry is:

| Field | Rule |
|---|---|
| `id` | Unique, stable record key. Entries are sorted by it. |
| `surface` | `rest`, `grpc`, or `mcp`. |
| `contract_id` | REST and gRPC only. The REST registry's `contract_id`, or `<package>.<Service>/<Method>` for gRPC. |
| `tool`, `server` | MCP only. The tool `name` and the server, `operator` or `memory`. |
| `successor` | The replacement contract or tool. Required, and must differ from the deprecated contract. |
| `stability` | `stable` or `beta`. For REST it must equal the registry row's value. |
| `notice_date`, `sunset_date` | `YYYY-MM-DD`. The window between them must meet the class minimum. |
| `status` | `proposed`, `announced`, or `withdrawn`. |
| `headers_implemented` | Boolean. Must be `true` before `status` can be `announced`. |
| `evidence` | Repository-relative file. It must exist when the entry is `announced`. |

**An empty `entries` array is the correct 1.0 state.** Nothing is deprecated today, and an empty list proves nothing
is: the record cannot claim a deprecation that does not exist. An entry is added when a deprecation is real, not in
anticipation of one.

`status` moves in one direction: `proposed` while the replacement and migration note are being built, `announced`
once the headers are implemented and the evidence exists, `withdrawn` if the plan is cancelled before sunset. A
`proposed` entry may carry `headers_implemented: false`; an `announced` entry may not, and an `announced` entry whose
`sunset_date` has passed fails the check until it is withdrawn.

### The check

```bash
cd services/api && .venv/bin/python scripts/check_deprecations.py
```

The check reads the record and both registries, uses no network, and prints sorted one-line failures. It fails on:

- a window shorter than 180 days (`stable`) or 31 days (`beta`), and on any date that is not `YYYY-MM-DD`;
- a `rest` entry whose `contract_id` is absent from the REST registry, or whose `stability` disagrees with that row;
- an `mcp` entry whose `server` is not `operator` or `memory`, or whose `tool` is absent from that server's
  `mcp_tools.json`;
- an empty `successor`, or a `successor` that names the contract itself;
- `status: announced` with `headers_implemented: false`, with an `evidence` path that is not an existing file inside the
  repository, or with a `sunset_date` already in the past;
- an unknown `surface`/`stability`/`status` value, an unknown or missing field, a schema id other than
  `ibex.deprecations.v1`, a duplicate `id`, or entries not sorted by `id`.

The same check runs in CI through `services/api/tests/unit/test_deprecations.py`, which
`infra/scripts/api-test-ci.sh` collects in the `api-test` job, so a pull request that records an invalid window or a
phantom contract fails without a workflow change.

### What the check proves, and what it does not

| Question | Answered? | How |
|---|---|---|
| Is the record a valid `ibex.deprecations.v1` document? | **yes** | schema id, exact field set per surface, no unknown fields, enum values, `headers_implemented` boolean, unique `id`, entries sorted by `id` |
| Does every entry keep its class window? | **yes** | `sunset_date - notice_date` in whole days against 180 (`stable`) / 31 (`beta`), and both dates must be exact `YYYY-MM-DD` |
| Does a `rest` entry name a real contract, with the recorded stability? | **yes** | cross-check against [`contracts/rest-route-registry.json`](contracts/rest-route-registry.json) |
| Does an `mcp` entry name a real tool on a known server? | **yes** | cross-check against that server's `mcp_tools.json` (`operator` or `memory`) |
| Does a `grpc` entry name a real method? | **no** | field set, types, enums, dates, window, successor, evidence and status are checked; the `contract_id` is checked against no method list, and `<package>.<Service>/<Method>` is not validated as a shape, because no gRPC method registry is committed |
| Is a deprecation that exists in code but is missing from the record caught? | **no** | nothing scans handlers, the proto files, or tool registrations for a deprecation marker. The check validates what the record says; it cannot see what the record omits |
| Is the MCP descriptor compared with the previous commit? | **no** | `python -m app.descriptors --check` (a step of the `mcp-memory-test` and `mcp-operator-test` jobs) compares the committed record with the surface the service publishes now, not with a previous commit |
| Is an MCP tool `description` pinned? | **yes** | `mcp_tools.json` records `description_sha256` beside name, version, stability, `deprecated` and the input/output JSON Schemas, and `--check` fails with `description-drift` when the published text changes — the model reads that text, so an injected instruction is a schema-level change |
| Is an MCP schema `title` pinned? | **no** | the descriptor hash is taken over a title-free canonical form, so a rename that only moves titles passes |
| Is a `description` inside a tool's input/output schema pinned? | **yes** | it is part of the hashed schema, and that hash is compared on every `mcp-memory-test` / `mcp-operator-test` run |

The boundary an auditor should read from this table: the record binds the contract a service *publishes* — its schemas
and the tool description the model reads — but not the code that implements it. A description-only change is descriptor
drift and fails the check; a title-only change still passes, because the hash is taken over a title-free canonical form.

### Deliberately out of scope

This change is the policy, the record, and the gate. It ships no emitter. No middleware or interceptor in `services/`
writes `Deprecation`, `Sunset`, or `Link` today, which is exactly why `headers_implemented` exists: it is the switch
that stops a `proposed` entry becoming `announced` before an emitter ships, with existing evidence. Three further gaps
are deliberate:

- a `grpc` entry is validated structurally only: field set, field types, enums, dates, window, successor, evidence and
  status. Its `contract_id` is resolved against no method list, and `<package>.<Service>/<Method>` is not validated as a
  shape, because no committed gRPC method registry exists. gRPC shapes are gated by `buf-breaking` (W5.1) — which runs
  in CI as an advisory job (`continue-on-error: true`) and is not a required check — and by P0-12, as the REST
  registry's `out_of_scope.grpc` records.
- a `rest` entry's `successor` is not required to be a registered contract, because the successor may be a contract
  that does not exist until the new version ships. `successor-version` is a forward pointer, not a current one.
- the MCP descriptor's `deprecated` flag is not cross-checked against the record, and cannot be: `mcp_tools.json` must
  record `deprecated: false` for every published tool (any `true` is a `deprecated-tool` failure), so a deprecated tool
  is removed from the surface and the record regenerated. A tool deprecation therefore lives in this record only, and
  nothing ties a removal to a recorded window: removing a tool fails the descriptor check as `stale-tool`, and
  regenerating the record clears it without a deprecation decision. Closing that gap is W5.5's remaining work.
