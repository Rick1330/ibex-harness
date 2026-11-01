---
description: Bring the heavy local scanners up for the review stage (starts Docker for SonarQube).
---

Bring the local quality scanners online only for as long as the review needs them.

Call the `local_mcp_enable` tool. Default it to the three scanners:

```json
{ "servers": ["codescene", "codacy", "sonarqube"] }
```

Add `"shadcn"` (or `includeShadcn: true`) only when the task touches console UI components.

Then run `/quality-gate`. When the review is finished, run `/review-off` — do not leave the scanners or the container
running.
