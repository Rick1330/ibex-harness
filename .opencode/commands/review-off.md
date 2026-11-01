---
description: Put the heavy local scanners back to sleep and stop the SonarQube container and Docker Desktop.
---

Take the local scanners offline. This is not optional — leaving them running wastes memory for the rest of the session.

Call the `local_mcp_disable` tool with no arguments. It will:

- disable `codescene`, `codacy`, `sonarqube`, and `shadcn`;
- stop the SonarQube container;
- stop Docker Desktop if this session started it.

Then call `local_mcp_status` and report the RAM before/after. Remote servers (Exa, Context7, DeepWiki) stay connected;
they cost no local memory.
