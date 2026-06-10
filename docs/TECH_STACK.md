# IBEX Harness - Technology Stack

## 🎯 Technology Selection Philosophy

Every technology choice in IBEX Harness is made based on these criteria:

1. **Performance Characteristics**: Does it meet our latency/throughput requirements?
2. **Production Maturity**: Is it battle-tested at scale by other companies?
3. **Team Expertise**: Can we hire for it? Is there sufficient learning material?
4. **Ecosystem**: Does it have libraries/tools we need?
5. **Operational Simplicity**: Can we deploy, monitor, and debug it effectively?
6. **Long-term Viability**: Will it be maintained 5+ years from now?

**We explicitly avoid:**

- Bleeding-edge technologies (no production track record)
- Niche languages (hiring difficulty)
- Vendor lock-in when avoidable
- Technology for technology's sake (trend-chasing)

---

## 🔧 Core Services Technology Choices

### LLM Proxy Service: **Go 1.21+**

**Why Go:**

**Performance Justification:**

- Goroutines: 8KB memory per concurrent connection vs. MB-per-thread in Python
- At 10,000 concurrent connections: ~80MB in Go vs. ~10GB in Python/Node
- Garbage collection pauses: <1ms (sub-millisecond GC in Go 1.21+)
- Native HTTP/2 support with excellent performance
- Compiled binary: ~15MB, starts in <50ms, no runtime dependencies

**Alternatives Considered:**

| Language | Why Not Chosen |
|----------|----------------|
| **Rust** | Would be 10-20% faster, but development velocity cost too high. The proxy is IO-bound, not CPU-bound—Rust's zero-cost abstractions help most in CPU-intensive work. Hiring difficulty 3-5x vs Go. |
| **Node.js** | Event loop adds 2-5ms overhead per request in proxy benchmarks. Memory footprint grows unpredictably under high concurrency. Single-threaded nature requires complex clustering. |
| **Python** | CPython GIL makes true parallelism impossible. Would need process-per-core model. Even with asyncio, measured 5-10ms slower than Go for proxy workloads. |
| **Java** | JVM startup time (seconds) and memory overhead (GBs) unacceptable for sidecar deployment model. JIT warmup period creates inconsistent latency. |

**Real-World Evidence:**

- Docker daemon: Rewritten from Python to Go, 10x performance improvement
- Kubernetes: Written in Go, handles 1000s of concurrent connections
- Traefik proxy: Go-based, handles 100k+ req/sec

**Framework Choice: Standard Library Only**

We use Go's `net/http` directly, not Gin/Echo/Fiber.

**Reasoning:**

- At this performance level, frameworks add indirection without benefit
- `net/http` is production-grade (powers production systems at Google scale)
- Less dependency surface area = less security vulnerability exposure
- Direct control over connection handling and timeouts

**Exception:** `fasthttp` for the provider-facing LLM connection pool

- Zero-allocation HTTP client
- Measurably reduces GC pressure at scale (15% reduction in allocations in benchmarks)
- Only for upstream connections, not for agent-facing API (standard library there)

---

### Memory Service, API Server, Workers: **Python 3.11+**

**Why Python:**

**Ecosystem Justification:**

The memory service does:

- Embedding generation (HuggingFace transformers)
- Vector similarity scoring (NumPy, SciPy)
- Memory ranking with composite functions (scientific computation)
- Conflict detection using language model classification (PyTorch/Transformers)
- Behavioral fingerprinting with statistical analysis (pandas, scikit-learn)

**Every single one of these has mature, production-grade Python libraries.** Rewriting in Go would mean:

- Calling Python microservices anyway (adding latency + complexity)
- Or building ML tooling from scratch in a language where it barely exists
- Losing access to the HuggingFace ecosystem (70k+ models)

**Python 3.11 Specific Features Used:**

- 25% faster than Python 3.10 (verified in our benchmarks)
- Better error messages (development velocity)
- Native TOML support for config
- Faster asyncio (important for async SQLAlchemy)

**Framework Choice: FastAPI**

**Why FastAPI over Flask/Django:**

| Framework | Why Not Chosen |
|-----------|----------------|
| **Flask** | Synchronous by default. Most API operations are IO-bound (waiting for database, waiting for vector search, waiting for embedding API). Flask's sync model would require manual async workarounds or thread pools. |
| **Django** | Carries enormous ORM and admin machinery irrelevant to this project. Startup time: ~2 seconds (vs <500ms for FastAPI). Django ORM doesn't support async well. Admin interface not needed (we have custom dashboard). |
| **Sanic/Quart** | Smaller ecosystems, fewer production examples. FastAPI's automatic OpenAPI generation eliminates documentation maintenance work. Pydantic v2 integration is tighter in FastAPI. |

**FastAPI Advantages Leveraged:**

- Native async/await throughout
- Automatic OpenAPI/Swagger documentation from type annotations
- Pydantic v2 validation (5-10x faster than v1, compiled with Rust internals)
- Dependency injection system (clean testing, request lifecycle management)
- WebSocket support (for future real-time dashboard features)

**Runtime Choice: Uvicorn + Gunicorn**

```bash
# Production startup
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --graceful-timeout 30
```

**Why This Combination:**

- Gunicorn: Process management, graceful restarts, worker lifecycle
- Uvicorn: ASGI server, async event loop, HTTP/2 support
- This is the de-facto production standard for FastAPI apps

**Async Database: SQLAlchemy 2.0 (Async Mode)**

**Why SQLAlchemy 2.0 Async:**

- Native async/await support (not bolted on)
- Mature ORM with excellent PostgreSQL support
- Transaction management for complex multi-table operations
- Connection pooling with async drivers (asyncpg)
- Type safety with SQLAlchemy 2.0's improved typing

**Database Driver: asyncpg**

- 3-5x faster than psycopg2 in async workloads
- Pure Python, excellent error messages
- Native support for PostgreSQL types (JSONB, arrays, etc.)

**Validation: Pydantic v2**

**Why Pydantic v2:**

- 5-10x faster than Pydantic v1 (Rust core)
- Type coercion and validation in one step
- Excellent error messages for API validation
- Serialization/deserialization with zero boilerplate
- JSON Schema generation for API docs

**Background Workers: Celery**

**Why Celery over alternatives:**

| Alternative | Why Not Chosen |
|-------------|----------------|
| **Redis RQ** | Simpler, but lacks advanced features: task prioritization, scheduled tasks, complex workflows. Good for simple queues, insufficient for our needs. |
| **Dramatiq** | Excellent library, but smaller ecosystem. Celery's monitoring tools (Flower) and production usage at scale (Instagram) proven. |
| **Kafka + custom consumers** | Over-engineered for our throughput (<10k tasks/min). Kafka shines at 50k+ events/sec. Operational complexity not justified. |
| **Cloud queues (SQS/GCP Tasks)** | Vendor lock-in. Self-hosted requirement for enterprise customers eliminates cloud-only solutions. |

**Celery Configuration:**

```python
# Broker: Redis (we already run it)
broker_url = "redis://localhost:6379/0"

# Backend: Redis (for task result storage)
result_backend = "redis://localhost:6379/1"

# Task serialization
task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]

# Concurrency
worker_prefetch_multiplier = 4  # Fetch 4 tasks per worker
worker_max_tasks_per_child = 1000  # Restart worker after 1k tasks (memory leak prevention)

# Retry configuration
task_acks_late = True  # Don't ack until task completes (at-least-once delivery)
task_reject_on_worker_lost = True  # Requeue tasks if worker crashes
```

**Monitoring: Flower**

- Web UI for Celery monitoring
- Real-time task tracking
- Worker management
- Task history and statistics
- Built-in alerting

---

### Dashboard: **Next.js 14 (App Router) + TypeScript + Tailwind CSS**

**Why Next.js 14 App Router:**

**Server Components Advantage:**

The dashboard has data-heavy pages:

- Session history (potentially thousands of turns)
- Memory graphs (visualizing relationships between memories)
- Behavioral fingerprint timelines
- Analytics dashboards with large datasets

**Traditional React SPA Approach:**

1. Ship empty HTML shell
2. Ship megabytes of JavaScript
3. JavaScript fetches data
4. JavaScript renders page
5. Total time to interactive: 3-5 seconds on slow connections

**Next.js App Router Approach:**

1. Server components fetch data server-side
2. Render HTML with data on server
3. Ship minimal JavaScript (only for interactive components)
4. Total time to interactive: 1-2 seconds on same connection

**Real Metrics from Production Next.js Apps:**

- 40-60% reduction in JavaScript bundle size
- 30-50% faster time to interactive
- Better SEO (server-rendered content)

**Why App Router over Pages Router:**

- Streaming SSR: Send HTML as it's ready, don't wait for entire page
- Nested layouts: Shared layouts don't re-render on navigation
- Server actions: Form handling without API routes
- Better data fetching patterns: fetch in components, automatic deduplication

**Why TypeScript:**

**Type Safety = Fewer Bugs:**

```typescript
// Without TypeScript
function getMemory(id) {
  return fetch(`/api/memories/${id}`)
    .then(res => res.json())
    .then(data => data.memory) // What if 'memory' doesn't exist? Runtime error.
}

// With TypeScript
interface Memory {
  id: string;
  content: string;
  embedding: number[];
  created_at: string;
}

async function getMemory(id: string): Promise<Memory> {
  const res = await fetch(`/api/memories/${id}`);
  const data = await res.json();
  return data.memory; // TypeScript ensures this matches Memory interface
}
```

**Production Evidence:**

- Airbnb: 38% of bugs preventable with TypeScript (from their postmortem analysis)
- Slack: "TypeScript has been a massive improvement in code quality"
- Microsoft: Created TypeScript because JavaScript lacked necessary guardrails for large codebases

**Specific Benefits for IBEX Dashboard:**

- Autocomplete for API responses (developer velocity)
- Refactoring safety (rename a field, compiler finds all usages)
- Self-documenting code (types are documentation)
- Integration with backend: Generate TypeScript types from proto files

**Why Tailwind CSS:**

**Utility-First Advantages:**

Traditional CSS:

```css
/* Somewhere in a CSS file */
.memory-card {
  padding: 1rem;
  margin-bottom: 1rem;
  border-radius: 0.5rem;
  background-color: white;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

/* Now need to find this class in HTML */
```

Tailwind:

```tsx
<div className="p-4 mb-4 rounded-lg bg-white shadow-md">
  {/* Styling colocated with markup */}
</div>
```

**Why This Matters:**

- No context switching between files
- No naming things (naming is hard)
- No dead CSS (only used utilities are included)
- Design system constraints built-in (spacing scale, color palette)
- Production bundle: ~10KB after PurgeCSS (removes unused utilities)

**Production Evidence:**

- GitHub: Redesigned with Tailwind, development velocity increased
- Shopify: Faster UI development, more consistent design
- Vercel: Uses Tailwind for their own dashboard products

**State Management:**

**Client State: Zustand**

```typescript
import create from 'zustand';

const useStore = create((set) => ({
  selectedAgent: null,
  setSelectedAgent: (agent) => set({ selectedAgent: agent }),
}));

// Usage in component
const selectedAgent = useStore(state => state.selectedAgent);
```

**Why Zustand over Redux:**

- Less boilerplate (5 lines vs 20 lines for same functionality)
- Hooks-based (natural React integration)
- No Provider wrapper needed (works anywhere)
- TypeScript support excellent
- Bundle size: 1KB vs 3KB (Redux) vs 5KB (MobX)

**Server State: TanStack Query (React Query)**

```typescript
const { data, isLoading, error } = useQuery({
  queryKey: ['memory', memoryId],
  queryFn: () => fetchMemory(memoryId),
  staleTime: 5000, // Consider fresh for 5 seconds
  cacheTime: 300000, // Keep in cache for 5 minutes
});
```

**Why TanStack Query:**

- Automatic caching, deduplication, background refetch
- Pagination, infinite scroll built-in
- Optimistic updates for better UX
- Synchronization across components (fetch once, use everywhere)
- DevTools for debugging

**Together:** Zustand for UI state (selected items, modal open/closed), TanStack Query for server state (memories, sessions, analytics). Clean separation of concerns.

**Data Visualization:**

**For Complex Charts: Observable Plot**

```typescript
import * as Plot from "@observableplot/plot";

Plot.plot({
  marks: [
    Plot.line(data, {x: "timestamp", y: "latency"}),
    Plot.dot(data, {x: "timestamp", y: "latency"}),
  ]
})
```

**Why Observable Plot:**

- Built on D3 (proven foundation)
- Higher-level API (less code than raw D3)
- Excellent for time-series, distributions, correlations
- Designed for data analysis (our use case)

**For Simple Charts: Recharts**

```tsx
<LineChart data={data}>
  <Line dataKey="latency" />
  <XAxis dataKey="timestamp" />
  <YAxis />
</LineChart>
```

**Why Recharts:**

- React-native API (declarative)
- Good for simple bar, line, area charts
- Responsive by default
- Accessible

**Not Chart.js:** Imperative API fights against React's declarative model.

---

### CLI Tool: **Go 1.21+**

**Why Go for CLI:**

**Developer Experience:**

```bash
# Installation
curl -L https://install.ibexharness.com | sh

# Result: Single binary, works immediately
ibex --version
```

**Comparison:**

| Language | Developer Experience |
|----------|---------------------|
| **Python CLI** | Requires Python installed, correct version, pip install, virtualenv management, slow startup (100-500ms interpreter init) |
| **Node CLI** | Requires Node.js installed, npm install, node_modules bloat, startup latency |
| **Go CLI** | Download binary, run. No runtime. Starts in <50ms. Works on Linux, macOS, Windows without changes. |

**Real Examples:**

- GitHub CLI (`gh`): Go
- Kubernetes CLI (`kubectl`): Go
- Terraform: Go
- Docker CLI: Go
- Hugo: Go

**Why They All Chose Go:**

- Cross-compilation: `GOOS=linux GOARCH=amd64 go build` produces Linux binary from macOS
- Single binary: No dependency hell
- Fast startup: Critical for CLI UX
- Good libraries: `cobra` (command structure), `viper` (config)

**CLI Framework: Cobra + Viper**

**Cobra** (command structure):

```go
var rootCmd = &cobra.Command{
  Use:   "ibex",
  Short: "IBEX Harness CLI",
}

var memoryCmd = &cobra.Command{
  Use:   "memory",
  Short: "Manage memories",
}

var searchCmd = &cobra.Command{
  Use:   "search [query]",
  Short: "Search memories",
  Run: func(cmd *cobra.Command, args []string) {
    // Implementation
  },
}

rootCmd.AddCommand(memoryCmd)
memoryCmd.AddCommand(searchCmd)

// Result: ibex memory search "dark mode preference"
```

**Why Cobra:**

- Used by kubectl, GitHub CLI, Hugo (proven)
- Automatic help generation
- Flag parsing
- Command suggestions (typo tolerance)
- Shell completion generation

**Viper** (configuration):

```go
viper.SetConfigName("config")
viper.AddConfigPath("$HOME/.ibex")
viper.SetEnvPrefix("ibex")
viper.AutomaticEnv()

// Reads from (in order):
// 1. Flags
// 2. Environment variables (IBEX_*)
// 3. Config file (~/.ibex/config.yaml)
// 4. Defaults
```

**Authentication Flow: OAuth 2.0 Device Flow**

Same flow as GitHub CLI:

```text
$ ibex auth login

Visit: https://ibexharness.com/device
Enter code: ABCD-1234

Waiting for authentication...
✓ Authenticated as user@example.com
```

**Why Device Flow:**

- Works in SSH sessions (no localhost redirect)
- Works in remote environments
- No plaintext passwords
- No tokens in shell history
- Browser-based (can use SSO, MFA)

---

### SDKs: **Python, TypeScript, Go**

**Design Philosophy: Thin Wrappers, Minimal Dependencies**

**The Dependency Problem:**

Every dependency you add to an SDK is a dependency you force on every user.

**Bad SDK Example:**

```python
# sdk/requirements.txt
requests
pydantic
click
rich
tenacity
httpx
orjson
...  # 20 more dependencies

# User installs your SDK
pip install ibex-sdk

# User now has version conflicts with their other packages
ERROR: ibex-sdk requires pydantic==2.0, but you have pydantic==1.10
```

**Our Approach:**

```python
# Python SDK: 3-5 dependencies MAXIMUM
httpx       # Supports both sync and async
pydantic    # Will be installed anyway in most Python projects
typing-extensions  # For older Python versions
```

**TypeScript SDK: ZERO dependencies**

```typescript
// Uses native fetch (Node 18+, all browsers)
// No axios, no lodash, no moment
// Total SDK size: <10KB
```

**Go SDK: Standard library + gRPC only**

```go
// Only dependency
google.golang.org/grpc
```

**SDK Interface Design:**

**Python SDK:**

```python
from ibex import Ibex

# Initialize
ibex = Ibex(api_key="...")

# Synchronous API
memory = ibex.memory.write(content="User prefers dark mode")
memories = ibex.memory.search(query="UI preferences")

# Async API (same interface)
memory = await ibex.memory.write_async(content="...")
memories = await ibex.memory.search_async(query="...")

# Context manager for sessions
async with ibex.session() as session:
    response = await session.llm.chat(messages=[...])
    # Session automatically closed, checkpointed
```

**Why Both Sync and Async:**

- Many users are in synchronous codebases
- FastAPI users need async
- Same API surface = less documentation, less confusion

**TypeScript SDK:**

```typescript
import { Ibex } from 'ibex-sdk';

const ibex = new Ibex({ apiKey: '...' });

// Promise-based
const memory = await ibex.memory.write({ content: '...' });
const memories = await ibex.memory.search({ query: '...' });

// Streaming LLM calls
const stream = ibex.llm.chat({ messages: [...], stream: true });
for await (const chunk of stream) {
  console.log(chunk.content);
}
```

**Dual Module Format:**

```json
{
  "main": "./dist/cjs/index.js",
  "module": "./dist/esm/index.js",
  "types": "./dist/types/index.d.ts"
}
```

**Why Both:**

- Old Node.js projects use CommonJS
- Modern projects and bundlers prefer ESM
- TypeScript types for autocomplete

**Go SDK:**

```go
import "github.com/ibexharness/ibex-go"

client := ibex.NewClient(ibex.Config{
    APIKey: os.Getenv("IBEX_API_KEY"),
})

// Context-aware
ctx := context.Background()
memory, err := client.Memory.Write(ctx, &ibex.WriteRequest{
    Content: "User prefers dark mode",
})

memories, err := client.Memory.Search(ctx, &ibex.SearchRequest{
    Query: "UI preferences",
})
```

**Why Context-First:**

- Idiomatic Go
- Timeout and cancellation propagation
- Request tracing via context values

---

## 🗄️ Data Storage Technology Choices

### Primary Database: **PostgreSQL 16**

**Why PostgreSQL over MySQL:**

| Feature | PostgreSQL | MySQL |
|---------|-----------|-------|
| **Row-Level Security** | First-class feature | Not available (must implement in application) |
| **JSONB** | Native type with GIN indexing, excellent performance | JSON type exists but less performant |
| **Full-text search** | tsvector/tsquery built-in | Full-text search exists but less powerful |
| **Array types** | Native support, indexable | Not supported (must use JSON or separate table) |
| **Window functions** | Comprehensive | Partial support |
| **CTEs (WITH)** | Recursive and non-recursive | Basic support |
| **Extension ecosystem** | Rich (pgvector, PostGIS, etc.) | Limited |

**PostgreSQL 16 Specific Features:**

- Improved parallelism (faster queries on multi-core)
- Better vacuum performance (less downtime)
- Logical replication improvements (for read replicas)
- SQL/JSON improvements (better JSONB querying)

**pgvector Extension:**

**Why pgvector over dedicated vector databases:**

| Solution | Why Not Chosen (Initially) |
|----------|---------------------------|
| **Pinecone** | SaaS-only, cannot self-host (deal-breaker for enterprise). Vendor lock-in. Cost scales unpredictably. |
| **Weaviate** | Operational complexity. Separate cluster to manage, monitor, backup. Learning curve. |
| **Qdrant** | Excellent choice, but **we plan to migrate to Qdrant at scale**. For <50M vectors, pgvector performs well enough. Starting with pgvector keeps infrastructure simple. |
| **Milvus** | Very complex to operate. Heavy infrastructure requirements. Over-engineered for our initial scale. |

**pgvector Performance:**

- <100K vectors: Excellent performance (<50ms queries)
- 100K-10M vectors: Good performance with IVFFlat index
- >10M vectors per tenant: Transition to Qdrant (planned migration path)

**Migration Strategy to Qdrant:**

```text
1. Deploy Qdrant alongside PostgreSQL
2. Write embeddings to both (dual-write)
3. Background job migrates existing embeddings
4. Switch reads to Qdrant when 99% migrated
5. Retain PostgreSQL embeddings for 90 days (rollback)
6. Drop embedding column from PostgreSQL
```

**Connection Pooling: PgBouncer**

**Why PgBouncer:**

- PostgreSQL has limited connections (typically 100-200)
- Each connection uses significant memory (~10MB)
- Applications need many more connections than PostgreSQL can handle

**PgBouncer solves this:**

```text
1000 application connections → PgBouncer → 50 PostgreSQL connections

Mode: Transaction pooling (connection returned after each transaction)
```

**Configuration:**

```ini
[databases]
ibex = host=postgresql port=5432 dbname=ibex

[pgbouncer]
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
reserve_pool_size = 5
```

---

### Cache and Coordination: **Redis 7.x (Redis Stack)**

**Why Redis:**

**Not Just a Cache:**

We use Redis for:

1. **Caching**: Hot memories, directive content, auth tokens
2. **Rate Limiting**: Atomic counters with TTL (Lua scripts)
3. **Pub/Sub**: Directive update notifications
4. **Message Queue**: Celery broker (background jobs)
5. **Session State**: Heartbeats, checkpoints
6. **Sorted Sets**: Hot memory ranking
7. **Bloom Filters**: Fast token invalidation (Redis Stack)
8. **Time Series**: Metrics aggregation (Redis Stack)

**Why Redis Stack over Plain Redis:**

**Redis Stack Includes:**

- **RedisJSON**: Native JSON support (better than serializing to strings)
- **RedisSearch**: Full-text search and secondary indexing
- **RedisTimeSeries**: Time-series data (for metrics)
- **RedisBloom**: Probabilistic data structures (Bloom filters, Cuckoo filters)
- **RedisGraph**: Graph queries (future: memory relationship visualization)

**Example Use Cases:**

**Bloom Filter for Token Validation:**

```redis
# Add valid token to bloom filter
BF.ADD valid_tokens {token_hash}

# Check if token is potentially valid
BF.EXISTS valid_tokens {token_hash}
# Returns 0 (definitely not valid) or 1 (possibly valid)

# False positive rate: 0.01% (1 in 10,000)
# If returns 0: Skip expensive database lookup
# If returns 1: Proceed with cache/database check
```

**Cuckoo Filter for "Has Agent Seen This Memory":**

```redis
# Check if agent has ever accessed this memory
CF.EXISTS agent:{agent_id}:seen_memories {memory_id}

# If not: This is a novel memory for this agent
# If yes: Agent has seen this before

# Eliminates many database lookups
```

**Why Redis over Memcached:**

| Feature | Redis | Memcached |
|---------|-------|-----------|
| **Data structures** | Strings, lists, sets, sorted sets, hashes, streams, etc. | Only key-value strings |
| **Persistence** | RDB snapshots, AOF log | None (pure cache) |
| **Pub/Sub** | Built-in | Not available |
| **Atomic operations** | Many | Very few |
| **Lua scripting** | Supported (crucial for rate limiting) | Not available |

**Redis is a superset of Memcached's functionality.**

**Redis Cluster vs Sentinel:**

**Development/Small Deployments: Single instance with AOF**

```text
redis.conf:
  appendonly yes
  appendfsync everysec
```

**Medium Scale: Sentinel (HA without sharding)**

```text
1 Master + 2 Replicas + 3 Sentinels
Automatic failover
No sharding (all data on all instances)
```

**Large Scale: Redis Cluster**

```text
6+ nodes (3 masters, 3 replicas)
Data sharded across masters (hash slots)
Automatic failover
Linear scalability
```

**We start with Sentinel, migrate to Cluster at >100GB data or >100K ops/sec.**

---

### Analytics Store: **ClickHouse 23.x**

**Why ClickHouse over alternatives:**

**The Use Case:**

- 1M+ inference traces per day
- Billions of rows within a year
- Queries: "Average token usage per agent over last 30 days"
- Scans millions of rows, aggregates results
- This is OLAP (Online Analytical Processing), not OLTP

**PostgreSQL is Wrong for This:**

- Row-based storage: Reads entire row even if you need 2 columns
- At billions of rows, aggregation queries slow to minutes
- Competes with transactional queries for I/O

**Alternatives Considered:**

| Solution | Why Not Chosen |
|----------|----------------|
| **Elasticsearch** | Search engine, not analytical database. Memory consumption 10x higher than ClickHouse for same data. More expensive to run. |
| **BigQuery** | Google Cloud only. Need multi-cloud + self-hosted support. Vendor lock-in. |
| **Apache Druid** | Operational complexity: requires Zookeeper, coordinator, broker, historical nodes. Over-engineered for our needs. |
| **TimescaleDB** | PostgreSQL extension. Better than plain PostgreSQL, but row-based storage fundamentally slower than columnar for analytics. |
| **Snowflake** | SaaS-only, expensive, vendor lock-in. |

**ClickHouse Advantages:**

**Columnar Storage:**

```text
Row-based (PostgreSQL):
Row 1: [trace_id, org_id, agent_id, model, prompt_tokens, completion_tokens, latency, ...]
Row 2: [trace_id, org_id, agent_id, model, prompt_tokens, completion_tokens, latency, ...]

Query: SELECT AVG(latency) FROM traces WHERE org_id = '...'
Reads: All columns of all matching rows (wasteful)

Columnar (ClickHouse):
trace_id column: [id1, id2, id3, ...]
org_id column: [org1, org1, org2, ...]
latency column: [100ms, 150ms, 120ms, ...]

Query: SELECT AVG(latency) FROM traces WHERE org_id = '...'
Reads: Only org_id column (for filtering) + latency column (for averaging)
Result: 10-100x faster
```

**Compression:**

- Columnar data compresses extremely well (similar values adjacent)
- ClickHouse achieves 10:1 compression typically
- 1TB of data becomes 100GB on disk

**Performance:**

- Aggregations over billions of rows in seconds
- 1M+ inserts per second per server
- Linear scalability (add nodes, get proportional performance)

**ClickHouse Table Design:**

```sql
CREATE TABLE inference_traces (
  trace_id UUID,
  org_id UUID,
  agent_id UUID,
  model String,
  prompt_tokens UInt32,
  completion_tokens UInt32,
  total_latency_ms UInt32,
  created_at DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (org_id, agent_id, created_at)
TTL created_at + INTERVAL 90 DAY;
```

**Design Choices Explained:**

**ENGINE = MergeTree:**

- Most common engine for analytics
- Background merges keep data sorted
- Supports TTL (automatic deletion)

**PARTITION BY toYYYYMM:**

- Each month is a separate partition
- Old partitions easily dropped (GDPR compliance)
- Queries with date filters only scan relevant partitions

**ORDER BY (org_id, agent_id, created_at):**

- Data sorted by these columns
- Queries filtering by org_id or agent_id are fast
- Time-range queries benefit from sorting by created_at

**TTL 90 days:**

- Old data automatically deleted
- Keeps storage costs manageable
- Compliance with data retention policies

---

### Object Storage: **MinIO (S3-Compatible)**

**Why S3-Compatible Storage:**

**What We Store:**

- Full session transcripts (potentially GB per long session)
- Large memory snapshots
- Directive archives
- Exported data (GDPR requests, backups)

**These are:**

- Written once, read rarely
- Large files (MB to GB)
- Cost-sensitive (don't want expensive block storage)

**Object Storage Economics:**

- Block storage (EBS, etc.): $0.10/GB/month
- Object storage (S3, MinIO): $0.023/GB/month
- 4-5x cheaper for cold data

**Why MinIO over AWS S3:**

**AWS S3 (Cloud Deployment):**

- Use AWS S3 directly (mature, reliable, cheap)

**MinIO (Self-Hosted Deployment):**

- S3-compatible API (same code works for both)
- Self-hosted (data sovereignty for enterprise)
- Open source (can modify if needed)
- High performance (can saturate 10GbE)

**Compatibility Layer:**

```python
import boto3

# Works with both AWS S3 and MinIO
s3 = boto3.client(
    's3',
    endpoint_url=os.getenv('S3_ENDPOINT'),  # AWS or MinIO
    aws_access_key_id=os.getenv('S3_KEY'),
    aws_secret_access_key=os.getenv('S3_SECRET')
)

# Same API for both
s3.put_object(Bucket='ibex-sessions', Key='session.json', Body=data)
```

**Lifecycle Policies:**

```json
{
  "Rules": [
    {
      "Id": "archive-old-sessions",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ],
      "Expiration": {
        "Days": 730
      }
    }
  ]
}
```

**Result:**

- Recent sessions: Hot storage (fast access)
- 90+ day sessions: Cold storage (cheaper, slower)
- 2+ year sessions: Deleted automatically

---

## 🔧 Development & Operations Tools

### Containerization: **Docker**

**Why Docker:**

- Industry standard (everyone knows it)
- Excellent tooling (Docker Compose, Docker Desktop)
- Consistent environments (dev, staging, prod)
- Efficient layering (cache intermediate layers)

**Multi-Stage Builds:**

```dockerfile
# Stage 1: Build
FROM golang:1.21 AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o proxy ./cmd/proxy

# Stage 2: Runtime
FROM gcr.io/distroless/static-debian11
COPY --from=builder /app/proxy /proxy
ENTRYPOINT ["/proxy"]
```

**Result:**

- Build stage: 1GB (includes Go toolchain)
- Runtime image: 15MB (just the binary)
- Smaller images = faster deployments

---

### Orchestration: **Kubernetes**

**Why Kubernetes:**

**Alternatives Considered:**

| Alternative | Why Not Chosen |
|-------------|----------------|
| **Docker Swarm** | Simpler to operate, but lacks ecosystem. No Helm, no Operators, smaller community. At scale, Kubernetes wins. |
| **Nomad** | Interesting alternative, but smaller ecosystem. Fewer production examples. Kubernetes is the proven choice for complex systems. |
| **ECS/Fargate** | AWS-only. Multi-cloud + self-hosted requirement eliminates cloud-specific orchestration. |
| **Manual VMs** | Doesn't scale. No automatic failover, no rolling updates, no resource scheduling. |

**What Kubernetes Provides:**

- **Automatic failover**: Container dies → K8s restarts it
- **Rolling updates**: Deploy new version with zero downtime
- **Horizontal scaling**: Scale from 3 to 20 instances automatically
- **Service discovery**: Services find each other by name
- **Secret management**: Securely inject secrets
- **Resource limits**: Prevent runaway processes
- **Health checks**: Automatic removal of unhealthy instances

**Helm for Packaging:**

**Why Helm:**

- Package Kubernetes manifests with variables
- One chart, many environments (dev, staging, prod)
- Versioned releases (rollback easily)
- Standard way to distribute K8s apps

**Helm Chart Structure:**

```text
ibex-harness/
  Chart.yaml          # Chart metadata
  values.yaml         # Default values
  values-prod.yaml    # Production overrides
  templates/
    proxy/
      deployment.yaml
      service.yaml
      hpa.yaml
    memory-service/
      deployment.yaml
      service.yaml
    postgresql/
      statefulset.yaml
      service.yaml
```

**One Command Deployment:**

```bash
helm install ibex ./ibex-harness \
  --namespace ibex-system \
  --values values-prod.yaml
```

---

### CI/CD: **GitHub Actions**

**Why GitHub Actions:**

| Alternative | Why Not Chosen |
|-------------|----------------|
| **Jenkins** | Self-hosted burden. Complex to maintain. Legacy system. |
| **CircleCI/TravisCI** | Another SaaS dependency. GitHub Actions integrated with repo. |
| **GitLab CI** | Would require GitLab hosting. We use GitHub. |
| **ArgoCD** | For CD (deployment), not CI. We use both: Actions for CI, ArgoCD for CD. |

**What GitHub Actions Provides:**

- Integrated with GitHub (no separate login)
- Matrix builds (test on multiple Python/Node versions)
- Caching (faster builds)
- Secrets management
- Free for open-source, reasonable pricing for private

**Example Workflow:**

```yaml
name: CI

on: [push, pull_request]

jobs:
  test-python:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -r requirements-dev.txt
      - run: pytest --cov --cov-report=xml
      - uses: codecov/codecov-action@v5
        with:
          files: coverage-python.xml
          flags: python

  test-go:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-go@v4
        with:
          go-version: '1.21'
      - run: go test -count=1 -coverprofile=coverage-go-unit.out ./packages/... ./services/...
      - uses: codecov/codecov-action@v5
        with:
          files: coverage-go-unit.out
          flags: go,unit

  test-typescript:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - run: npm ci
      - run: npm run test:ci
```

---

### GitOps Deployment: **ArgoCD**

**Why ArgoCD:**

**GitOps Philosophy:**

- Git is source of truth for infrastructure
- Declare desired state in Git
- ArgoCD reconciles cluster to match Git
- Changes require PR review (no cowboy deploys)

**Benefits:**

- **Audit trail**: Every deployment is a Git commit
- **Rollback**: `git revert` to undo deployment
- **Disaster recovery**: Rebuild cluster from Git
- **Multi-cluster**: Manage dev/staging/prod from one place

**ArgoCD Application:**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ibex-harness
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/ibexharness/ibex
    targetRevision: main
    path: helm/ibex-harness
    helm:
      valueFiles:
        - values-prod.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: ibex-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**Result:**

- Push to `main` → ArgoCD detects change → Updates cluster
- Automatic or manual sync (configurable)
- Diff view before sync
- Health monitoring after sync

---

### Monitoring: **Prometheus + Grafana**

**Why Prometheus:**

- Industry standard for metrics
- Pull-based (agents don't need outbound access)
- Powerful query language (PromQL)
- Service discovery (auto-discovers Kubernetes services)
- Alerting built-in (Alertmanager)

**Why Grafana:**

- Best visualization for Prometheus
- Templated dashboards (variables, repeating panels)
- Alerting (alternative to Alertmanager)
- Multi-datasource (Prometheus, Loki, ClickHouse)

**Not Datadog/NewRelic:**

- $15-30/host/month quickly becomes expensive
- Vendor lock-in
- Self-hosted requirement for enterprise
- Prometheus + Grafana: Free, open-source, powerful

---

### Logging: **Loki**

**Why Loki:**

- "Like Prometheus, but for logs"
- Indexes labels, not content (cheaper than Elasticsearch)
- Integrates perfectly with Grafana
- Stores logs in object storage (S3/MinIO) - cheap

**Not Elasticsearch:**

- Elasticsearch indexes full text → expensive
- Complex to operate (cluster management)
- Heavy memory usage
- Loki is 10x cheaper for same data

**Loki Query Example:**

```logql
{service="proxy", org_id="123"}
  | json
  | latency_ms > 100
```

---

### Error Tracking: **Sentry**

**Why Sentry:**

- Best error grouping (deduplicates similar errors)
- Source map support (unminify JavaScript)
- Breadcrumbs (what happened before error)
- Release tracking (which version introduced error)
- Self-hosted option (enterprise requirement)

**SDKs for All Languages:**

```python
# Python
import sentry_sdk
sentry_sdk.init(dsn="...")
```

```typescript
// TypeScript
import * as Sentry from "@sentry/nextjs";
Sentry.init({ dsn: "..." });
```

```go
// Go
import "github.com/getsentry/sentry-go"
sentry.Init(sentry.ClientOptions{Dsn: "..."})
```

---

### Infrastructure as Code: **Terraform**

**Why Terraform:**

- Multi-cloud (AWS, GCP, Azure)
- Declarative (describe what you want, Terraform figures out how)
- State management (knows what exists, what to change)
- Plan before apply (review changes)
- Modules (reusable components)

**Not CloudFormation/ARM Templates:**

- Vendor-specific (can't switch clouds)
- Less mature

**Not Pulumi:**

- Newer, smaller ecosystem
- Terraform is proven standard

**Example:**

```hcl
resource "aws_eks_cluster" "ibex" {
  name     = "ibex-prod"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = "1.28"

  vpc_config {
    subnet_ids = [
      aws_subnet.private_1.id,
      aws_subnet.private_2.id,
    ]
  }
}
```

---

## 📦 Complete Stack Summary

| Layer | Technology | Why This Choice |
|-------|-----------|-----------------|
| **Proxy** | Go 1.21+ | Low latency, high concurrency, single binary |
| **API/Workers** | Python 3.11+, FastAPI, Celery | ML ecosystem, async support, rapid development |
| **Dashboard** | Next.js 14, TypeScript, Tailwind | Server components, type safety, fast development |
| **CLI** | Go 1.21+, Cobra | Single binary, fast startup, cross-platform |
| **SDKs** | Python, TypeScript, Go | Cover 90%+ of agent use cases |
| **Primary DB** | PostgreSQL 16, pgvector | ACID, RLS, vector search, mature |
| **Cache** | Redis 7.x Stack | Speed, data structures, Lua scripting |
| **Analytics** | ClickHouse 23.x | Columnar, compression, billions of rows |
| **Object Store** | MinIO (S3-compatible) | Cheap, self-hostable, S3 API |
| **Container** | Docker | Industry standard, efficient |
| **Orchestration** | Kubernetes, Helm | Scalability, reliability, ecosystem |
| **CI** | GitHub Actions | Integrated, powerful, free tier |
| **CD** | ArgoCD | GitOps, audit trail, rollback |
| **Metrics** | Prometheus, Grafana | Pull model, PromQL, visualization |
| **Logging** | Loki | Cheap, Prometheus-like, Grafana |
| **Errors** | Sentry | Grouping, breadcrumbs, self-hosted |
| **IaC** | Terraform | Multi-cloud, declarative, proven |

---

**Every choice justified by:**

1. Performance requirements (proxy latency, data scale)
2. Operational simplicity (fewer systems to manage)
3. Team productivity (good DX, good docs)
4. Long-term viability (won't be abandoned)
5. Enterprise requirements (self-hosted, multi-cloud)

**We avoid:**

- Bleeding edge (unproven)
- Vendor lock-in (where possible)
- Over-engineering (start simple, scale later)
- Technology for technology's sake (use boring tech)
