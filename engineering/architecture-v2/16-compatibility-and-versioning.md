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
measured from the date it was announced in that record.

### Support windows

The window is `sunset_date - announced_on` in whole days, measured from the entry's announcement date — from
`notice_date` only while no announcement is recorded, which is the `proposed` and `withdrawn` case. It must be at least
the minimum for the contract's compatibility class. `notice_date` is when the promise was planned; `announced_on` is
when consumers were actually told, and the clock starts there, so a record cannot spend its own planning delay as part
of what a consumer is owed. An `announced` entry must therefore record `announced_on`:

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
days after its `announced_on`: the class at notice time is the class the window is measured against, and the window
itself runs from the announcement.

### Announcement headers

A REST deprecation is announced on the wire with standard headers, not vendor headers:

| Header | Standard | Value |
|---|---|---|
| `Deprecation` | RFC 9745 | an RFC 9651 Date naming the notice time, e.g. `@1798761600` |
| `Sunset` | RFC 8594 | an HTTP-date naming the removal date, e.g. `Wed, 30 Jun 2027 00:00:00 GMT` |
| `Link` | `deprecation` relation (RFC 9745) and `successor-version` (RFC 5829) | `<migration-doc-url>; rel="deprecation"` and `<successor-url>; rel="successor-version"` |

The `Deprecation` and `Sunset` examples are one worked `stable` notice, not two unrelated dates — an illustration of the
arithmetic, not an entry in the record: `@1798761600` is `2027-01-01` (a Friday), and `Wed, 30 Jun 2027 00:00:00 GMT`
is exactly 180 days later, the `stable` minimum. The same announcement on a `beta` contract would sunset no earlier
than `Mon, 01 Feb 2027 00:00:00 GMT`, 31 days later.

`Deprecation` is a structured field whose value is a Date; RFC 8594's `Sunset` uses an HTTP-date, and a response's
`Sunset` timestamp must not be earlier than its `Deprecation` timestamp. The former `X-IBEX-Deprecation`,
`X-IBEX-Deprecation-Date`, `X-IBEX-Sunset-Date`, and `X-IBEX-Successor` headers are retired and must not be emitted.

This table is the policy, not an implementation record: no middleware or interceptor in `services/` emits `Deprecation`,
`Sunset`, or `Link` today, and [Deliberately out of scope](#deliberately-out-of-scope) records the gap.

Header enforcement is therefore per surface, because only REST has a standard header to set:

| Surface | `headers_implemented` | What the notice is |
|---|---|---|
| `rest` | `false` until an emitter ships, and `true` before `status` may become `announced` | the three response headers above |
| `grpc` | `false` always: the protocol defines no deprecation response header | the committed record, with the method comment naming the successor |
| `mcp` | `false` always: MCP defines no deprecation header for a tool | the committed record, with the tool description naming the successor |

The flag is a declaration, not an observation: the check reads `headers_implemented` and an `evidence` path that exists,
and neither proves an emitter. A green run never says a `rest` response actually carries the headers. For `grpc` and
`mcp` the record itself is the notice of record, and no HTTP header claim is made for them.

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
| `stability` | `stable` or `beta`. For REST and MCP it must equal the registry row's value. |
| `notice_date`, `sunset_date` | `YYYY-MM-DD`. `notice_date` is when the promise was planned; `sunset_date` is the removal date. |
| `announced_on` | `YYYY-MM-DD`. The date consumers were told. Absent or `null` on a `proposed` or `withdrawn` entry, required once `status` is `announced`, never earlier than `notice_date`, and never later than the day of the check. The support window is measured from this field when it is recorded. |
| `status` | `proposed`, `announced`, or `withdrawn`. |
| `headers_implemented` | Boolean, and per surface: `true` only for `rest`, and only after an emitter ships; `false` for `grpc` and `mcp`, whose protocols define no deprecation header. No `rest` entry reaches `announced` on `false`; `grpc` and `mcp` reach it on `false` because the record is their notice. |
| `evidence` | Repository-relative file. It must exist when the entry is `announced`. |

**An empty `entries` array is the correct 1.0 state.** Nothing is deprecated today, and an empty list proves nothing
is: the record cannot claim a deprecation that does not exist. An entry is added when a deprecation is real, not in
anticipation of one.

`status` moves in one direction: `proposed` while the replacement and migration note are being built, `announced`
once the notice is published — for `rest`, once the headers are implemented as well — and the evidence exists,
`withdrawn` if the plan is cancelled before sunset. `announced_on` is set by the move to `announced`, and that date is
what starts the clock, so it cannot precede `notice_date`, cannot be in the future, and cannot be present while the
entry is `proposed`. A `proposed` or `withdrawn` entry carries `headers_implemented: false`; an `announced` `rest`
entry may not; an `announced` entry whose `sunset_date` has passed fails the check until it is withdrawn.

### The check

```bash
cd services/api && .venv/bin/python scripts/check_deprecations.py
```

The check reads the record and both registries, uses no network, and prints sorted one-line failures. It fails on:

- a window shorter than 180 days (`stable`) or 31 days (`beta`) measured from its announcement date, an `announced`
  entry with no `announced_on`, an `announced_on` earlier than `notice_date` or later than the day of the check, an
  `announced_on` present on a `proposed` or `withdrawn` entry, or any date that is not an exact `YYYY-MM-DD`;
- a `rest` entry whose `contract_id` is absent from the REST registry, or whose `stability` disagrees with that row;
- an `mcp` entry whose `server` is not `operator` or `memory`, whose `tool` is absent from that server's
  `mcp_tools.json`, or whose `stability` disagrees with the tool's descriptor row;
- an empty `successor`, or a `successor` that names the contract itself;
- `headers_implemented: true` on a `grpc` or `mcp` entry, which has no standard header to implement, or on a `rest`
  entry that is still `proposed` or `withdrawn`;
- `status: announced` on a `rest` entry with `headers_implemented: false`, with an `evidence` path that is not an
  existing file inside the repository, or with a `sunset_date` already in the past;
- an unknown `surface`/`stability`/`status` value, an unknown or missing field, a schema id other than
  `ibex.deprecations.v1`, a duplicate `id`, or entries not sorted by `id`.

The same check runs in CI through `services/api/tests/unit/test_deprecations.py`, which
`infra/scripts/api-test-ci.sh` collects in the `api-test` job, so a pull request that records an invalid window or a
phantom contract fails without a workflow change.

### What the check proves, and what it does not

| Question | Answered? | How |
|---|---|---|
| Is the record a valid `ibex.deprecations.v1` document? | **yes** | schema id, exact field set per surface, no unknown fields, enum values, `headers_implemented` boolean, unique `id`, entries sorted by `id` |
| Does every entry keep its class window? | **yes** | `sunset_date` minus the announcement date (`announced_on` when recorded, otherwise `notice_date`) in whole days against 180 (`stable`) / 31 (`beta`); every date field must be an exact `YYYY-MM-DD`, an `announced` entry must carry an `announced_on` no earlier than its `notice_date` and no later than the day of the check, and a `proposed` or `withdrawn` entry must carry none |
| Is the header flag right for the surface? | **yes** | `headers_implemented: true` fails on a `grpc` or `mcp` entry, which has no standard deprecation header, and on a `proposed` or `withdrawn` `rest` entry; an `announced` `rest` entry fails on `false` |
| Can a `grpc` or `mcp` entry be announced without headers? | **yes** | those entries record `headers_implemented: false` and reach `announced` on the record plus an existing `evidence` path; only `rest` must reach `true` first |
| Does a declared `headers_implemented: true` prove an emitter exists? | **no** | the flag is trusted together with an existing `evidence` path; nothing reads a `Deprecation` or `Sunset` header from a running response, so a `rest` entry can announce headers no route sends |
| Does a `rest` entry name a real contract, with the recorded stability? | **yes** | cross-check against [`contracts/rest-route-registry.json`](contracts/rest-route-registry.json) |
| Does an `mcp` entry name a real tool on a known server, with the recorded stability? | **yes** | cross-check against that server's `mcp_tools.json` (`operator` or `memory`), including the tool's recorded `stability` |
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
writes `Deprecation`, `Sunset`, or `Link` today, which is exactly why `headers_implemented` exists: for a `rest` entry it
is the switch that stops a `proposed` entry becoming `announced` before an emitter ships, with existing evidence, while a
`grpc` or `mcp` entry keeps it `false` because the record is its notice. Three further gaps are deliberate:

- a `grpc` entry is validated structurally only: field set, field types, enums, dates, window, successor, evidence and
  status. Its `contract_id` is resolved against no method list, and `<package>.<Service>/<Method>` is not validated as a
  shape, because no committed gRPC method registry exists. gRPC shapes are gated by `buf-breaking` (W5.1) — which runs
  in CI as an advisory job (`continue-on-error: true`) and is not a required check — and by P0-12, as the REST
  registry's `out_of_scope.grpc` records.
- a `rest` entry's `successor` is not required to be a registered contract, because the successor may be a contract
  that does not exist until the new version ships. `successor-version` is a forward pointer, not a current one.
- the MCP descriptor's `deprecated` flag is not cross-checked against this record, and cannot carry the notice:
  `_record()` writes `deprecated: false` for every published tool, and any `true` is a `deprecated-tool` failure ("remove
  it from the surface and run `--update`"). The lifecycle is therefore one fixed sequence. While a tool is inside its
  window it **stays published** and recorded in `mcp_tools.json` with `deprecated: false`, and the entry in
  `contracts/deprecations.json` — its `announced_on`, `sunset_date` and `successor` — is the notice of record. At
  `sunset_date` the tool **and** its entry are removed in the same change. The two halves cannot drift apart in the
  direction that matters: an `mcp` entry resolves against the committed `mcp_tools.json`, so removing the tool while the
  entry remains fails this check as `unknown-tool`, and a leftover `deprecated: true` fails the descriptor check as
  `deprecated-tool`. What the check cannot see is a removal that was never recorded, because it validates what the
  record says and does not scan tool registrations for missing entries; tying a removal to a recorded window before it
  happens is W5.5's remaining work.
