# IBEX Harness — Prompt Files

Reusable prompts for AI-assisted development. Paste file contents into your tool (Cursor, Copilot, Claude, Codex, etc.).

**Always start with** `00-invariants.txt` (or reference it) for implementation and review work.

| File | Use when |
|------|----------|
| `00-invariants.txt` | Paste into any prompt (global invariant block) |
| `01-session-start.txt` | Beginning of every work session |
| `02-assumption-audit.txt` | Hallucination or unverified assumptions appear |
| `03-context-compression.txt` | Long session; preserve state before context loss |
| `04-handoff.txt` | Ending mid-task; hand off to a new session |
| `05-new-service-bootstrap.txt` | Creating a new Go/Python/Next.js service |
| `06-feature-implement.txt` | Feature in an existing service |
| `07-algorithm-implement.txt` | Ranking, drift, rate limiting, etc. |
| `08-security-implement.txt` | Auth, crypto, permissions, RLS |
| `09-test-plan.txt` | Planning tests for a feature or service |
| `10-property-based-testing.txt` | Hypothesis / invariant tests |
| `11-integration-test.txt` | Testcontainers / real dependencies |
| `12-code-review.txt` | Adversarial code review |
| `13-security-review.txt` | Deep security review |
| `14-performance-review.txt` | Proxy / context / hot path changes |
| `15-debugger.txt` | Bug or regression root cause |
| `16-incident-triage.txt` | Production incident |
| `17-spike.txt` | Research before implementation |
| `18-pr-description.txt` | PR description from a diff |
| `19-issue-spec-audit.txt` | Validate an issue before assigning to AI |
| `20-security-ci-audit.txt` | Review changes to CI, security configs, or `.cursorrules` |

Full narrative and usage guide: [PROMPTS.md](../PROMPTS.md).
