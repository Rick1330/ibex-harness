# IBEX Harness - System Architecture

## 🏗️ Architecture Overview

IBEX Harness is a distributed system designed for high performance, reliability, and scalability. The architecture follows microservices principles with clear service boundaries, while maintaining tight latency requirements for the critical path.

## 📐 System Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                          Agent Applications                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│  │ Python   │  │TypeScript│  │   Go     │  │   CLI    │                │
│  │   SDK    │  │   SDK    │  │   SDK    │  │   Tool   │                │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘                │
└───────┼─────────────┼─────────────┼─────────────┼────────────────────────┘
        │             │             │             │
        └─────────────┴─────────────┴─────────────┘
                          │
                    ┌─────▼─────┐
                    │   LLM     │
                    │   Proxy   │ ◄──────── Critical Path (Go)
                    │  Service  │           <20ms overhead target
                    └─────┬─────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
   │  Auth   │      │Context  │      │ Memory  │
   │ Service │      │Assembly │      │ Service │
   │   (Go)  │      │  Engine │      │ (Python)│
   └────┬────┘      │ (Python)│      └────┬────┘
        │           └────┬────┘            │
        │                │                 │
        │           ┌────▼────┐            │
        │           │Embedding│            │
        │           │ Service │            │
        │           │ (Python)│            │
        │           └────┬────┘            │
        │                │                 │
   ┌────▼────────────────▼─────────────────▼────┐
   │           Infrastructure Layer              │
   ├──────────────────────────────────────────────┤
   │  PostgreSQL  │  Redis   │ ClickHouse │ MinIO│
   │   (Primary)  │ (Cache)  │ (Analytics)│ (S3) │
   └──────────────────────────────────────────────┘
                          │
   ┌──────────────────────▼─────────────────────┐
   │       Background Workers (Python/Celery)   │
   │  • Memory Extraction  • Conflict Detection │
   │  • Fingerprinting     • Drift Detection    │
   │  • Notification       • Garbage Collection │
   └────────────────────────────────────────────┘
                          │
   ┌──────────────────────▼─────────────────────┐
   │         Operator Interfaces                │
   │  ┌─────────┐  ┌─────────┐  ┌─────────┐   │
   │  │Dashboard│  │   API   │  │ Admin   │   │
   │  │(Next.js)│  │ Server  │  │  Tools  │   │
   │  └─────────┘  │(Python) │  └─────────┘   │
   │               └─────────┘                 │
   └────────────────────────────────────────────┘
```

## 🎯 Design Philosophy

### Critical Path Optimization

The **critical path** is the LLM proxy request flow:

```text
Agent Request → Proxy → Context Assembly → LLM Provider → Proxy → Agent Response
```

**Every service in this path must be:**

- Extremely low latency (<50ms total added)
- Highly available (circuit breakers, fallbacks)
- Horizontally scalable
- Monitored at millisecond granularity

**Everything else can be asynchronous** - memory extraction, behavioral analysis, conflict detection, notifications - none of these block the agent's LLM call.

### Fail Gracefully, Never Fail Hard

Every component has explicit fallback behavior:

- Auth service down → Use cached permissions (with audit flag)
- Context assembly timeout → Return directive-only context
- Memory service slow → Serve from hot cache only
- Embedding service down → Queue writes, succeed synchronously with placeholder

### Multi-Tenancy First

Isolation is enforced at **every layer**:

- **Database**: PostgreSQL Row-Level Security on every table
- **Cache**: Redis key namespacing by org_id
- **Search**: Vector index filtered by org_id
- **Application**: Permission checks before every operation
- **Audit**: Every action logged with org_id and user_id

### Observable Everything

Every operation emits:

- **Metrics**: Counters, gauges, histograms (Prometheus)
- **Logs**: Structured JSON logs (severity, trace_id, org_id)
- **Traces**: Distributed traces across services (OpenTelemetry)
- **Events**: Business events for analytics (ClickHouse)

## 🔧 Core Services

### 1. LLM Proxy Service (Go)

**Purpose**: Intercept every LLM request, inject context and memory, forward to provider

**Technology**: Go 1.21+

- Chosen for: Low latency, excellent concurrency, single-binary deployment
- Package layout: Standard Go project layout (cmd/, internal/, pkg/)

**Key Responsibilities**:

- Parse and validate incoming LLM requests
- Authenticate requests via token validation (bloom filter → LRU cache → Auth Service)
- Rate limit enforcement (Redis Lua scripts, hierarchical: agent/org/global)
- Parallel context retrieval (40ms deadline):
  - Directive from Redis
  - Hot memories from Redis
  - Recent conversation history from session store
- gRPC call to Context Assembly Engine
- Memory injection into LLM request (model-aware strategy)
- Streaming response handling:
  - Simultaneous forwarding to agent (real-time UX)
  - Accumulation for post-processing
- Async operations (non-blocking):
  - Trace emission to ClickHouse
  - Memory extraction job trigger
  - Metrics and logging

**Performance Characteristics**:

- Target latency overhead: <20ms (p99)
- Throughput: 1000+ requests/sec per instance
- Concurrency: 10,000+ simultaneous connections
- Memory: <500MB per instance

**Scaling Strategy**:

- Stateless, horizontally scalable
- Load balanced (round-robin or least-connections)
- Auto-scale on CPU >70% or request queue depth

**Critical Dependencies**:

- Redis (for auth cache, rate limiting, hot memories)
- Auth Service (for token validation on cache miss)
- Context Assembly Engine (gRPC)
- LLM Providers (OpenAI, Anthropic, etc.)

**Failure Modes and Handling**:

| Failure | Detection | Handling | Impact |
|---------|-----------|----------|--------|
| Auth Service down | 3 consecutive timeouts | Use disk-cached permissions (5min TTL) | Degraded auth, flagged in audit |
| Context Assembly timeout | 40ms deadline | Return directive-only context | Reduced quality, not failure |
| Memory Service slow | Latency >100ms | Skip memory retrieval, log warning | Degraded quality |
| LLM Provider down | Connection refused or 5xx | Circuit breaker (5 failures → open) | Return 503 with retry-after |
| Redis down | Connection error | Local in-memory fallback (conservative limits) | Degraded rate limiting |

---

### 2. Memory Service (Python/FastAPI)

**Purpose**: Write, store, deduplicate, and retrieve agent memories

**Technology**: Python 3.11+, FastAPI, SQLAlchemy 2.0 (async)

- Chosen for: Rich ML ecosystem, async support, rapid development
- Framework: FastAPI for automatic OpenAPI, native async, dependency injection

**Key Responsibilities**:

- **Memory Write Pipeline**:
  1. Input validation and sanitization
  2. PII detection and redaction
  3. Content deduplication (hash check)
  4. Embedding generation (async call to Embedder)
  5. Near-duplicate detection (vector similarity)
  6. Conflict detection trigger (if near-duplicate found)
  7. Database write (PostgreSQL with vector)
  8. Hot cache write (Redis)
  9. Index update (pgvector, async)

- **Memory Retrieval**:
  1. Semantic search (vector similarity)
  2. Filtering (org_id, agent_id, session_id, category, tags)
  3. Ranking (composite score: relevance + recency + usefulness)
  4. Permission enforcement (org-level, agent-level, session-level visibility)

- **Memory Management**:
  - CRUD operations via REST API
  - Bulk operations (import/export)
  - Memory versioning and history
  - Soft delete with retention period
  - GDPR-compliant deletion (cascade with audit trail)

- **Conflict Resolution**:
  - Detect contradictions, overlaps, supersession
  - Apply resolution strategies (configurable)
  - Confidence score propagation
  - Audit trail of resolutions

**Data Model**:

```python
Memory:
  id: UUID
  org_id: UUID (indexed, RLS enforced)
  agent_id: UUID (indexed)
  session_id: UUID (optional, indexed)
  content: TEXT
  content_hash: VARCHAR(64) (SHA-256, indexed for dedup)
  embedding: VECTOR(384) (MiniLM-L6-v2 dimension)
  category: ENUM (factual, preference, behavioral, episodic)
  confidence: DECIMAL(3,2) (0.00 to 1.00)
  source: ENUM (extracted, user_provided, imported)
  status: ENUM (active, superseded, merged, archived)
  metadata: JSONB (flexible schema)
  created_at: TIMESTAMPTZ
  updated_at: TIMESTAMPTZ
  last_retrieved_at: TIMESTAMPTZ
  retrieval_count: INTEGER
```

**Indexes**:

- `idx_memories_org_agent` on (org_id, agent_id) WHERE status='active'
- `idx_memories_content_hash` on (content_hash)
- `idx_memories_embedding` USING ivfflat (embedding vector_cosine_ops)
- `idx_memories_search` USING gin(to_tsvector('english', content))

**Performance Characteristics**:

- Write latency: p95 <200ms (including embedding)
- Search latency: p95 <100ms (up to 10M memories)
- Throughput: 500 writes/sec, 2000 searches/sec per instance

**Scaling Strategy**:

- Horizontal scaling of API instances (stateless)
- Read replicas for PostgreSQL (search queries)
- Transition to dedicated vector DB (Qdrant) at 50M+ vectors per tenant

---

### 3. Context Assembly Engine (Python)

**Purpose**: Assemble the optimal context for each LLM request within token budget

**Technology**: Python 3.11+, gRPC server

- Chosen for: Complex ranking logic, ML integration, gRPC for low-latency RPC

**Algorithm**:

```text
Input:
  - Query (current conversation turn)
  - Agent ID
  - Session ID
  - Model (determines context window)
  - Directive version

Output:
  - Assembled context string ready for LLM injection

Process:
1. Calculate token budget:
   - Total = model context window (e.g., 128k for GPT-4 Turbo)
   - Reserve 15% for LLM response (min 500, max 4096)
   - Reserve 10% safety buffer
   - Remaining = usable budget

2. Allocate budget (priority order):
   - Directive: always included in full (typically 500-2000 tokens)
   - Recent conversation: last N turns until budget consumed
   - Tool schemas: if applicable
   - Memories: remaining budget

3. Parallel retrieval (shared 40ms deadline):
   - Directive: Redis lookup (hot path, <1ms)
   - Hot memories: Redis sorted set (agent-specific, <5ms)
   - Cold memories: Semantic search (vector similarity, <30ms)

4. Rank memories (composite score):
   Score = 0.40 × relevance_score       (cosine similarity)
         + 0.25 × recency_score          (exponential decay)
         + 0.20 × usefulness_score       (historical feedback)
         + 0.10 × confidence_score       (memory quality)
         + 0.05 × access_frequency_score (proven value)

5. Greedy knapsack packing:
   - Sort by score (descending)
   - Add memories in order until budget exhausted
   - Skip memories that don't fit, try next

6. Compression (if needed):
   - If top memories are too large, summarize lowest-ranked
   - Use lightweight compression model (7B local)
   - Trade verbosity for coverage

7. Format and inject:
   - Order: Directive → Procedural → Declarative → Episodic → Tools → History
   - Wrap in structured delimiters (XML-style with session nonce)
   - Return complete context string
```

**Performance Characteristics**:

- Target latency: p95 <50ms, p99 <100ms
- Budget calculation: <1ms
- Memory ranking (100 candidates): <10ms
- Packing algorithm: <5ms
- Context formatting: <2ms

**Optimization Techniques**:

- Embedding search: ANN (approximate nearest neighbor) for >1M vectors
- Ranking: Pre-computed scores cached in Redis for hot memories
- Budget allocation: Static allocation until proven bottleneck
- Format: Template-based string building (not concatenation)

---

### 4. Embedding Service (Python)

**Purpose**: Generate vector embeddings for all text (memories, queries)

**Technology**: Python 3.11+, sentence-transformers, FastAPI

- Chosen for: HuggingFace ecosystem, model flexibility

**Model**: `all-MiniLM-L6-v2`

- Dimensions: 384
- Performance: ~3000 sentences/sec on CPU, 10k+/sec on GPU
- Quality: Optimized for semantic similarity
- Size: 90MB model file

**Batching Strategy**:

```text
Requests arrive → Accumulate in batch buffer → Process when:
  - Buffer size >= 64 items, OR
  - Time since first item >= 50ms

Rationale:
- Batching dramatically improves GPU utilization
- 50ms timeout keeps latency acceptable for context assembly
- 64 items empirically optimal for this model on T4 GPU
```

**API**:

```http
POST /embed
Request: { texts: ["text1", "text2", ...] }
Response: { embeddings: [[0.1, 0.2, ...], [...]], model: "all-MiniLM-L6-v2" }
```

**Scaling**:

- Multiple instances behind load balancer
- GPU instances for production (T4 or better)
- CPU-only instances acceptable for development
- Auto-scale on queue depth (>100 items waiting)

**Model Upgrade Strategy**:

```text
When upgrading embedding model (e.g., to larger, better model):
1. Deploy new Embedder alongside old
2. Dual-write: compute both embeddings
3. Add new_embedding column to memories table
4. Background job: re-embed all memories (priority: most-accessed first)
5. Transition search to new_embedding when 99% complete
6. Retain old_embedding for 90 days (rollback capability)
7. Drop old_embedding column
```

---

### 5. Authentication Service (Go)

**Purpose**: Centralized authentication and authorization

**Technology**: Go 1.21+

- Chosen for: High throughput, low latency, security-critical path

**Token Types**:

1. **Personal Access Token (PAT)**:
   - Long-lived (no expiry unless revoked)
   - Created by users for SDK usage
   - Hashed with Argon2id before storage via `packages/crypto` ([ADR-0010](adr/ADR-0010-cryptography-policy.md))
   - Never stored in plaintext after creation

2. **Organization Token**:
   - Scoped to organization
   - Permission bitmap (64-bit integer)
   - Used by production agents
   - Rotatable without agent restart

3. **Session Token (JWT)**:
   - Short-lived (1 hour)
   - For dashboard and API sessions
   - RS256 signed with key rotation support
   - Includes claims: org_id, user_id, permissions

4. **Service Token**:
   - Internal service-to-service
   - Auto-rotated every 24 hours
   - Mutual TLS optional for extra security

5. **Marketplace Token**:
   - Scope-limited to marketplace operations
   - For third-party directive publishers

**Validation Pipeline** (in Proxy):

```text
1. Bloom Filter Check (Redis):
   - False positive rate: 0.01%
   - Immediately reject invalid tokens
   - ~1ms check time

2. LRU Cache Check (In-memory):
   - Size: 10,000 entries
   - TTL: 30 seconds
   - Hit rate: ~95% in production
   - ~0.1ms check time

3. Auth Service Call (gRPC):
   - Only on cache miss
   - Returns: permissions bitmap, org_id, agent_id, expiry
   - Cache result for 30s
   - ~5ms call time
```

**Permission Bitmap** (64 bits):

```text
Bit Position | Permission
-------------|----------------------------------
0-7          | Memory operations (read, write, delete, etc.)
8-15         | Directive operations (read, write, promote, revoke)
16-23        | Session operations (create, read, terminate)
24-31        | Trace operations (read, export)
32-39        | Admin operations (user management, billing)
40-47        | Marketplace operations (publish, install)
48-55        | Federation operations (cross-org share)
56-63        | Reserved for future use
```

**Canonical implementation:** Go constants and predefined sets live in `packages/permissions` ([ADR-0009](adr/ADR-0009-permission-bitmap.md)). Use `permissions.Has(bitmap, required)` for checks — do not invent ad-hoc bit values in services.

| Constant | Bit | Notes |
| --- | --- | --- |
| `TokenCreate` | 36 | Required for `CreateToken` / `ListTokens` gRPC (auth service) |
| `TokenRevoke` | 37 | Required to revoke another user's token |
| `ProxyChatCompletion` | 0, 16, 17 | Phase 2 proxy minimum: `MemoryRead \| SessionCreate \| SessionRead` |

**Enterprise SSO** (via Keycloak):

```text
1. User initiates login via dashboard
2. Dashboard redirects to Keycloak (OIDC flow)
3. Keycloak authenticates against corporate IDP (Okta, Azure AD, etc.)
4. Keycloak issues token
5. Auth Service exchanges Keycloak token for IBEX session token
6. Group → Role mapping applied (configured per organization)
7. Session token returned to dashboard
```

**Multi-Factor Authentication**:

- TOTP (Time-based One-Time Password)
- Required for privileged operations:
  - Creating admin-level tokens
  - Promoting directives to production
  - Revoking directives
  - Deleting organizations
  - Exporting all data
- 30-second time window, 1 retry allowed
- Backup codes generated at MFA enrollment (10 codes)

---

### 6. Background Workers (Python/Celery)

**Purpose**: Async processing that doesn't block agent requests

**Technology**: Python 3.11+, Celery, Redis as broker

**Worker Types**:

**1. Memory Extraction Worker**:

- Triggered after each LLM response
- Analyzes request/response pair
- Classification: is this learnable? (fine-tuned BERT, F1=0.89)
- Extraction: uses LLM to extract structured facts/preferences/patterns
- Deduplication: checks against existing memories
- Writes new memories to database
- Throughput: 100 extractions/sec per worker

**2. Conflict Detection Worker**:

- Triggered on new memory write if near-duplicate detected
- Semantic comparison: contradiction, overlap, supersession, specialization
- Resolution strategy determination
- Updates memory status and relationships
- Throughput: 50 conflict resolutions/sec per worker

**3. Behavioral Fingerprint Worker**:

- Runs every 10 inference calls per agent
- Computes statistical features from traces
- Stores fingerprint snapshot
- Throughput: 500 fingerprints/sec per worker

**4. Drift Detection Worker**:

- Runs after each fingerprint computation
- Compares current fingerprint to baseline
- Statistical tests: z-score for scalar features, cosine distance for embeddings
- Generates alerts if thresholds exceeded
- Throughput: 200 drift checks/sec per worker

**5. Notification Worker**:

- Processes notification queue
- Sends emails, webhooks, Slack messages
- Handles retries with exponential backoff
- Throughput: 1000 notifications/sec per worker

**6. Garbage Collection Worker**:

- Runs daily
- Cleans up expired sessions
- Archives old traces beyond retention period
- Removes soft-deleted memories after grace period
- Compacts ClickHouse partitions
- Runs during low-traffic hours (scheduled)

**Worker Scaling**:

- Auto-scale based on queue depth
- Min workers: 2 per type (redundancy)
- Max workers: 20 per type (cost control)
- Scale up: queue depth >100 items
- Scale down: queue depth <10 items for >5 minutes

**Failure Handling**:

- Max retries: 3 (exponential backoff: 1s, 10s, 100s)
- Dead letter queue for persistent failures
- Alerts on DLQ depth >10
- Manual inspection and replay of DLQ items

---

## 💾 Data Storage Architecture

### PostgreSQL (Primary Database)

**Purpose**: Source of truth for all operational data

**Version**: PostgreSQL 16

- Chosen for: ACID guarantees, Row-Level Security, JSONB, excellent performance

**Key Features Used**:

- **Row-Level Security**: Multi-tenant isolation at DB level
- **JSONB**: Flexible metadata without schema migration
- **pgvector**: Vector similarity search (1M+ vectors)
- **Full-text search**: tsvector/tsquery for tag and content search
- **Partitioning**: Large tables partitioned by month (traces, memory_versions)
- **Replication**: Streaming replication for read replicas

**Major Tables**:

```sql
-- Organizations
organizations (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  tier TEXT NOT NULL, -- free, pro, enterprise
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Users
users (
  id UUID PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL, -- owner, admin, member, viewer
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agents
agents (
  id UUID PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  name TEXT NOT NULL,
  directive_version_id UUID REFERENCES directive_versions(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Memories (detailed above in Memory Service section)
memories (...);

-- Directives
directives (
  id UUID PRIMARY KEY,
  org_id UUID REFERENCES organizations(id),
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

directive_versions (
  id UUID PRIMARY KEY,
  directive_id UUID REFERENCES directives(id),
  version_number INTEGER NOT NULL,
  parent_version_id UUID REFERENCES directive_versions(id),
  content TEXT NOT NULL,
  status TEXT NOT NULL, -- draft, review, active, deprecated, revoked
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sessions
sessions (
  id UUID PRIMARY KEY,
  agent_id UUID REFERENCES agents(id),
  directive_version_id UUID REFERENCES directive_versions(id),
  status TEXT NOT NULL, -- initializing, active, suspended, resuming, completed, failed
  started_at TIMESTAMPTZ DEFAULT NOW(),
  last_heartbeat_at TIMESTAMPTZ,
  checkpoint_sequence INTEGER DEFAULT 0
);

checkpoints (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES sessions(id),
  sequence_number INTEGER NOT NULL,
  state JSONB NOT NULL, -- serialized session state
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(session_id, sequence_number)
);

-- Tokens
tokens (
  id UUID PRIMARY KEY,
  type TEXT NOT NULL, -- pat, org_token, session_token, service_token
  hash TEXT UNIQUE NOT NULL, -- Argon2id hash
  org_id UUID REFERENCES organizations(id),
  user_id UUID REFERENCES users(id),
  permissions BIGINT NOT NULL, -- bitmap
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Row-Level Security Policies**:

```sql
-- Example for memories table
CREATE POLICY memories_isolation ON memories
  USING (org_id = current_setting('app.current_org_id')::UUID);

-- Applied to every table with org_id
-- Connection pool sets current_org_id from authenticated token
-- Even bugs in application code cannot leak cross-tenant data
```

**Scaling Strategy**:

- Primary for writes
- 2+ read replicas for read queries
- Connection pooling via PgBouncer (max 100 connections per instance)
- Automatic failover via Patroni
- Typical RTO: 30 seconds, RPO: 0 (synchronous replication)

---

### Redis (Cache and Coordination)

**Purpose**: Hot data cache, rate limiting, pub/sub, message queue

**Version**: Redis 7.x with Redis Stack (RedisJSON, RedisSearch, RedisBloom, RedisTimeSeries)

**Data Structures Used**:

**1. Strings**: Simple caches (auth tokens, directive content)

```text
Key: auth:token:{hash}
TTL: 30 seconds
Value: JSON {org_id, permissions, expiry}
```

**2. Sorted Sets**: Hot memories (ordered by composite score)

```text
Key: hot_memories:{agent_id}
Score: composite_score (relevance * recency * usefulness)
Member: memory_id
TTL: 1 hour
```

**3. Bloom Filter**: Fast token invalidation

```text
Key: valid_tokens_bloom
False positive rate: 0.01%
Size: Dynamically sized for 1M tokens
```

**4. Streams**: Message queue for async jobs

```text
Stream: memory_extraction_jobs
Consumer Group: memory_extractors
Max length: 10,000 (capped, overflow to dead letter)
```

**5. Hash**: Session state

```text
Key: session:{session_id}
Fields: {status, last_heartbeat, checkpoint_sequence}
TTL: 30 days after last_heartbeat
```

**Key Namespacing**:

All keys prefixed with org_id for isolation:

```text
{org_id}:auth:token:{hash}
{org_id}:hot_memories:{agent_id}
```

**Scaling**:

- Redis Cluster for horizontal scaling (6 nodes: 3 masters, 3 replicas)
- Consistent hashing for shard distribution
- Automatic failover (Sentinel or Cluster mode)
- Typical RTO: 5 seconds, RPO: 1 second (AOF with fsync every second)

**Eviction Policy**:

- `allkeys-lru` for cache keys
- `noeviction` for critical keys (tokens, rate limiters)
- Separate Redis instances for different use cases if needed

---

### ClickHouse (Analytics Store)

**Purpose**: Append-only event storage for traces, analytics, billing

**Version**: ClickHouse 23.x

**Why ClickHouse**:

- Columnar storage: 10-100x faster for analytical queries
- Compression: 10x better than row-based storage
- Scale: Handles billions of rows easily
- Fast writes: 1M+ rows/sec per server
- Fast aggregations: SUM/COUNT/AVG over billions in seconds

**Major Tables**:

```sql
-- Inference Traces
CREATE TABLE inference_traces (
  trace_id UUID,
  org_id UUID,
  agent_id UUID,
  session_id UUID,

  -- Request
  model String,
  prompt_tokens UInt32,
  prompt_hash String,

  -- Response
  completion_tokens UInt32,
  response_length UInt32,

  -- Performance
  total_latency_ms UInt32,
  provider_latency_ms UInt32,
  proxy_overhead_ms UInt16,

  -- Memory
  memories_retrieved UInt8,
  memory_ids Array(UUID),

  -- Status
  status Enum8('success' = 1, 'error' = 2, 'timeout' = 3),
  error_type Nullable(String),

  created_at DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (org_id, agent_id, created_at)
TTL created_at + INTERVAL 90 DAY;

-- Billing Events
CREATE TABLE billing_events (
  org_id UUID,
  event_type String, -- token_usage, memory_write, embedding_generated
  quantity UInt64,
  unit_cost_cents Decimal(10,2),
  total_cost_cents Decimal(10,2),
  metadata String, -- JSON
  created_at DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (org_id, created_at);

-- Behavioral Fingerprints
CREATE TABLE behavioral_fingerprints (
  agent_id UUID,
  computed_at DateTime64(3),
  avg_prompt_tokens Float32,
  avg_completion_tokens Float32,
  tool_call_rate Float32,
  error_rate Float32,
  -- ... more features
  embedding_centroid Array(Float32),
  PRIMARY KEY (agent_id, computed_at)
)
ENGINE = MergeTree()
ORDER BY (agent_id, computed_at);
```

**Partitioning Strategy**:

- By month: Old partitions easily dropped for GDPR/retention
- Queries with time filters scan only relevant partitions
- Automatic partition management

**Scaling**:

- Sharding: Distribute across multiple nodes by org_id hash
- Replication: 2x replication for durability
- Typical setup: 3 shards × 2 replicas = 6 nodes

---

### MinIO (Object Storage)

**Purpose**: S3-compatible storage for large blobs

**What's Stored**:

- Full session transcripts (conversation history)
- Large memory snapshots
- Directive version archives
- Exported data (GDPR requests)
- Backup archives

**Bucket Structure**:

```text
ibex-sessions/{org_id}/{session_id}/transcript.json
ibex-exports/{org_id}/{export_id}/data.tar.gz
ibex-backups/{date}/postgresql.dump
```

**Lifecycle Policies**:

- Sessions: Transition to cold storage after 90 days, delete after 2 years
- Exports: Delete after 30 days
- Backups: Retain daily for 30 days, weekly for 1 year

---

## 🔄 Data Flow Examples

### Example 1: Agent Makes LLM Call

```text
1. Agent SDK sends request to Proxy
   POST /v1/chat/completions
   Headers: Authorization: Bearer {token}, X-Agent-ID: {agent_id}
   Body: {messages: [...], model: "gpt-4-turbo"}

2. Proxy validates token
   - Bloom filter check (1ms): Is token potentially valid?
   - LRU cache check (0.1ms): Do we have cached permissions?
   - [Cache miss] Auth Service gRPC (5ms): Validate and return permissions
   - Cache result for 30s

3. Proxy checks rate limits
   - Redis Lua script (2ms): Atomic check + decrement
   - Three levels: agent, org, global
   - If exceeded: return 429 with Retry-After header

4. Proxy retrieves context (parallel, 40ms deadline)
   - Directive: Redis GET (1ms)
   - Hot memories: Redis ZRANGE (3ms)
   - Recent history: Session store query (10ms)
   Total: ~10ms (fastest completes)

5. Proxy calls Context Assembly (gRPC)
   - Request: {query, agent_id, session_id, model}
   - Context Assembly:
     - Budget calculation (1ms)
     - Cold memory search (25ms) - parallel with hot memories
     - Ranking (5ms)
     - Packing (3ms)
     - Formatting (2ms)
   - Response: {context_string}
   - Total: 36ms

6. Proxy injects context and forwards to LLM
   - Augment messages with context
   - Stream to OpenAI/Anthropic
   - Begin streaming response to agent

7. Proxy accumulates response while streaming
   - Agent receives tokens in real-time
   - Proxy buffers complete response
   - No added latency from accumulation

8. Proxy async operations (non-blocking)
   - Emit trace to ClickHouse (buffered write)
   - Trigger memory extraction job (Redis Stream publish)
   - Update session heartbeat (Redis SET)
   - Emit metrics (Prometheus counters)

9. Agent receives complete response
   Total latency: LLM time + ~50ms proxy overhead
```

### Example 2: Memory Extraction (Async)

```text
1. Proxy publishes job to Redis Stream
   XADD memory_extraction_jobs * trace_id {id} session_id {id}

2. Worker consumes from stream
   XREADGROUP GROUP extractors consumer1 STREAMS memory_extraction_jobs >

3. Worker fetches trace from ClickHouse
   SELECT request, response FROM inference_traces WHERE trace_id = {id}

4. Worker classifies learnability
   - Fine-tuned BERT model
   - Input: concatenated request + response
   - Output: learnable (0.87 confidence)
   - Decision: confidence > 0.7 → proceed

5. Worker extracts memories via LLM
   - Prompt: "Extract factual knowledge, preferences, behavioral patterns from..."
   - Response: [{category: "preference", content: "User prefers dark mode", confidence: "high"}]
   - Parse JSON response

6. Worker generates embeddings
   - Batch request to Embedding Service
   - POST /embed {texts: ["User prefers dark mode"]}
   - Response: {embeddings: [[0.1, 0.2, ...]]}

7. Worker checks for duplicates
   - Content hash: SHA-256 of normalized content
   - Query: SELECT id FROM memories WHERE content_hash = {hash}
   - If exists: skip, increment retrieval_count
   - If not: proceed

8. Worker checks for near-duplicates
   - Vector similarity search
   - SELECT id, content, embedding FROM memories
     WHERE agent_id = {id}
     ORDER BY embedding <=> {new_embedding}
     LIMIT 5
   - Cosine similarity > 0.85 → near-duplicate

9. Worker triggers conflict detection
   - If near-duplicate found: publish to conflict_detection_jobs stream
   - Otherwise: proceed to write

10. Worker writes memory
    - INSERT INTO memories (content, embedding, category, confidence, ...)
    - Write to Redis hot cache
    - XACK the stream message (job complete)
```

### Example 3: Drift Detection

```text
1. After 10 inference calls, trigger fingerprint computation
   - Worker: Fetch last 100 traces for this agent
   - Extract features: avg_tokens, tool_call_rate, error_rate, etc.
   - Compute embedding centroid of responses
   - Write fingerprint to ClickHouse

2. Compare to baseline
   - Fetch baseline fingerprint (computed at agent creation or last reset)
   - For scalar features: compute z-score
   - For embedding: compute cosine distance
   - For tool distribution: compute KL divergence

3. Detect drift
   - If |z-score| > 2.0 for any feature: flag
   - If embedding distance > 0.3: flag
   - If KL divergence > 0.5: flag
   - Aggregate flags into severity: low, medium, high

4. Generate alert
   - If severity = high:
     - Pause agent (set status to SUSPENDED)
     - Send notification to owner
     - Create incident record
   - If severity = medium:
     - Send notification with details
     - Suggest directive review
   - If severity = low:
     - Log event to dashboard
     - No immediate action

5. Owner reviews alert
   - Dashboard shows:
     - Which features drifted
     - Current vs baseline values
     - Recent traces that contributed to drift
   - Owner decides:
     - False alarm: reset baseline to current
     - Legitimate drift: update directive
     - Bug: investigate and fix
```

---

## 🔐 Security Architecture

### Multi-Tenant Isolation (Defense in Depth)

**Layer 1: Database (Row-Level Security)**

```sql
-- Every table with org_id
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;

CREATE POLICY org_isolation ON memories
  USING (org_id = current_setting('app.current_org_id')::UUID);

-- Connection pool sets org_id from authenticated token
SET LOCAL app.current_org_id = '{org_id}';
```

**Protection**: Even application bugs cannot leak cross-tenant data

**Layer 2: Application (Permission Checks)**

```python
@require_permission(Permission.MEMORY_READ)
async def get_memory(memory_id: UUID, token: TokenData):
    # Permission bitmap already checked by decorator
    # org_id from token enforced in query
    memory = await db.fetch_one(
        "SELECT * FROM memories WHERE id = $1 AND org_id = $2",
        memory_id, token.org_id
    )
```

**Protection**: Explicit permission checks before every operation

**Layer 3: Cache (Namespace Isolation)**

```python
def cache_key(org_id: UUID, entity: str, id: str) -> str:
    return f"{org_id}:{entity}:{id}"

# Example
key = cache_key(token.org_id, "memory", memory_id)
redis.get(key)
```

**Protection**: Cache keys namespaced, cross-tenant reads impossible

**Layer 4: Search (Filter Enforcement)**

```python
def search_memories(query: str, token: TokenData):
    results = vector_db.search(
        query_vector,
        filter={"org_id": str(token.org_id)},  # Always applied
        limit=20
    )
```

**Protection**: Vector search always filtered by org_id

**Layer 5: Audit (Every Access Logged)**

```python
audit_log.record(
    action="memory_read",
    org_id=token.org_id,
    user_id=token.user_id,
    resource_id=memory_id,
    timestamp=now(),
    ip=request.client.host
)
```

**Protection**: Anomaly detection, forensics, compliance

---

### Encryption

**At Rest**:

- Database: PostgreSQL TDE (Transparent Data Encryption) or disk encryption
- Object Storage: MinIO encryption (AES-256)
- Backups: Encrypted with AWS KMS or HashiCorp Vault

**In Transit**:

- All external connections: TLS 1.3
- Inter-service: mTLS optional (performance vs security tradeoff)
- LLM provider connections: HTTPS only

**Secrets Management**:

- Development: `.env` files (not committed)
- Staging/Production: HashiCorp Vault or AWS Secrets Manager
- Kubernetes: Sealed Secrets or External Secrets Operator
- Rotation: Automated rotation for service tokens (24h), manual for others

---

### Authentication & Authorization

**Authentication Flow**:

```text
1. User/Agent presents token (PAT, Org Token, or Session Token)
2. Proxy validates:
   - Bloom filter: Is it potentially valid?
   - Cache: Do we have recent validation?
   - Auth Service: Validate and retrieve permissions
3. Extract claims: org_id, user_id, permissions bitmap
4. Set context for downstream services
5. Proceed with request
```

**Authorization Enforcement**:

```text
Every protected endpoint:
1. Check permission bitmap: Does token have required permission?
2. Check resource ownership: Does token's org_id match resource's org_id?
3. Check scope: Is token allowed to access this specific resource?
4. Log access for audit
5. Proceed or return 403 Forbidden
```

---

## 📊 Monitoring & Observability

### Metrics (Prometheus)

**Critical Metrics**:

```text
# Proxy
ibex_proxy_request_duration_seconds{quantile, operation, status}
ibex_proxy_active_connections{instance}
ibex_proxy_requests_total{operation, status}

# Context Assembly
ibex_context_assembly_duration_seconds{quantile}
ibex_context_budget_utilization_ratio

# Memory Service
ibex_memory_write_duration_seconds{quantile}
ibex_memory_search_duration_seconds{quantile}
ibex_memory_deduplication_rate

# System
ibex_cpu_usage_percent{service, instance}
ibex_memory_usage_bytes{service, instance}
ibex_db_connection_pool_active{service}
ibex_db_query_duration_seconds{query_type, quantile}

# Business
ibex_active_agents_total
ibex_daily_llm_requests
ibex_memory_operations_total{operation}
```

**Alerting Rules**:

```yaml
- alert: HighProxyLatency
  expr: ibex_proxy_request_duration_seconds{quantile="0.99"} > 0.1
  for: 5m
  severity: warning

- alert: MemoryServiceDown
  expr: up{job="memory-service"} == 0
  for: 1m
  severity: critical

- alert: HighErrorRate
  expr: rate(ibex_proxy_requests_total{status="error"}[5m]) > 0.05
  for: 5m
  severity: critical
```

### Logging (Structured JSON)

**Log Format**:

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "service": "proxy",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "org_id": "123e4567-e89b-12d3-a456-426614174000",
  "message": "Memory injection completed",
  "duration_ms": 42,
  "memories_count": 5,
  "model": "gpt-4-turbo"
}
```

**Log Levels**:

- ERROR: Failures requiring immediate attention
- WARN: Degraded behavior, fallbacks activated
- INFO: Normal operations, audit trail
- DEBUG: Detailed diagnostic (not in production)

**Log Aggregation**: Loki or ELK stack, retention: 30 days

### Tracing (OpenTelemetry)

**Instrumentation**:

```text
Agent Request (root span)
├─ Proxy: Token Validation (span)
├─ Proxy: Rate Limit Check (span)
├─ Proxy: Context Retrieval (span)
│  ├─ Redis: Get Directive (span)
│  ├─ Redis: Get Hot Memories (span)
│  └─ Session Store: Get History (span)
├─ Context Assembly (span)
│  ├─ Vector Search (span)
│  ├─ Ranking (span)
│  └─ Packing (span)
├─ LLM Provider Call (span)
└─ Proxy: Response Streaming (span)
```

**Trace Sampling**:

- 100% of errors
- 100% of requests >500ms
- 1% of normal requests (cost control)

**Trace Storage**: Jaeger or Tempo, retention: 7 days

---

## 🚀 Deployment Architecture

### Kubernetes-Based Deployment

**Namespace Structure**:

```text
ibex-system:       Core platform services
  - proxy
  - auth-service
  - memory-service
  - context-assembly
  - embedding-service
  - api-server
  - workers

ibex-data:         Stateful services
  - postgresql
  - redis
  - clickhouse
  - minio

ibex-monitoring:   Observability stack
  - prometheus
  - grafana
  - loki
  - jaeger
```

**Service Deployment**:

```yaml
# Example: Proxy Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: proxy
  namespace: ibex-system
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: proxy
  template:
    spec:
      containers:
      - name: proxy
        image: ibex/proxy:v1.0.0
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

**Auto-Scaling**:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: proxy-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: proxy
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Infrastructure as Code

**Terraform Structure**:

```text
terraform/
  ├── environments/
  │   ├── dev/
  │   ├── staging/
  │   └── prod/
  ├── modules/
  │   ├── k8s-cluster/
  │   ├── database/
  │   ├── redis/
  │   ├── monitoring/
  │   └── networking/
  └── shared/
      └── variables.tf
```

### CI/CD Pipeline

**On Push to Main**:

```text
1. Lint & Format Check
2. Type Checking (mypy, tsc, golangci-lint)
3. Unit Tests
4. Build Docker Images
5. Security Scan (Trivy)
6. Push to Registry
7. Deploy to Staging
8. Integration Tests (Staging)
9. Manual Approval Gate
10. Deploy to Production (Blue-Green)
11. Smoke Tests (Production)
12. Automated Rollback if Smoke Tests Fail
```

---

## Related documentation

- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) — PostgreSQL, Redis, and ClickHouse schema reference
- [DEPLOYMENT.md](DEPLOYMENT.md) — CI/CD, environments, and rollout
- [MONITORING.md](MONITORING.md) — observability, dashboards, and alerts
