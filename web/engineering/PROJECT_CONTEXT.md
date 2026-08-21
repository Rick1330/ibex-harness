# IBEX Harness - Project Context

## 🎯 Project Vision

IBEX Harness is a production-grade AI agent memory and context management platform designed to give AI agents persistent memory, behavioral consistency, and contextual awareness across sessions and interactions.

## 💡 The Problem We're Solving

### Current State of AI Agents
Modern AI agents suffer from critical limitations:

1. **No Persistent Memory**: Every conversation starts from scratch. Agents cannot remember previous interactions, learned preferences, or accumulated knowledge.

2. **Context Loss**: Agents lose important context as conversations grow, leading to degraded performance and contradictory behavior.

3. **No Behavioral Consistency**: Without memory of past decisions and patterns, agents cannot maintain consistent behavior over time.

4. **No Cross-Session Learning**: Knowledge gained in one session is lost when the session ends.

5. **No Drift Detection**: When agent behavior changes over time (often degrading), there's no mechanism to detect and correct it.

6. **Manual Context Management**: Developers must manually manage what context to provide to agents, leading to inefficiency and errors.

## ✨ What IBEX Harness Provides

### Core Capabilities

**1. Persistent Memory System**
- Agents can write, store, and retrieve memories across sessions
- Semantic search over memory using vector embeddings
- Automatic memory extraction from agent interactions
- Memory deduplication and conflict resolution
- Multi-tenant isolation with enterprise-grade security

**2. Intelligent Context Assembly**
- Automatic retrieval of relevant memories for each agent interaction
- Smart ranking algorithm that balances recency, relevance, and usefulness
- Context budget management that fits within LLM token limits
- Performance-optimized assembly pipeline (<50ms overhead)

**3. Behavioral Fingerprinting & Drift Detection**
- Statistical tracking of agent behavior patterns
- Automatic detection when behavior drifts from expected patterns
- Alerting system for behavioral anomalies
- Baseline establishment and evolution over time

**4. Session Management**
- Robust session lifecycle management
- Crash recovery with checkpoint/resume capability
- Agent Transaction Protocol (ATP) for reliable multi-step operations
- Loop detection to prevent runaway agents

**5. Directive Versioning System**
- Version control for agent instructions and system prompts
- A/B testing of directive changes
- Behavioral regression testing before directive promotion
- Live session transition during directive updates
- Emergency revocation capability

**6. Developer Experience**
- SDKs for Python, TypeScript, and Go
- CLI for memory management and session inspection
- Web dashboard for visualization and management
- Integrations with LangChain, AutoGen, CrewAI, LlamaIndex
- VS Code and Cursor extensions for development workflow

## 🎪 Target Users

### Primary Users

**1. AI Agent Developers**
- Building production AI agents that need memory
- Need to debug agent behavior across sessions
- Want to improve agent consistency and reliability
- Require enterprise-grade security and isolation

**2. AI Product Teams**
- Shipping AI-powered products to customers
- Need to manage agent behavior at scale
- Require visibility into agent decision-making
- Must ensure agent quality and safety

**3. AI Researchers**
- Experimenting with agent memory architectures
- Need to track agent behavior over long-running experiments
- Want to analyze agent learning patterns

### Secondary Users

**4. Enterprise IT/DevOps**
- Deploying and managing IBEX Harness infrastructure
- Monitoring system health and performance
- Managing multi-tenant security and isolation

**5. Data Scientists**
- Analyzing agent behavior patterns
- Optimizing memory retrieval and ranking
- Tuning drift detection parameters

## 📊 Success Metrics

### Product Metrics

**Adoption Metrics**
- Monthly Active Agents: Target 10,000 in year 1
- Memory Operations per Day: Target 1M in year 1
- SDK Downloads: Growth rate target 20% MoM
- Enterprise Customers: Target 50 in year 1

**Quality Metrics**
- Memory Retrieval Accuracy: >85% relevance score from users
- Context Assembly Latency: p95 < 50ms
- System Uptime: 99.9% SLA
- Memory Write Success Rate: >99.9%

**Engagement Metrics**
- Memories per Agent: Average >1,000
- Session Retention: >40% of agents active after 30 days
- Dashboard DAU: >30% of agent owners check dashboard weekly
- Integration Adoption: >60% of users use at least one integration

### Business Metrics

**Revenue Metrics**
- ARR: Target $5M in year 1
- Average Revenue per Agent: Target $50/month
- Enterprise Contract Value: Average $50k/year
- Gross Margin: Target >80%

**Efficiency Metrics**
- Cost per 1M Memory Operations: <$10
- Infrastructure Cost as % of Revenue: <20%
- Customer Acquisition Cost: <$500
- Customer Lifetime Value: >$5,000

## 🔧 Technical Success Criteria

### Performance Requirements

**Latency Targets**
- LLM Proxy Request Overhead: <20ms added latency
- Context Assembly: p95 <50ms, p99 <100ms
- Memory Write: p95 <200ms
- Memory Search: p95 <100ms
- Dashboard Page Load: <2s on 3G

**Throughput Targets**
- Concurrent Agent Sessions: 10,000+
- Memory Writes per Second: 1,000+
- Memory Searches per Second: 5,000+
- LLM Requests Proxied per Second: 1,000+

**Scale Targets**
- Memories per Agent: Support 1M+
- Total Memories in System: Support 10B+
- Total Agents: Support 1M+
- Organizations: Support 10,000+

### Reliability Requirements

**Availability**
- System Uptime: 99.9% (8.76 hours downtime per year)
- Planned Maintenance Windows: <4 hours per quarter
- Mean Time to Recovery: <30 minutes
- Data Durability: 99.999999999% (11 nines)

**Data Integrity**
- Zero data loss for committed memory writes
- Eventual consistency acceptable for analytics
- Strong consistency required for memory reads
- ACID guarantees for critical operations

**Security Requirements**
- Multi-tenant isolation: 100% guarantee (no cross-tenant data access)
- Encryption at rest: AES-256 for all data
- Encryption in transit: TLS 1.3 minimum
- SOC 2 Type II compliance
- GDPR compliance including right to erasure
- Authentication: Support for SSO, MFA
- Authorization: Role-based access control

## 🌍 Deployment Models

### Cloud (Primary)
- Fully managed SaaS offering
- Multi-region deployment (US, EU, Asia)
- Auto-scaling infrastructure
- Managed monitoring and alerting
- Automated backups and disaster recovery

### Self-Hosted (Enterprise)
- Complete on-premises deployment
- Kubernetes-based architecture
- Customer-managed infrastructure
- Air-gapped deployment support
- Custom compliance requirements

### Hybrid
- Proxy in customer environment
- Core platform in IBEX cloud
- Data residency compliance
- Custom integration requirements

## 📅 Project Phases (redesigned roadmap)

Phases **0–2 are complete**. The public source of truth for milestones is
[`web/content/roadmap/`](../content/roadmap/) ([overview](https://ibexharness.com/roadmap/overview),
[current state](https://ibexharness.com/roadmap/current-state)). Calendar “months” below are
planning orientation only — not commitments.

| Phase | Name | Status | What it delivers |
| --- | --- | --- | --- |
| 0 | Foundation | **Complete** | Monorepo, CI, compose, proto, Go skeletons |
| 1 | Core Platform | **Complete** | Migrations, auth, proxy platform, security gates |
| 1.5 | Public Web Product | **Complete** | Unified site at ibexharness.com |
| 2 | Single Provider E2E | **Complete** | Authenticated OpenAI-compatible chat through the proxy |
| **2.5** | Provider Generalization & Foundation | **Next** | Anthropic + self-hosted adapters, tokenizer, response pipeline, embedder, schema pre-work, MCP skeleton |
| **3** | Core Memory Substrate | Planned | Memory schema v2 (HNSW), write pipeline, read/ranking, hot cache |
| **3.5** | Extraction & Context Assembly | Planned | Celery extraction worker, context assembly on the proxy hot path, MCP memory tools |
| **4** | Operator Platform & Multi-Provider | Planned | Management API, dashboard, multi-provider routing, hierarchical rate limiting |
| **4.5** | Intelligence Layer | Planned | Behavioral fingerprinting, drift detection, directive regression testing |
| **5** | Advanced Retrieval & Graph Memory | Planned | Hybrid search (dense+sparse+reranking), graph traversal, evaluation harness |

**Important redesign notes** (see [findings](https://ibexharness.com/roadmap/findings)):

- Phase 3 is **memory substrate only** — extraction and context assembly moved to **3.5**.
- Management API + operator dashboard land in **Phase 4** (not a separate early DX phase).
- Intelligence work that used to look like a late “Phase 6” is absorbed into **4.5**.
- Org-wide production hardening (full observability stack, chaos, release governance) is **deferred beyond Phase 5** as future roadmap scope; per-phase exit gates still cover hardening for that phase’s surfaces.

### Capability → phase mapping (high level)

| Capability | Preferred phase |
| --- | --- |
| Multi-provider adapters, tokenizer, embedder, MCP skeleton | 2.5 |
| Memory schema, vector store, write/read pipelines | 3 |
| Extraction workers, context assembly gRPC, MCP tools | 3.5 |
| Management API, dashboard, BYO keys, circuit breakers | 4 |
| Fingerprints, drift, directive regression | 4.5 |
| Hybrid retrieval, graph lineage at query time | 5 |

Service and package inventories: [`services/README.md`](../../services/README.md), [`packages/README.md`](../../packages/README.md).

---

## 🎨 Design Principles

### Technical Principles

1. **Performance First**: Every millisecond matters in the critical path (proxy, context assembly)
2. **Security by Default**: Multi-tenant isolation at every layer, encryption everywhere
3. **Fail Gracefully**: Degraded functionality better than complete failure
4. **Observable**: Every operation emits metrics, logs, and traces
5. **Simple Deployment**: Should run locally with one command
6. **Scalable Architecture**: Horizontal scaling for all services
7. **Data Integrity**: Never lose committed data, even in failure scenarios

### Product Principles

1. **Developer-First**: Optimized for developer workflow and debugging
2. **Batteries Included**: Works out of the box with sensible defaults
3. **Extensible**: Easy to integrate with existing agent frameworks
4. **Transparent**: Agents and developers can understand what memories were used and why
5. **Reliable**: Consistent behavior that developers can depend on
6. **Fast**: Low enough latency to use in production without compromise

## 🚫 Explicit Non-Goals (near-term product)

To keep focus through Phase 5, we explicitly defer or narrow:

1. **Multi-modal memory**: text-first; no image/audio/video memories as a v1 requirement
2. **Federated memory sharing**: single-org tenancy model
3. **Real-time multi-writer collaboration**: single-writer per agent session as the default
4. **Custom proprietary ML training pipelines**: use standard embedding / reranker models behind pluggable backends
5. **Mobile SDKs**: server-side SDKs (Python, TypeScript, Go) first
6. **Edge runtime**: cloud or self-hosted Kubernetes-style deploy; no edge agent runtime requirement
7. **Dedicated graph database as a default**: Phase 5 starts with Postgres recursive CTEs over `memory_relationships`; a separate graph DB only with evidence + ADR
8. **Org-wide production-hardening phase as a numbered roadmap gate**: deferred beyond Phase 5 (observability stack, chaos, release governance) — track as future scope
9. **Framework integrations marketplace**: LangChain/AutoGen/etc. plugins remain post-Phase-5 product expansion unless pulled forward with evidence

If implementation needs to deviate, record an ADR and update this document plus the public roadmap.

## 🎯 Definition of Success

IBEX Harness will be considered successful when:

1. **Developers adopt it**: 1,000+ production agents using IBEX Harness
2. **It works reliably**: 99.9% uptime with <50ms added latency
3. **Customers pay for it**: $1M ARR with >50 paying customers
4. **Quality is high**: >4.5/5 satisfaction score from users
5. **Community grows**: Active community contributing integrations and examples
6. **It solves the problem**: Measurable improvement in agent consistency and capability

When these criteria are met, we will have validated that IBEX Harness solves a real problem in a way that customers value.

---

## 📝 Notes for AI Agents Working on This Project

This document is the source of truth for **what** we are building and **why**. When implementing any feature, refer back to this document to ensure alignment with:

- The core problem we're solving
- The users we're serving  
- The success metrics we're targeting
- The technical constraints we must satisfy
- The principles that guide our decisions

If implementation requires deviating from anything in this document, that deviation should be explicitly discussed, documented in the decision log, and this document updated to reflect the new understanding.
