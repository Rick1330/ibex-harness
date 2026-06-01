# IBEX Harness — Prompt Library (PROMPTS.md)

## 0) Purpose

This file is a **reusable prompt library** for building IBEX Harness with AI assistance (Cursor, Copilot Chat, Claude, Codex, Gemini CLI, etc.).

It standardizes how you:

- start sessions without losing context
- implement tasks without hallucinating APIs/paths
- enforce security and multi-tenancy invariants
- write tests that actually catch bugs
- do adversarial reviews (security/perf/correctness)
- create resumable handoffs across sessions

**Rule:** For any non-trivial work, use one of these prompts rather than free-form chatting.

**Canonical prompt text:** Each prompt lives in [`prompts/`](prompts/) as a separate `.txt` file. Copy the file contents into your tool. See [`prompts/README.md`](prompts/README.md) for the index.

---

## 1) How to Use This Library

### 1.1 Pick the right agent “role”

When you engage an AI tool, choose the role explicitly:

- Implementer (writes code + tests)
- Reviewer (adversarial code review)
- Security reviewer (threat model + auth/tenant checks)
- Test writer (integration/property tests)
- Debugger (root-cause analysis)
- Spike researcher (prototype/benchmark)
- Docs writer (API/schema/ADR updates)

### 1.2 Provide repository anchors (anti-hallucination)

In every implementation prompt, include:

- [docs/roadmap/CURRENT_STATE.md](docs/roadmap/CURRENT_STATE.md) and the active milestone under `docs/roadmap/phase-*/milestones/` when implementing planned work
- relevant file paths that already exist (or confirm none exist)
- references to at least 1 similar file/module pattern
- “what is allowed to change” vs “must not change”

If the tool cannot inspect the repo:

- paste relevant file listings (tree) and key file contents as context
- ask it to propose changes only after that

### 1.3 Stop conditions

If the model starts inventing:

- file paths that don’t exist
- APIs/methods not present
- schema tables not defined

You must stop and re-run using the **Assumption Audit Prompt** ([`prompts/02-assumption-audit.txt`](prompts/02-assumption-audit.txt)).

---

## 2) Global “Invariant Block” (Paste into every prompt)

Copy/paste from [`prompts/00-invariants.txt`](prompts/00-invariants.txt) into the top of any prompt to enforce consistency.

---

## 3) Session Prompts

### 3.1 Session Start / Orientation Prompt

**Goal:** prevent context loss; force the agent to restate constraints and plan.

**File:** [`prompts/01-session-start.txt`](prompts/01-session-start.txt)

Paste `00-invariants.txt` where indicated before sending.

---

### 3.2 Assumption Audit Prompt

**Goal:** use when hallucination or uncertainty appears.

**File:** [`prompts/02-assumption-audit.txt`](prompts/02-assumption-audit.txt)

---

### 3.3 Context Compression Prompt

**Goal:** use when a session is long and model quality degrades.

**File:** [`prompts/03-context-compression.txt`](prompts/03-context-compression.txt)

---

### 3.4 Session End / Handoff Prompt

**Goal:** mandatory when you stop mid-task.

**File:** [`prompts/04-handoff.txt`](prompts/04-handoff.txt)

---

## 4) Implementation Prompts

### 4.1 New Service Bootstrap Prompt (Go / Python / Next.js)

**Use when:** creating a new service from scratch.

**File:** [`prompts/05-new-service-bootstrap.txt`](prompts/05-new-service-bootstrap.txt)

---

### 4.2 Feature Implementation Prompt (existing service)

**File:** [`prompts/06-feature-implement.txt`](prompts/06-feature-implement.txt)

---

### 4.3 Algorithm Implementation Prompt (ranking/drift/rate limiting)

**File:** [`prompts/07-algorithm-implement.txt`](prompts/07-algorithm-implement.txt)

---

### 4.4 Security-Sensitive Implementation Prompt (auth, crypto, permissions, RLS)

**File:** [`prompts/08-security-implement.txt`](prompts/08-security-implement.txt)

---

## 5) Testing Prompts

### 5.1 Test Plan Prompt

**File:** [`prompts/09-test-plan.txt`](prompts/09-test-plan.txt)

---

### 5.2 Property-Based Testing Prompt (Hypothesis / invariants)

**File:** [`prompts/10-property-based-testing.txt`](prompts/10-property-based-testing.txt)

---

### 5.3 Integration Test Prompt (Testcontainers discipline)

**File:** [`prompts/11-integration-test.txt`](prompts/11-integration-test.txt)

---

## 6) Review Prompts (Adversarial Quality Gates)

### 6.1 General Code Review Prompt

**File:** [`prompts/12-code-review.txt`](prompts/12-code-review.txt)

---

### 6.2 Security Review Prompt (Deep)

**File:** [`prompts/13-security-review.txt`](prompts/13-security-review.txt)

---

### 6.3 Performance Review Prompt (Proxy/context critical path)

**File:** [`prompts/14-performance-review.txt`](prompts/14-performance-review.txt)

---

## 7) Debugging & Incident Prompts

### 7.1 Debugging Prompt (root cause, no guessing)

**File:** [`prompts/15-debugger.txt`](prompts/15-debugger.txt)

---

### 7.2 Incident Triage Prompt (production)

**File:** [`prompts/16-incident-triage.txt`](prompts/16-incident-triage.txt)

---

## 8) Research / Spike Prompts

### 8.1 Spike Prompt (prototype/benchmark)

**File:** [`prompts/17-spike.txt`](prompts/17-spike.txt)

---

## 9) PR Description / Changelog Prompts

### 9.1 PR Description Generator Prompt

**File:** [`prompts/18-pr-description.txt`](prompts/18-pr-description.txt)

---

## 10) “Issue Spec Quality Checker” Prompt

Use this before giving an AI agent an issue to implement.

**File:** [`prompts/19-issue-spec-audit.txt`](prompts/19-issue-spec-audit.txt)

---

## 11) Prompt Directory Layout

One prompt per file (recommended for Cursor, Copilot, and CLI tools):

```text
prompts/
  README.md
  00-invariants.txt
  01-session-start.txt
  02-assumption-audit.txt
  03-context-compression.txt
  04-handoff.txt
  05-new-service-bootstrap.txt
  06-feature-implement.txt
  07-algorithm-implement.txt
  08-security-implement.txt
  09-test-plan.txt
  10-property-based-testing.txt
  11-integration-test.txt
  12-code-review.txt
  13-security-review.txt
  14-performance-review.txt
  15-debugger.txt
  16-incident-triage.txt
  17-spike.txt
  18-pr-description.txt
  19-issue-spec-audit.txt
```

Implementation prompts reference `prompts/00-invariants.txt` instead of duplicating the invariant block.

---

## 12) What You Should Do Next (first day checklist)

1. Put `.cursorrules` in repo root (already drafted)
2. Put `AGENTS.md` in repo root (already drafted)
3. Put `PROMPTS.md` in repo root; use `prompts/*.txt` for copy-paste
4. Start with a single bootstrap PR:
   - infra compose
   - 1 service skeleton (auth or proxy)
   - migrations scaffolding
5. Use **Session Start** (`01-session-start.txt`) before every AI-assisted change
6. Use **Security Review** (`13-security-review.txt`) on any auth/tenant work
7. Use **Issue Spec Audit** (`19-issue-spec-audit.txt`) before writing large issues
