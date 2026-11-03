# IBEX Harness: Skills, Tools, Rules, Execution, and Governance Audit

**Date:** 2026-10-02
**Purpose:** Extend the IBEX product strategy to cover skills, tool calls, rules and instructions, permissions, approvals, credentials, sandboxing, workspaces, artifacts, durable runs, context budgets, registries, plugins, evaluation, and governance.

## The missing conclusion

IBEX should not only be a model gateway plus memory service. The complete product opportunity is a **trusted control plane for agentic work**.

An agentic run is not just:

```text
prompt → model → response
```

It is closer to:

```text
identity
  → policy and deployment snapshot
  → skills and instructions
  → tool discovery
  → context and memory
  → model decision
  → approval and capability checks
  → sandboxed execution
  → files, artifacts, and external effects
  → evidence, evaluation, and resumability
```

The central rule should be:

> **Model-visible text can propose, explain, or inform. It cannot grant permission, widen tenant scope, mint credentials, or authorize side effects.**

That distinction must be implemented, not merely documented.

## What the research found

### Skills are portable context packages, not permissions

The Agent Skills format has converged around a directory containing `SKILL.md`, frontmatter with a name and description, and optional scripts, references, and assets. Claude Code, Codex, Letta, OpenHands, Microsoft Agent Framework, and other systems use similar progressive disclosure: advertise metadata first, load the main instructions after activation, and read resources or execute scripts only when necessary.[26] [27] [28]

This is attractive because skills are easy to author, version-control, share, and port between agents. It is also dangerous because a skill can contain executable scripts, network instructions, MCP references, package dependencies, hidden prompt injection, or credential-seeking behavior.

A skill must therefore be treated as a software supply-chain artifact. It needs an immutable digest, source commit, publisher, license, compatibility declaration, declared resources, capability requirements, owner, review status, and revocation state.

The `allowed-tools` field some ecosystems expose must be treated as metadata for review or client behavior. It cannot be the authorization system. Actual permission must come from AuthService and policy at execution time.

IBEX should support the portable `SKILL.md` format and client-specific adapters, while owning:

- Tenant-scoped registry and resolver.
- Immutable storage in MinIO.
- Postgres ownership, ACL, version, and lifecycle state.
- Digest and signature verification.
- Skill scanning and evaluation.
- Progressive loading with context budgets.
- Script execution through a sandboxed worker.
- Capability composition analysis.
- Revocation and audit.

The first safe skill tier should be instruction-only. Shell, network, MCP, secret, and write capabilities should require explicit declarations and stronger review.

### Tools need a real contract

OpenAI, Anthropic, and MCP all use a similar loop: define a named tool and schema, let the model propose a call, execute the call outside the model, then return a correlated result.[29] [30] [31]

Schema correctness is not authorization. A model can emit valid JSON that requests another tenant’s file, a secret, a destructive operation, or an unauthorized recipient.

IBEX should normalize all tool calls into a provider-neutral contract:

```text
ToolDescriptor
  contract_version
  qualified_tool_id
  immutable_tool_version
  descriptor_digest
  publisher/provenance
  input_schema
  output_schema
  side_effect_class
  required_scopes
  allowed_resources
  data_classification
  timeout/deadline
  idempotency_support
  confirmation_policy
  max_input/output_bytes

ToolCall
  call_id
  parent_call_id
  tenant/actor/session/run/trace
  ToolRef
  canonical_arguments
  argument_hash
  policy_snapshot
  approval_reference
  idempotency_key
  deadline
  attempt

ToolResult
  call_id
  status
  retryable
  machine_error_code
  safe_error_message
  validated_structured_output
  content_blocks
  output_hash
  truncation/reference metadata
  provenance
```

Dispatch must require an exact tool reference containing the tool ID, version, descriptor digest, and provider namespace. A registry search may discover candidates, but only a policy decision can make a candidate callable.

Tool descriptions, annotations, schemas, registry metadata, tool arguments, and tool results must all be treated as potentially untrusted. Tool poisoning research has shown that malicious instructions can be hidden in descriptions and that servers can change behavior after approval.[32]

IBEX should use qualified IDs, immutable descriptor versions, descriptor hashes, schema compatibility checks, narrow tool catalogs, and per-tenant discovery. A `list_changed` notification should trigger invalidation and review, not silently grant new execution authority.

### Rules and instructions are context, not enforcement

Claude Code, Cursor, GitHub Copilot, and AGENTS.md all provide persistent repository or project instructions. These are useful for conventions, build commands, architecture notes, and workflow guidance. Their scope and precedence differ across clients.[33] [34] [35]

The same file may be loaded differently by Claude Code, Cursor, Copilot, Codex, or a custom agent. Some clients concatenate all relevant files. Others use closest-file precedence, globs, relevance selection, or personal-over-repository ordering.

IBEX should normalize instruction sources into an `InstructionEnvelope` containing:

- Scope and applicability.
- Authority class.
- Trust level.
- Source URI and content hash.
- Tenant and project ownership.
- Expiry and version.
- Data classification.
- Conflict status.

The authority lattice should be explicit:

```text
IBEX tenancy and hard safety constraints
  > tenant policy and AuthService decisions
  > approved deployment snapshot
  > project/repository guidance
  > user task request
  > stylistic guideline
```

Repository files, issue text, pull requests, web pages, memory, and generated tool output are advisory or untrusted data. They must never override the hard policy layer.

IBEX should provide a loaded-instructions manifest showing which sources were included, omitted, conflicted, or superseded. That will be much more useful than hiding all context in one concatenated prompt.

Hard authorization must be evaluated in the Go proxy/AuthService and at every action boundary. OPA or Cedar could be integrated as policy decision engines, but the application must enforce their structured results; the model must not enforce them.[36] [37]

### Approvals are not a sandbox

Claude Code, Codex, OpenAI Agents, LangGraph, Cursor, and VS Code all demonstrate a similar two-layer model:

1. **Capability enforcement:** what files, processes, networks, credentials, and tools are technically reachable.
2. **Approval policy:** when the agent must pause for a human or policy decision.[38] [39] [40]

Approval is useful, but approval is not a security boundary. Users suffer from approval fatigue, and prompt injection can manipulate what they see or cause them to approve a broader action than intended.

IBEX should separate capability from approval. A capability is a narrow, short-lived grant for an action and resource. An approval authorizes one exact canonical action or a tightly bounded homogeneous set.

Approval records should contain:

- Tenant, subject, agent, run, and resource.
- Tool or operation ID and immutable version.
- Exact canonical arguments and digest.
- Data leaving the tenant and destination.
- Current policy version.
- Reversibility and blast radius.
- Expiry and one-time nonce.
- Reviewer identity and reason.
- Idempotency key.

At execution time, IBEX must re-check the token, tenant, policy epoch, resource version, action digest, expiry, destination, quota, and idempotency state. An approval must not survive material changes to the action.

Use risk tiers instead of one global “auto” or “manual” switch:

- Read-only and low-risk computation.
- Workspace writes in an isolated workspace.
- Guarded writes with conditional approval.
- Auto-review inside a hard sandbox.
- Full-access isolated execution for explicitly controlled infrastructure only.

Cross-tenant access, secret exfiltration, policy mutation, sandbox escape, and disallowed egress should be unconditional denies.

### Sandboxing must be a separate execution plane

IBEX should not execute shell commands inside the Go proxy, AuthService, MCP memory server, or database services.

A worker should execute code under an immutable `ExecutionPolicy` specifying:

- Tenant and run identity.
- Image or VM digest.
- Read/write roots.
- Network and DNS policy.
- CPU, memory, PID, disk, and I/O limits.
- Wall-clock and idle timeouts.
- Secret grants.
- Artifact limits.
- Approval or elevation state.
- Snapshot lineage.

The baseline isolation tier can use rootless OCI containers with namespaces, cgroups, dropped capabilities, `no-new-privileges`, seccomp, and AppArmor or SELinux. Higher-risk or cross-tenant workloads should use gVisor or Firecracker microVMs.[41] [42] [43]

Network access must be deny-by-default and enforced outside the worker. The worker must not be able to disable its own egress policy. Block private, link-local, metadata, and control-plane destinations. Permit only explicit destinations, ports, protocols, and budgets through a host-side egress broker.

Do not inject long-lived keys into the worker environment. Use short-lived credentials from a broker, scoped to the tenant, run, audience, connector, and action. A secret must not appear in model context, ordinary logs, OTel attributes, memory, or snapshots.

There must be no automatic unsandboxed retry. If a sandbox fails, IBEX should return a typed policy or execution error, pause for a separately authorized elevation, or use a different pre-approved isolation tier.

### Credentials need delegation, not impersonation

IBEX should distinguish:

- Human or tenant subject.
- Logical agent.
- Specific run or session.
- Worker workload.
- Connector or tool.
- Downstream resource and audience.

The preferred internal context is a short-lived, signed, audience-bound envelope with subject and actor information. The subject remains the human or tenant owner. The actor identifies the agent, connector, or worker acting on its behalf.

For remote MCP and user connectors, use OAuth authorization-code plus PKCE, protected-resource metadata, exact redirect validation, state/CSRF checks, narrow scopes, and one audience per protected resource.[44] [45]

For workload identity, SPIFFE/SPIRE or an equivalent short-lived mTLS identity is appropriate. For tenant-owned provider keys or APIs without delegated OAuth, use a Vault/KMS-backed broker and retrieve credentials just in time.[46] [47]

Do not pass through arbitrary upstream bearer tokens. Do not let a worker choose its own audience or scope. Downstream tokens should be an intersection of the subject grant, tenant policy, agent policy, connector policy, and requested operation.

### Runs, retries, artifacts, and workspaces need one identity model

A live HTTP or streaming connection is not the durable boundary. OpenAI Background Responses, Letta, LangGraph, and Temporal all demonstrate the importance of persisted state, event history, cursors, cancellation, and idempotency.[48] [49] [50]

IBEX should define:

- `RunEnvelope`.
- `RunEvent`.
- `CheckpointEnvelope`.
- `OperationIntent`.
- `OperationReceipt`.
- `WorkspaceRef`.
- `ArtifactEnvelope`.
- `PatchBundle`.

The durable run state machine should include accepted, queued, running, waiting, cancellation requested, cancelling, cancelled, succeeded, failed, timed out, expired, and force terminated.

Every retry is a new attempt under the same logical run. Every resume starts from an identified checkpoint and cursor. Every fork creates a new run with an explicit parent checkpoint.

Every side effect needs an operation key. If a worker crashes after sending an external request but before recording the receipt, IBEX must reconcile by operation ID rather than blindly repeat the operation.

Postgres should own run state, leases, fencing epochs, checkpoints, idempotency receipts, and outbox rows. MinIO should own immutable large artifacts and snapshots. Redis should only accelerate queues, locks, and short-lived caches. ClickHouse and OTel should be projections, not the recovery source of truth.

### Artifacts must be content-addressed

A branch name, path, session name, or artifact name is not immutable identity. Git offers a useful model: content-addressed blobs and trees, immutable commit snapshots, mutable branch references, and worktree views.[51]

IBEX should represent a workspace using a digest-based `WorkspaceRef`, including base commit or tree, current snapshot, worktree identity, dirty/untracked files, environment image, and lease.

An `ArtifactEnvelope` should include:

- Artifact ID and tenant.
- Kind and media type.
- Size and digest.
- Immutable storage reference.
- Creating run, attempt, step, and actor.
- Sensitivity and trust state.
- Retention class.
- Provenance.

A patch should include its base snapshot digest, target digest when materialized, file operations, per-file preconditions, binary references, and tool/container provenance. A text diff is only a view of a patch, not the full artifact identity.

Large attachments should pass through an artifact gateway with size, MIME, decompression, malware, secret, retention, and tenant checks. Model context should contain bounded excerpts or references, not arbitrary full blobs.

### Context budgets are security and cost controls

Provider documentation confirms that tool definitions, messages, tool results, attachments, retrieved documents, reasoning, and output all consume the effective context window.[52] Tool-search and deferred loading exist because large catalogs degrade tool selection and consume substantial context.[53]

IBEX needs a typed `ContextEnvelope`. Each item should carry tenant, source, trust, provenance, sensitivity, expiry, byte size, token estimate, tokenizer, model, and content hash.

Packing should reserve output and reasoning headroom first. It should separately budget:

- Trusted policy.
- Stable instructions.
- Active skill.
- Tool schemas.
- Conversation tail.
- Summaries and checkpoints.
- Memory.
- Retrieved data.
- Attachments.
- Tool results.

Compaction should preserve source lineage and unresolved decisions. A summary is a new artifact, not a replacement for the original evidence. Cache keys must include tenant, policy version, model, tokenizer, schema and skill versions, and data classification.

The fallback ladder should shrink low-priority data, return continuation handles, compact when allowed, and finally produce a structured context-budget error. It must never silently drop the current user constraints, policy, approval state, or evidence required to explain a decision.

### Plugins and registries require governance

Claude Code plugins, Cursor plugins, VS Code extensions, MCP servers, LangChain integrations, CrewAI tools, and OpenAI Agents extensions show that ecosystem packaging is a powerful adoption mechanism.[54] It also creates arbitrary-code execution, dependency, publisher, update, and compatibility risks.

IBEX should own a private, self-hostable registry overlay. The registry should separate:

- Discovery.
- Automated scanning.
- Security review.
- Owner approval.
- Tenant enablement.
- Runtime authorization.
- Deprecation.
- Revocation.

Use immutable digests, signatures, SBOMs, source commits, accountable owners, compatibility matrices, declared capabilities, and staged rollout. A public registry entry or verification badge should never imply that a tool is trusted for every tenant.

Recommended lifecycle:

```text
draft → submitted → scanned → reviewed → approved → published
→ tenant-enabled → canary → active
```

With parallel states for rejected, suspended, deprecated, revoked, and archived.

High-risk changes should require proposer/approver separation. Owner mappings should be protected and re-certified. Exceptions should be scoped, reasoned, expiring, and audited rather than edits to global policy.

### Evaluation should include the environment

A final answer is not enough. OpenAI and Anthropic evaluation guidance emphasizes traces, tool trajectories, environment outcomes, repeated trials, deterministic graders, model graders, and human review.[55] [56]

IBEX evaluation must test:

- Schema and protocol compatibility.
- Tenant and authorization invariants.
- Tool selection, argument, and ordering constraints.
- Actual database, artifact, and workspace state.
- Side-effect absence after deny.
- Sandbox filesystem and network isolation.
- Citation support and provenance.
- Cost and latency tails.
- Replay and recovery.
- Trace and evidence completeness.

A single aggregate score must not hide one unauthorized side effect or one cross-tenant read. Authentication bypass, tenant leakage, forbidden side effect, sandbox escape, missing evidence, and stale approval must be hard release blockers.

Every evaluation should pin an immutable DeploymentSnapshot containing policy, skills, tools, model/provider, sandbox image, memory snapshot, retrieval index, schemas, and evaluator versions.

## Recommended IBEX control-plane objects

The strategy should add these canonical contracts:

```text
PrincipalContext
PolicyBundle
PolicyDecision
SkillDescriptor
SkillVersion
ToolDescriptor
PluginDescriptor
CapabilityManifest
InstructionEnvelope
ContextEnvelope
ApprovalRequest
ApprovalGrant
ExecutionPolicy
DeploymentSnapshot
RunEnvelope
RunEvent
CheckpointEnvelope
OperationIntent
OperationReceipt
WorkspaceRef
ArtifactEnvelope
PatchBundle
EvalRun
ProvenanceAttestation
```

`DeploymentSnapshot` should be the unit of promotion and execution. It should immutably reference:

- Approved skills, tools, and plugins.
- Policy bundle hash.
- Model/provider configuration.
- Tool and protobuf schema hashes.
- Credential and connector policy.
- Sandbox image or VM digest.
- Context rules.
- Dependency lock.
- Evaluation evidence.
- Rollout and expiry metadata.

A `RunManifest` then adds tenant, principal, workspace, inputs, retrieval/memory snapshot IDs, and trace identity.

## Revised product boundaries

### IBEX should own

- Tenant identity and authorization.
- Policy decision and enforcement.
- Credential brokering and delegated authority.
- Skill, tool, plugin, and policy registry governance.
- Deployment snapshots and immutable resolution.
- Durable runs, approvals, leases, checkpoints, and idempotency.
- Context assembly, memory authorization, provenance, and token budgets.
- Artifact/workspace mediation.
- Sandboxed execution-provider contracts.
- Evidence, replay, evaluation, and release gates.
- Operator and tenant APIs.

### IBEX should integrate rather than own

- Agent Skills and Agent Plugins formats.
- MCP and A2A protocols.
- OpenAI and Anthropic provider semantics.
- OAuth, SPIFFE, Vault, OPA, and Cedar.
- OCI, gVisor, Firecracker, Kubernetes, and network plugins.
- Git, worktrees, GitHub, and CI systems.
- LangGraph, OpenAI Agents, CrewAI, AutoGen, Letta, Claude Code, Codex, Cursor, and Copilot.
- Langfuse and other external evidence systems.

### IBEX should explicitly not become

- A replacement agent runtime.
- A new graph DSL.
- A global MCP marketplace.
- An IDE or coding-agent UX.
- A provider-count competition.
- A public OAuth identity provider.
- A general workflow engine for every business process.
- A shell executor inside the control plane.

## Revised roadmap

### Phase 0: contracts and trust model

Freeze the authority lattice, principal model, trust and taint taxonomy, protobuf envelope repository, lifecycle states, policy/error codes, digest rules, storage ownership, and compatibility matrix.

Create golden fixtures for cross-tenant access, stale digests, poisoned memory, approval replay, duplicate side effects, stale worker leases, and cache-key isolation.

### Phase 1: safe read-only ecosystem

Ship instruction-only skills, read-only tools, a tenant-scoped registry, SKILL.md validation, immutable bundles, loaded-instructions manifests, tool discovery, OTel/ClickHouse events, and explainable effective-policy output.

Disable implicit invocation for new or untrusted packages.

### Phase 2: durable tool calls and runs

Ship ToolCall/ToolResult normalization for OpenAI, Anthropic, and MCP. Add strict schema handling, qualified IDs, descriptor digests, approvals bound to canonical arguments, OperationIntent/Receipt, leases, fencing, cancellation, checkpoints, artifact contracts, and private registry overlays.

### Phase 3: sandboxed execution and credentials

Start with rootless OCI and host-enforced deny-by-default egress. Add gVisor or Firecracker for higher-risk workloads. Add short-lived credentials, setup-versus-agent phases, workspace overlays, artifact scanning, cleanup, and escape/SSRF/secret-exfiltration tests.

There must be no dangerous fallback mode.

### Phase 4: context economics and adapters

Implement preflight token counting, deterministic packing, reference-first tool results, compaction lineage, attachment handling, memory taint and ACL enforcement, cache isolation, and rule/skill adapters for Claude, Codex, OpenHands, Cursor, Copilot, and AGENTS.md.

### Phase 5: governance and evaluation

Add signed DeploymentSnapshots, provenance attestations, staged rollout and rollback, lifecycle enforcement, two-person review for high-risk changes, deterministic replay, sandbox evidence, citation grading, provider conformance, and shadow/warn/deny policy rollout.

## New metrics

Measure:

- Time to first approved tool.
- Skill activation precision and omission rate.
- Percentage of production artifacts pinned and attested.
- Policy decision latency and false-deny rate.
- Approval lead time and approval fatigue.
- Stale approval and stale worker rejection.
- Duplicate and ambiguous side-effect rate.
- Sandbox escape and denied-egress attempts.
- Secret exposure findings.
- Run recovery and cancellation success.
- Artifact and snapshot restore success.
- Context packing cost, compaction ratio, and token drops.
- Tool-call and schema compatibility failures.
- Evidence completeness and replay success.
- Time to revoke a skill, tool, credential, or run.
- Shadow connector or policy bypass signals.

Do not use the number of skills, tools, registry entries, plugins, providers, or average final-answer score as the main success measures.

## Final recommendation

The prior strategy correctly identified IBEX as a self-hostable, multi-tenant agent control and context plane. This audit strengthens the idea:

> **IBEX should govern the complete lifecycle of agentic work, while remaining underneath the agent framework.**

That means controlling the boundary between instructions and policy, discovery and authorization, approval and capability, model output and side effect, workspace and artifact, run and attempt, memory and trusted context, and registry listing and executable code.

The product’s deepest moat will not be a novel prompt format or a larger model catalog. It will be the accumulated correctness of these boundaries:

- A model cannot use memory to widen its authority.
- A skill cannot silently change behavior after approval.
- A tool cannot execute from a mutable reference.
- An approval cannot be replayed for changed arguments.
- A stale worker cannot append or act after lease expiry.
- A sandbox cannot reach another tenant or its credentials.
- A patch cannot be applied to the wrong base without a conflict.
- A registry listing cannot become permission by itself.
- A high average evaluation score cannot hide one forbidden side effect.

That is the version of IBEX that can become genuinely useful to organizations running many different agents and tools.

## References

[26]: https://agentskills.io/specification "Agent Skills specification"
[27]: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview "Anthropic Agent Skills overview"
[28]: https://developers.openai.com/codex/skills "OpenAI Codex skills"
[29]: https://developers.openai.com/api/docs/guides/function-calling "OpenAI function calling"
[30]: https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/handle-tool-calls "Anthropic tool-call handling"
[31]: https://modelcontextprotocol.io/specification/2025-06-18/server/tools "MCP tools specification"
[32]: https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks "MCP tool-poisoning security research"
[33]: https://code.claude.com/docs/en/memory "Claude Code memory and CLAUDE.md"
[34]: https://cursor.com/docs/rules "Cursor rules"
[35]: https://docs.github.com/en/copilot/customizing-copilot/adding-repository-custom-instructions-for-github-copilot "GitHub Copilot repository instructions"
[36]: https://www.openpolicyagent.org/docs "Open Policy Agent documentation"
[37]: https://docs.cedarpolicy.com/ "Cedar authorization documentation"
[38]: https://developers.openai.com/codex/agent-approvals-security "OpenAI Codex approvals and security"
[39]: https://openai.github.io/openai-agents-python/human_in_the_loop/ "OpenAI Agents SDK human-in-the-loop"
[40]: https://docs.langchain.com/oss/python/langchain/human-in-the-loop "LangChain human-in-the-loop middleware"
[41]: https://docs.docker.com/engine/security/ "Docker Engine security"
[42]: https://gvisor.dev/docs/ "gVisor documentation"
[43]: https://github.com/firecracker-microvm/firecracker/blob/main/docs/design.md "Firecracker design and isolation"
[44]: https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/authorization "MCP authorization tutorial"
[45]: https://datatracker.ietf.org/doc/html/rfc8707 "OAuth 2.0 Resource Indicators"
[46]: https://spiffe.io/docs/latest/spiffe-about/overview/ "SPIFFE workload identity"
[47]: https://developer.hashicorp.com/vault/docs/concepts/lease "Vault leases and dynamic secrets"
[48]: https://developers.openai.com/api/docs/guides/background "OpenAI background mode"
[49]: https://docs.langchain.com/oss/python/langgraph/interrupts "LangGraph interrupts"
[50]: https://docs.temporal.io/workflow-execution "Temporal workflow execution"
[51]: https://git-scm.com/book/en/v2/Git-Internals-Git-Objects "Git content-addressed objects"
[52]: https://platform.claude.com/docs/en/build-with-claude/context-windows "Claude context windows"
[53]: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool "Anthropic tool search"
[54]: https://code.claude.com/docs/en/plugins/overview "Claude Code plugins"
[55]: https://developers.openai.com/api/docs/guides/agent-evals "OpenAI agent evaluations"
[56]: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents "Anthropic agent evaluations"
