# IBEX Harness - Coding Standards

## 🎯 Philosophy

These standards exist for one reason: **to make the codebase predictable**. When every engineer and every AI agent follows the same patterns, anyone can read any part of the codebase and immediately understand what it does, why it exists, and how it behaves under failure.

Standards are not suggestions. They are enforced by:

- Linters that fail the build
- Type checkers that reject incorrect code
- Code review that blocks merges
- CI pipelines that prevent deployment

If a standard seems wrong for a specific case, the correct response is to open a discussion and change the standard — not to quietly violate it.

---

## 🌍 Universal Standards (All Languages)

### Naming Philosophy

Names are the primary documentation of code. A well-named function needs no comment. A poorly named function misleads even with comments.

**Rules that apply in every language:**

1. **Names describe what, not how**

   ```text
   Good: calculateMemoryScore()
   Bad:  runLoopAndMultiply()
   ```

2. **Names describe the complete truth**

   ```text
   Good: getActiveMemoriesForAgent()
   Bad:  getMemories()  (what memories? which agent?)
   ```

3. **Boolean names are assertions**

   ```text
   Good: isExpired, hasPermission, shouldRetry
   Bad:  expired, permission, retry
   ```

4. **Functions that cause side effects say so**

   ```text
   Good: saveMemoryToDatabase(), sendNotification()
   Bad:  memory(), notify()
   ```

5. **Abbreviations are forbidden unless universal**

   ```text
   Allowed: id, url, api, http, sql, uuid, ttl, ctx
   Forbidden: mem (use memory), sess (use session),
              cfg (use config), msg (use message)
   ```

### Comment Standards

**What comments explain:**

- WHY a decision was made (not what the code does)
- Non-obvious edge cases being handled
- Links to external documentation, RFCs, or bug reports
- Temporary workarounds with ticket references

**What comments never do:**

- Restate what the code does in English
- Track history (that is what git is for)
- Explain obvious code

```python
# WRONG: This comment restates the code
# Increment the counter by 1
counter += 1

# RIGHT: This comment explains the why
# Increment before checking limit because the current
# request counts against the quota even if rejected.
# See rate limiting RFC in docs/adr/003-rate-limiting.md
counter += 1
if counter > limit:
    raise QuotaExceeded()
```

**TODO comments require a ticket:**

```python
# TODO(IBEX-247): Replace with streaming implementation
# once the streaming embedder service is deployed
result = embed_synchronously(text)
```

Never merge code with `TODO` comments that lack ticket references.

### Error Handling Philosophy

**Errors are first-class citizens.** They are not afterthoughts. Every function that can fail must make its failure modes explicit and handle them completely.

**Universal rules:**

1. **Never silently swallow errors**

   ```python
   # FORBIDDEN
   try:
       do_thing()
   except Exception:
       pass  # This hides real problems

   # REQUIRED
   try:
       do_thing()
   except SpecificError as e:
       logger.error("Thing failed", error=str(e),
                    context=context)
       raise  # Or handle specifically
   ```

2. **Catch specific exceptions, not broad ones**

   ```python
   # FORBIDDEN
   except Exception as e:

   # REQUIRED
   except (DatabaseConnectionError,
           DatabaseTimeoutError) as e:
   ```

3. **Errors must include context**

   ```python
   # FORBIDDEN
   raise ValueError("Invalid input")

   # REQUIRED
   raise ValueError(
       f"Memory content exceeds maximum length: "
       f"got {len(content)} chars, max is {MAX_CONTENT_LENGTH}. "
       f"agent_id={agent_id}"
   )
   ```

4. **Every error has an appropriate level**

   ```text
   ERROR:   System cannot proceed, human must intervene
   WARNING: System degraded but functional, investigate soon
   INFO:    Normal operation events worth recording
   DEBUG:   Detailed diagnostic, never in production
   ```

### Logging Standards

Every log entry must be structured JSON with these fields:

```json
{
  "timestamp": "2024-01-20T15:30:45.123Z",
  "level": "INFO",
  "service": "memory-service",
  "trace_id": "550e8400-...",
  "span_id": "a1b2c3d4",
  "org_id": "123e4567-...",
  "agent_id": "550e8400-...",
  "session_id": "7c9e6679-...",
  "message": "Memory created successfully",
  "memory_id": "a1b2c3d4-...",
  "duration_ms": 145,
  "category": "preference"
}
```

**What must never appear in logs:**

- API keys, tokens, passwords (any kind)
- Full memory content (PII risk)
- Credit card numbers or financial data
- Personal email addresses or phone numbers
- JWT token values

**The secret detection rule:** If a variable is named `token`, `key`, `secret`, `password`, `credential`, or `auth`, it must never be passed to a logger.

### Testing Standards

**The testing pyramid for IBEX Harness:**

```text
        /\
       /  \
      / E2E \      10% — Critical user flows only
     /--------\
    / Integration\  20% — Service interactions
   /--------------\
  /   Unit Tests   \  70% — Business logic, algorithms
 /------------------\
```

**Every piece of code must have tests that:**

1. Test behavior, not implementation

   ```python
   # WRONG: Tests implementation details
   def test_uses_correct_sql():
       # This breaks on any refactoring
       assert "SELECT * FROM" in query

   # RIGHT: Tests observable behavior
   def test_returns_active_memories_for_agent():
       # Creates real data, verifies real result
       memory = create_memory(agent_id=agent_id,
                              status="active")
       results = get_memories(agent_id=agent_id)
       assert memory.id in [m.id for m in results]
   ```

2. Test failure cases as thoroughly as happy paths

   ```python
   # For every function, test:
   # - Normal input → expected output
   # - Edge case inputs (empty, None, zero, max)
   # - Invalid input → correct error
   # - External dependency failure → graceful handling
   ```

3. Use real infrastructure for integration tests

   ```python
   # FORBIDDEN in integration tests
   mock_db = MagicMock()

   # REQUIRED in integration tests
   @pytest.fixture
   def db(postgres_container):
       return create_real_connection(postgres_container.url)
   ```

### Security Standards

**These rules apply everywhere, no exceptions:**

1. **All user input is untrusted until validated**

   ```python
   # Input validated at API boundary
   # Not trusted anywhere downstream
   # Even if validated, don't use in raw SQL
   ```

2. **SQL queries are always parameterized**

   ```python
   # FORBIDDEN — SQL injection vulnerability
   query = f"SELECT * FROM memories WHERE id = '{memory_id}'"

   # REQUIRED — Parameterized
   query = "SELECT * FROM memories WHERE id = $1"
   result = await db.fetch_one(query, memory_id)
   ```

3. **org_id is always included in data access**

   ```python
   # FORBIDDEN — Cross-tenant data leak
   memory = await db.fetch_one(
       "SELECT * FROM memories WHERE id = $1",
       memory_id
   )

   # REQUIRED — Tenant-scoped
   memory = await db.fetch_one(
       "SELECT * FROM memories WHERE id = $1 AND org_id = $2",
       memory_id, token.org_id
   )
   ```

4. **Secrets are never hardcoded**

   ```python
   # FORBIDDEN
   API_KEY = "sk-abc123..."

   # REQUIRED
   API_KEY = os.environ["OPENAI_API_KEY"]
   ```

5. **Cryptographic operations use approved algorithms only**

   ```text
   Hashing passwords: Argon2id only
   Signing tokens: RS256 (asymmetric) only
   Symmetric encryption: AES-256-GCM only
   Randomness: cryptographically secure RNG only
   Content hashing: SHA-256 only
   ```

---

## 🐹 Go Standards

### Package Organization

```text
services/proxy/
├── cmd/
│   └── proxy/
│       └── main.go          -- Entry point only. No logic here.
├── internal/
│   ├── auth/                -- Authentication logic
│   │   ├── bloom_filter.go
│   │   ├── lru_cache.go
│   │   ├── validator.go
│   │   └── validator_test.go
│   ├── ratelimit/           -- Rate limiting
│   │   ├── token_bucket.go
│   │   ├── lua_scripts.go
│   │   └── token_bucket_test.go
│   ├── proxy/               -- Core proxy logic
│   │   ├── handler.go
│   │   ├── context.go
│   │   ├── streaming.go
│   │   └── handler_test.go
│   ├── circuit/             -- Circuit breaker
│   │   ├── breaker.go
│   │   └── breaker_test.go
│   └── metrics/             -- Prometheus metrics
│       └── metrics.go
├── pkg/
│   └── ibexclient/          -- Reusable client (used by CLI too)
│       ├── client.go
│       └── client_test.go
├── Dockerfile
├── go.mod
└── go.sum
```

**Package naming rules:**

- Lowercase, single word when possible
- No underscores, no hyphens, no camelCase
- Name describes the domain, not the pattern

  ```text
  Good: auth, memory, ratelimit, circuit
  Bad: authService, memoryManager, rateLimitHelper
  ```

**`internal/` vs `pkg/`:**

- `internal/`: Code used only within this service
- `pkg/`: Code that may be imported by other services or tools

**`cmd/` rules:**

- Contains only `main.go` files
- `main()` does: parse config, wire dependencies, start server, handle shutdown signals
- No business logic in `main.go`

### Error Handling

**The four error patterns in this codebase:**

**Pattern 1: Sentinel errors for known conditions**

```go
// In the package that owns the error
var (
    ErrMemoryNotFound    = errors.New("memory not found")
    ErrQuotaExceeded     = errors.New("quota exceeded")
    ErrSessionExpired    = errors.New("session expired")
    ErrPermissionDenied  = errors.New("permission denied")
)

// Check with errors.Is()
if errors.Is(err, ErrMemoryNotFound) {
    return nil, status.Error(codes.NotFound, err.Error())
}
```

**Pattern 2: Error types for structured data**

```go
type ValidationError struct {
    Field   string
    Code    string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed: %s: %s",
                       e.Field, e.Message)
}

// Check with errors.As()
var ve *ValidationError
if errors.As(err, &ve) {
    // Access ve.Field, ve.Code
}
```

**Pattern 3: Wrapping with context**

```go
// Always wrap with context that adds information
if err := db.QueryRow(ctx, query, args...).Scan(&memory); err != nil {
    return nil, fmt.Errorf(
        "fetch memory %s for org %s: %w",
        memoryID, orgID, err,
    )
}
```

**Pattern 4: Error groups for concurrent operations**

```go
g, ctx := errgroup.WithContext(ctx)
var directive string
var hotMemories []Memory

g.Go(func() error {
    var err error
    directive, err = loadDirective(ctx, agentID)
    return fmt.Errorf("load directive: %w", err)
})

g.Go(func() error {
    var err error
    hotMemories, err = loadHotMemories(ctx, agentID)
    return fmt.Errorf("load hot memories: %w", err)
})

if err := g.Wait(); err != nil {
    return nil, err
}
```

**What is forbidden:**

```go
// FORBIDDEN: Ignoring errors
result, _ := doThing()

// FORBIDDEN: Panic for non-exceptional conditions
if user == nil {
    panic("user is nil") // Use error return instead
}

// FORBIDDEN: Broad error creation with no context
return errors.New("error")
```

### Goroutine Management

**Every goroutine must have:**

1. A clear owner (who is responsible for its lifecycle)
2. A clear termination condition
3. Panic recovery if it runs indefinitely
4. A way to propagate errors back

```go
// Pattern: Worker pool with error propagation
func (p *Processor) Start(ctx context.Context) error {
    g, ctx := errgroup.WithContext(ctx)

    for i := 0; i < p.workers; i++ {
        g.Go(func() error {
            return p.runWorker(ctx)
        })
    }

    return g.Wait()
}

func (p *Processor) runWorker(ctx context.Context) error {
    defer func() {
        if r := recover(); r != nil {
            p.logger.Error("Worker panic recovered",
                          "panic", r,
                          "stack", debug.Stack())
        }
    }()

    for {
        select {
        case <-ctx.Done():
            return ctx.Err()
        case job, ok := <-p.jobs:
            if !ok {
                return nil // Channel closed, exit cleanly
            }
            if err := p.processJob(ctx, job); err != nil {
                p.logger.Error("Job failed",
                              "job_id", job.ID,
                              "error", err)
                // Log and continue, don't crash the worker
            }
        }
    }
}
```

**Goroutine leak prevention:**

```go
// FORBIDDEN: Goroutine with no termination
go func() {
    for {
        doWork() // This runs forever with no way to stop
    }
}()

// REQUIRED: Context-aware goroutine
go func() {
    ticker := time.NewTicker(10 * time.Second)
    defer ticker.Stop()
    for {
        select {
        case <-ctx.Done():
            return // Clean exit when context cancelled
        case <-ticker.C:
            doWork(ctx)
        }
    }
}()
```

### Context Propagation

```go
// REQUIRED: Context is first parameter, always
func GetMemory(ctx context.Context,
               memoryID string,
               orgID string) (*Memory, error) {
    // Use ctx for:
    // 1. Cancellation (respect ctx.Done())
    // 2. Timeout (ctx has deadline)
    // 3. Trace propagation (extract span from ctx)
    // 4. Request-scoped values (org_id, trace_id)
}

// FORBIDDEN: Context stored in struct
type Service struct {
    ctx context.Context // Never do this
}

// FORBIDDEN: context.Background() inside request handler
func HandleRequest(w http.ResponseWriter,
                   r *http.Request) {
    // WRONG: Creates a context disconnected from request
    ctx := context.Background()
    // CORRECT: Use the request's context
    ctx := r.Context()
}
```

**Setting timeouts:**

```go
// For outbound calls, always set timeouts explicitly
func callAuthService(ctx context.Context,
                     tokenHash string) (*Claims, error) {
    // Create child context with timeout
    // Parent cancellation still works (shorter wins)
    callCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()

    return p.authClient.ValidateToken(callCtx, tokenHash)
}
```

### Interface Design

```go
// RULE: Interfaces defined at consumer, not producer
// The proxy defines what it needs from auth

// In package proxy:
type TokenValidator interface {
    Validate(ctx context.Context,
             tokenHash string) (*Claims, error)
}

// In package auth:
type Service struct { ... }

func (s *Service) Validate(ctx context.Context,
                            tokenHash string) (*Claims, error) {
    // Implements proxy.TokenValidator without knowing it
}

// RULE: Small, focused interfaces
// WRONG: One giant interface
type MemoryService interface {
    Create(...)
    Read(...)
    Update(...)
    Delete(...)
    Search(...)
    Rank(...)
    Extract(...)
    Deduplicate(...)
    ResolveConflict(...)
    // ... 20 more methods
}

// RIGHT: Focused interfaces per use case
type MemoryReader interface {
    GetMemory(ctx context.Context, id string) (*Memory, error)
    SearchMemories(ctx context.Context,
                   req *SearchRequest) ([]*Memory, error)
}

type MemoryWriter interface {
    CreateMemory(ctx context.Context,
                 req *CreateRequest) (*Memory, error)
    UpdateMemory(ctx context.Context,
                 id string,
                 req *UpdateRequest) (*Memory, error)
}
```

### Concurrency Primitives

```go
// Mutex rules:
// 1. Name the mutex after what it protects
type Cache struct {
    mu      sync.RWMutex // Protects entries
    entries map[string]*Entry
}

// 2. Lock for the minimum duration
func (c *Cache) Get(key string) (*Entry, bool) {
    c.mu.RLock()
    entry, ok := c.entries[key]
    c.mu.RUnlock() // Unlock before any expensive operations
    return entry, ok
}

// 3. Never hold mutex while calling external functions
func (c *Cache) GetWithRefresh(ctx context.Context,
                                key string) (*Entry, error) {
    c.mu.RLock()
    entry, ok := c.entries[key]
    c.mu.RUnlock()

    if !ok || entry.IsExpired() {
        // Fetch WITHOUT holding mutex (external call)
        fresh, err := c.fetchFromSource(ctx, key)
        if err != nil {
            return nil, err
        }

        // Re-acquire to update
        c.mu.Lock()
        c.entries[key] = fresh
        c.mu.Unlock()
        return fresh, nil
    }

    return entry, nil
}

// Channel rules:
// 1. Buffered channels for known capacity
jobs := make(chan Job, 100) // Won't block until 100 full

// 2. Close channels from sender, never receiver
close(jobs) // Only the goroutine sending to jobs closes it

// 3. Check for closed channel
job, ok := <-jobs
if !ok {
    return // Channel closed, exit
}
```

### Memory Management in Hot Path

```go
// The proxy hot path runs millions of times per day.
// Allocations in this path drive GC pressure.

// WRONG: Allocates new slice on every request
func buildHeaders(token string) []Header {
    return []Header{
        {Key: "Authorization", Value: "Bearer " + token},
    }
}

// RIGHT: Use sync.Pool for frequently allocated objects
var requestPool = sync.Pool{
    New: func() interface{} {
        return &ProxyRequest{
            Headers: make([]Header, 0, 10),
        }
    },
}

func handleRequest(w http.ResponseWriter,
                   r *http.Request) {
    req := requestPool.Get().(*ProxyRequest)
    defer func() {
        req.Reset() // Clear fields
        requestPool.Put(req)
    }()

    // Use req...
}

// WRONG: String concatenation in loop
var result string
for _, m := range memories {
    result += m.Content + "\n"
}

// RIGHT: strings.Builder (single allocation)
var sb strings.Builder
sb.Grow(estimatedSize) // Pre-allocate if size known
for _, m := range memories {
    sb.WriteString(m.Content)
    sb.WriteByte('\n')
}
result := sb.String()
```

### Testing in Go

```go
// Table-driven tests: required for functions with
// multiple input/output combinations
func TestComputeRelevanceScore(t *testing.T) {
    tests := []struct {
        name          string
        similarity    float64
        ageDays       float64
        retrievalCount int
        confidence    float64
        wantScore     float64
        wantErr       bool
    }{
        {
            name:          "high similarity recent memory",
            similarity:    0.95,
            ageDays:       1,
            retrievalCount: 10,
            confidence:    0.9,
            wantScore:     0.87, // Computed from formula
        },
        {
            name:          "zero similarity returns minimum score",
            similarity:    0.0,
            ageDays:       1,
            retrievalCount: 100,
            confidence:    1.0,
            wantScore:     0.35, // Weighted by non-similarity factors
        },
        {
            name:          "very old memory penalized",
            similarity:    0.9,
            ageDays:       365,
            retrievalCount: 5,
            confidence:    0.8,
            wantScore:     0.52,
        },
        {
            name:          "negative similarity is error",
            similarity:    -0.1,
            wantErr:       true,
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            score, err := ComputeRelevanceScore(
                tt.similarity,
                tt.ageDays,
                tt.retrievalCount,
                tt.confidence,
            )

            if tt.wantErr {
                assert.Error(t, err)
                return
            }

            assert.NoError(t, err)
            assert.InDelta(t, tt.wantScore, score, 0.01)
        })
    }
}

// Integration tests use testcontainers
func TestMemoryStorage_Integration(t *testing.T) {
    if testing.Short() {
        t.Skip("Skipping integration test in short mode")
    }

    ctx := context.Background()

    // Start real PostgreSQL container
    container, err := testcontainers.GenericContainer(ctx,
        testcontainers.GenericContainerRequest{
            ContainerRequest: testcontainers.ContainerRequest{
                Image:        "pgvector/pgvector:pg16",
                ExposedPorts: []string{"5432/tcp"},
                Env: map[string]string{
                    "POSTGRES_DB":       "ibex_test",
                    "POSTGRES_USER":     "ibex",
                    "POSTGRES_PASSWORD": "ibex",
                },
                WaitingFor: wait.ForListeningPort("5432/tcp"),
            },
            Started: true,
        },
    )
    require.NoError(t, err)
    defer container.Terminate(ctx)

    // Run migration
    host, _ := container.Host(ctx)
    port, _ := container.MappedPort(ctx, "5432")
    dsn := fmt.Sprintf(
        "postgres://ibex:ibex@%s:%s/ibex_test",
        host, port.Port(),
    )

    db, err := NewDatabase(dsn)
    require.NoError(t, err)

    err = db.Migrate(ctx)
    require.NoError(t, err)

    // Run actual test
    store := NewMemoryStore(db)

    memory, err := store.Create(ctx, &CreateMemoryRequest{
        OrgID:    uuid.New(),
        AgentID:  uuid.New(),
        Content:  "Test memory content",
        Category: "factual",
    })
    require.NoError(t, err)
    assert.NotEmpty(t, memory.ID)
    assert.Equal(t, "factual", memory.Category)
}
```

---

## 🐍 Python Standards

### Project Structure

```text
services/memory-service/
├── src/
│   └── memory_service/
│       ├── __init__.py
│       ├── main.py              -- FastAPI app creation
│       ├── config.py            -- Settings with Pydantic
│       ├── dependencies.py      -- FastAPI dependencies
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── memories.py      -- Memory endpoints
│       │   ├── search.py        -- Search endpoints
│       │   └── health.py        -- Health check endpoints
│       ├── services/
│       │   ├── __init__.py
│       │   ├── memory_service.py    -- Business logic
│       │   ├── embedding_service.py -- Embedding integration
│       │   └── conflict_service.py  -- Conflict detection
│       ├── repositories/
│       │   ├── __init__.py
│       │   ├── memory_repository.py -- DB operations
│       │   └── cache_repository.py  -- Redis operations
│       ├── models/
│       │   ├── __init__.py
│       │   ├── domain.py        -- Domain models (dataclasses)
│       │   ├── requests.py      -- Pydantic request models
│       │   └── responses.py     -- Pydantic response models
│       ├── exceptions.py        -- Custom exception hierarchy
│       └── middleware.py        -- FastAPI middleware
├── tests/
│   ├── unit/
│   │   ├── test_memory_service.py
│   │   └── test_conflict_service.py
│   └── integration/
│       ├── conftest.py          -- Shared fixtures
│       └── test_memory_api.py
├── pyproject.toml
├── Dockerfile
└── alembic/
    ├── alembic.ini
    ├── env.py
    └── versions/
```

### Type Annotations

**Every function must be fully annotated:**

```python
# FORBIDDEN: Missing annotations
def get_memory(memory_id, org_id):
    ...

# REQUIRED: Complete annotations
async def get_memory(
    memory_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> Memory | None:
    ...
```

**mypy configuration (pyproject.toml):**

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
```

**When `Any` is needed (rare), document why:**

```python
# Required because third-party library returns untyped JSON
# See: https://github.com/example/lib/issues/123
data: Any = external_lib.parse(raw_json)
```

### Pydantic Models

```python
from pydantic import BaseModel, Field, field_validator, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Literal

# Request models: strict validation
class CreateMemoryRequest(BaseModel):
    model_config = ConfigDict(
        strict=True,  # No coercion (int stays int, str stays str)
        frozen=True,  # Immutable after creation
    )

    agent_id: UUID
    content: str = Field(
        min_length=1,
        max_length=10_000,
        description="Memory content"
    )
    category: Literal[
        "factual", "preference",
        "behavioral", "episodic", "procedural"
    ] = "factual"
    confidence: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Confidence score 0-1"
    )
    tags: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Searchable tags"
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: list[str]) -> list[str]:
        for tag in tags:
            if len(tag) > 50:
                raise ValueError(
                    f"Tag '{tag[:20]}...' exceeds 50 char limit"
                )
            if not tag.strip():
                raise ValueError("Tags cannot be empty strings")
        return [tag.lower().strip() for tag in tags]

    @field_validator("content")
    @classmethod
    def validate_content(cls, content: str) -> str:
        stripped = content.strip()
        if not stripped:
            raise ValueError(
                "Memory content cannot be only whitespace"
            )
        return stripped

# Response models: always use explicit fields
class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    org_id: UUID
    content: str
    category: str
    confidence: float
    status: str
    tags: list[str]
    retrieval_count: int
    created_at: datetime
    updated_at: datetime

    # NEVER include: embedding vectors (too large)
    # NEVER include: internal fields (content_hash, etc.)
```

### FastAPI Patterns

**App creation:**

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .routers import memories, search, health
from .dependencies import get_db_pool, get_redis_pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize resources
    app.state.db_pool = await create_db_pool(settings.database_url)
    app.state.redis = await create_redis_pool(settings.redis_url)

    yield  # Application runs here

    # Shutdown: Cleanup resources
    await app.state.db_pool.close()
    await app.state.redis.aclose()

app = FastAPI(
    title="IBEX Harness Memory Service",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
)

app.include_router(health.router, tags=["health"])
app.include_router(
    memories.router,
    prefix="/v1/memories",
    tags=["memories"]
)
app.include_router(
    search.router,
    prefix="/v1/memories",
    tags=["search"]
)
```

**Dependency injection:**

```python
# dependencies.py
from typing import Annotated, AsyncGenerator
from fastapi import Request, Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

# Database session: One per request, auto-closed
async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(request.app.state.db_pool) as session:
        try:
            # Set org isolation context for RLS
            await session.execute(
                text("SET LOCAL app.current_org_id = :org_id"),
                {"org_id": str(request.state.token.org_id)}
            )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# Token validation: Required on protected endpoints
async def require_token(
    authorization: Annotated[str | None,
                             Header(alias="Authorization")] = None,
    request: Request = None,
) -> TokenData:
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"code": "MISSING_TOKEN",
                    "message": "Authorization header required"}
        )

    token_value = authorization.removeprefix("Bearer ")
    token_data = await validate_token(token_value)
    request.state.token = token_data
    return token_data

# Permission checking: Composable with require_token
def require_permission(permission: Permission):
    async def checker(
        token: Annotated[TokenData, Depends(require_token)]
    ) -> TokenData:
        if not token.has_permission(permission):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "INSUFFICIENT_PERMISSIONS",
                    "message": f"Permission required: {permission}"
                }
            )
        return token
    return checker
```

**Router pattern:**

```python
# routers/memories.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated
from uuid import UUID

router = APIRouter()

@router.post(
    "",
    status_code=201,
    response_model=CreateMemoryResponse,
    summary="Create a memory",
)
async def create_memory(
    request: CreateMemoryRequest,
    token: Annotated[
        TokenData,
        Depends(require_permission(Permission.MEMORY_WRITE))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    memory_service: Annotated[
        MemoryService,
        Depends(get_memory_service)
    ],
) -> CreateMemoryResponse:
    """
    Create a new memory for an agent.

    Automatically handles deduplication, embedding generation,
    and conflict detection. Returns 409 if exact duplicate exists.
    """
    try:
        memory = await memory_service.create_memory(
            org_id=token.org_id,
            agent_id=request.agent_id,
            request=request,
        )
        return CreateMemoryResponse.model_validate(memory)

    except DuplicateMemoryError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE_CONTENT",
                "message": "Memory with identical content exists",
                "existing_memory_id": str(e.existing_id),
            }
        )
    except EmbeddingServiceError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "EMBEDDING_FAILED",
                "message": "Embedding service unavailable",
            }
        )
```

### Async Patterns

```python
# REQUIRED: All I/O operations must be async
async def get_memory(
    memory_id: UUID,
    db: AsyncSession,
) -> Memory | None:
    result = await db.execute(
        select(MemoryModel).where(
            MemoryModel.id == memory_id,
            MemoryModel.status == "active"
        )
    )
    return result.scalar_one_or_none()

# FORBIDDEN: Blocking calls in async context
async def bad_example():
    time.sleep(1)           # Blocks the event loop
    requests.get(url)       # Sync HTTP, blocks event loop
    file = open("file.txt") # Sync file I/O, blocks event loop

# REQUIRED: Use async alternatives
async def good_example():
    await asyncio.sleep(1)              # Non-blocking
    async with httpx.AsyncClient() as c:
        await c.get(url)                # Async HTTP
    async with aiofiles.open("f") as f: # Async file I/O
        content = await f.read()

# REQUIRED: CPU-bound work goes in thread pool
async def compute_intensive_operation(data: list[float]) -> float:
    loop = asyncio.get_event_loop()
    # Run in thread pool to not block event loop
    return await loop.run_in_executor(
        None,  # Uses default ThreadPoolExecutor
        compute_statistics,  # The sync function
        data
    )

# REQUIRED: Concurrent I/O operations run together
async def assemble_context(
    agent_id: UUID,
    session_id: UUID,
) -> Context:
    # These three operations run CONCURRENTLY
    directive, hot_memories, history = await asyncio.gather(
        load_directive(agent_id),
        load_hot_memories(agent_id),
        load_session_history(session_id),
        return_exceptions=True  # Don't cancel others on failure
    )

    # Check for failures after gather
    if isinstance(directive, Exception):
        logger.warning("Directive load failed, using fallback",
                       error=str(directive))
        directive = get_fallback_directive()

    # ... continue with available data
```

### Exception Hierarchy

```python
# exceptions.py

class IBEXError(Exception):
    """Base exception for all IBEX Harness errors."""
    code: str = "INTERNAL_ERROR"
    http_status: int = 500

class NotFoundError(IBEXError):
    """Resource not found."""
    code = "NOT_FOUND"
    http_status = 404

class MemoryNotFoundError(NotFoundError):
    code = "MEMORY_NOT_FOUND"

class SessionNotFoundError(NotFoundError):
    code = "SESSION_NOT_FOUND"

class ValidationError(IBEXError):
    """Input validation failed."""
    code = "VALIDATION_ERROR"
    http_status = 400

    def __init__(
        self,
        message: str,
        field: str | None = None,
        field_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.field_code = field_code

class PermissionError(IBEXError):
    """Insufficient permissions."""
    code = "INSUFFICIENT_PERMISSIONS"
    http_status = 403

class ConflictError(IBEXError):
    """Resource conflict."""
    code = "CONFLICT"
    http_status = 409

class DuplicateMemoryError(ConflictError):
    code = "DUPLICATE_CONTENT"

    def __init__(self, existing_id: UUID) -> None:
        super().__init__("Memory with identical content exists")
        self.existing_id = existing_id

class ExternalServiceError(IBEXError):
    """External service call failed."""
    code = "UPSTREAM_ERROR"
    http_status = 503

class EmbeddingServiceError(ExternalServiceError):
    code = "EMBEDDING_SERVICE_ERROR"

class QuotaExceededError(IBEXError):
    """Organization quota exceeded."""
    code = "QUOTA_EXCEEDED"
    http_status = 429
```

### SQLAlchemy Patterns

```python
# repositories/memory_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert

class MemoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        memory: MemoryCreate,
    ) -> MemoryModel:
        db_memory = MemoryModel(
            id=uuid.uuid4(),
            org_id=memory.org_id,
            agent_id=memory.agent_id,
            content=memory.content,
            content_hash=memory.content_hash,
            embedding=memory.embedding,
            category=memory.category,
            confidence=memory.confidence,
        )
        self.db.add(db_memory)
        await self.db.flush()  # Get DB-generated values
        await self.db.refresh(db_memory)  # Load defaults
        return db_memory

    async def get_by_id(
        self,
        memory_id: UUID,
        org_id: UUID,  # Always required: tenant isolation
    ) -> MemoryModel | None:
        # org_id in every query even with RLS
        # Defense in depth: don't rely solely on RLS
        result = await self.db.execute(
            select(MemoryModel).where(
                MemoryModel.id == memory_id,
                MemoryModel.org_id == org_id,
                MemoryModel.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def vector_search(
        self,
        org_id: UUID,
        agent_id: UUID,
        query_embedding: list[float],
        limit: int = 20,
        min_similarity: float = 0.7,
    ) -> list[tuple[MemoryModel, float]]:
        # pgvector cosine similarity search
        # Cast required: Python list → PostgreSQL vector
        embedding_literal = func.cast(
            query_embedding,
            Vector(384)
        )

        result = await self.db.execute(
            select(
                MemoryModel,
                (1 - MemoryModel.embedding.cosine_distance(
                    embedding_literal
                )).label("similarity")
            )
            .where(
                MemoryModel.org_id == org_id,
                MemoryModel.agent_id == agent_id,
                MemoryModel.status == "active",
                MemoryModel.deleted_at.is_(None),
                # Pre-filter: cosine distance < threshold
                MemoryModel.embedding.cosine_distance(
                    embedding_literal
                ) < (1 - min_similarity),
            )
            .order_by(
                MemoryModel.embedding.cosine_distance(
                    embedding_literal
                )
            )
            .limit(limit)
        )

        return [(row.MemoryModel, row.similarity)
                for row in result]

    async def search_by_content_hash(
        self,
        org_id: UUID,
        agent_id: UUID,
        content_hash: str,
    ) -> MemoryModel | None:
        result = await self.db.execute(
            select(MemoryModel).where(
                MemoryModel.org_id == org_id,
                MemoryModel.agent_id == agent_id,
                MemoryModel.content_hash == content_hash,
                MemoryModel.status != "deleted",
            )
        )
        return result.scalar_one_or_none()
```

### Testing in Python

```python
# tests/unit/test_memory_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

class TestMemoryService:
    """Unit tests for MemoryService business logic."""

    @pytest.fixture
    def memory_repo(self) -> AsyncMock:
        return AsyncMock(spec=MemoryRepository)

    @pytest.fixture
    def embedding_service(self) -> AsyncMock:
        return AsyncMock(spec=EmbeddingService)

    @pytest.fixture
    def service(
        self,
        memory_repo: AsyncMock,
        embedding_service: AsyncMock,
    ) -> MemoryService:
        return MemoryService(
            memory_repo=memory_repo,
            embedding_service=embedding_service,
        )

    async def test_create_memory_success(
        self,
        service: MemoryService,
        memory_repo: AsyncMock,
        embedding_service: AsyncMock,
    ) -> None:
        # Arrange
        org_id = uuid4()
        agent_id = uuid4()
        content = "User prefers dark mode"
        embedding = [0.1] * 384

        embedding_service.embed.return_value = embedding
        memory_repo.search_by_content_hash.return_value = None
        memory_repo.create.return_value = MemoryModel(
            id=uuid4(),
            org_id=org_id,
            agent_id=agent_id,
            content=content,
        )

        # Act
        result = await service.create_memory(
            org_id=org_id,
            agent_id=agent_id,
            request=CreateMemoryRequest(
                agent_id=agent_id,
                content=content,
            ),
        )

        # Assert
        assert result.content == content
        embedding_service.embed.assert_called_once_with(content)
        memory_repo.create.assert_called_once()

    async def test_create_memory_duplicate_raises(
        self,
        service: MemoryService,
        memory_repo: AsyncMock,
        embedding_service: AsyncMock,
    ) -> None:
        # Arrange
        existing_id = uuid4()
        memory_repo.search_by_content_hash.return_value = \
            MemoryModel(id=existing_id)

        # Act & Assert
        with pytest.raises(DuplicateMemoryError) as exc_info:
            await service.create_memory(
                org_id=uuid4(),
                agent_id=uuid4(),
                request=CreateMemoryRequest(
                    agent_id=uuid4(),
                    content="Duplicate content",
                ),
            )

        assert exc_info.value.existing_id == existing_id

    async def test_create_memory_embedding_failure_raises(
        self,
        service: MemoryService,
        embedding_service: AsyncMock,
    ) -> None:
        embedding_service.embed.side_effect = \
            EmbeddingServiceError("Service unavailable")

        with pytest.raises(EmbeddingServiceError):
            await service.create_memory(
                org_id=uuid4(),
                agent_id=uuid4(),
                request=CreateMemoryRequest(
                    agent_id=uuid4(),
                    content="Some content",
                ),
            )

# tests/integration/conftest.py
@pytest.fixture(scope="session")
async def postgres_container():
    """Start PostgreSQL container for integration tests."""
    container = PostgresContainer("pgvector/pgvector:pg16")
    container.start()

    # Run migrations
    engine = create_async_engine(container.get_connection_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield container

    container.stop()

@pytest.fixture
async def db_session(postgres_container):
    """Provide a database session for each test."""
    engine = create_async_engine(
        postgres_container.get_connection_url()
    )
    async with AsyncSession(engine) as session:
        # Set test org isolation
        await session.execute(
            text("SET LOCAL app.current_org_id = :id"),
            {"id": str(TEST_ORG_ID)}
        )
        yield session
        await session.rollback()  # Clean up after each test
```

---

## 📘 TypeScript Standards

### Project Structure

```text
services/dashboard/
├── src/
│   └── app/                     -- Next.js App Router
│       ├── (auth)/              -- Route group: auth pages
│       │   ├── login/
│       │   │   └── page.tsx
│       │   └── layout.tsx
│       ├── (dashboard)/         -- Route group: main app
│       │   ├── agents/
│       │   │   ├── page.tsx     -- Server component
│       │   │   └── [id]/
│       │   │       ├── page.tsx
│       │   │       └── sessions/
│       │   │           └── page.tsx
│       │   ├── memories/
│       │   │   └── page.tsx
│       │   └── layout.tsx       -- Dashboard layout
│       ├── api/                 -- Route handlers (API)
│       │   └── auth/
│       │       └── route.ts
│       ├── layout.tsx           -- Root layout
│       └── globals.css
├── src/
│   ├── components/
│   │   ├── ui/                  -- Base components (Button, etc.)
│   │   ├── memory/              -- Memory-specific components
│   │   ├── session/             -- Session components
│   │   └── charts/              -- Data visualization
│   ├── lib/
│   │   ├── api.ts               -- API client
│   │   ├── auth.ts              -- Auth utilities
│   │   └── utils.ts             -- Shared utilities
│   ├── hooks/                   -- Custom React hooks
│   ├── stores/                  -- Zustand stores
│   └── types/                   -- TypeScript types
├── tsconfig.json
├── next.config.js
└── tailwind.config.ts
```

### TypeScript Configuration

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "ES2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "strictNullChecks": true,
    "strictFunctionTypes": true,
    "noImplicitAny": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "forceConsistentCasingInFileNames": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

### Server vs Client Components

```typescript
// SERVER COMPONENT (default in App Router)
// File: app/(dashboard)/agents/page.tsx

// Server components:
// - Run on server, no JavaScript sent to client
// - Can directly access database, secrets
// - Cannot use useState, useEffect, event handlers
// - Cannot use browser APIs

import { getAgents } from "@/lib/api/agents"
import { AgentList } from "@/components/agent/AgentList"

// This function runs on the server
// The result is sent as HTML to the browser
export default async function AgentsPage() {
  // Direct data fetch on server (no useEffect needed)
  const agents = await getAgents()

  return (
    <main>
      <h1>Agents</h1>
      {/* AgentList receives data as props */}
      <AgentList agents={agents} />
    </main>
  )
}

// CLIENT COMPONENT
// File: components/agent/AgentActions.tsx
// Must have "use client" directive

"use client"

// Client components:
// - Shipped as JavaScript to browser
// - Can use useState, useEffect, event handlers
// - Can use browser APIs
// - Cannot directly access server resources

import { useState } from "react"
import { pauseAgent } from "@/lib/api/agents"

interface AgentActionsProps {
  agentId: string
  initialStatus: "active" | "paused"
}

export function AgentActions({
  agentId,
  initialStatus,
}: AgentActionsProps) {
  const [status, setStatus] = useState(initialStatus)
  const [isPausing, setIsPausing] = useState(false)

  async function handlePause() {
    setIsPausing(true)
    try {
      await pauseAgent(agentId)
      setStatus("paused")
    } finally {
      setIsPausing(false)
    }
  }

  return (
    <button
      onClick={handlePause}
      disabled={isPausing || status === "paused"}
    >
      {isPausing ? "Pausing..." : "Pause Agent"}
    </button>
  )
}

// RULE: Only add "use client" when needed
// Keep server components as server components
// Push client interactivity to leaf components
```

### Type Definitions

```typescript
// types/memory.ts

// Domain types match the API response exactly
export interface Memory {
  readonly id: string
  readonly agentId: string
  readonly orgId: string
  readonly content: string
  readonly contentTokens: number
  readonly category: MemoryCategory
  readonly confidence: number
  readonly source: MemorySource
  readonly status: MemoryStatus
  readonly visibility: MemoryVisibility
  readonly pinned: boolean
  readonly tags: readonly string[]
  readonly retrievalCount: number
  readonly usefulnessScore: number
  readonly piiDetected: boolean
  readonly injectionRiskScore: number
  readonly createdAt: string
  readonly updatedAt: string
  readonly lastRetrievedAt: string | null
}

// Use string unions for enums (not TypeScript enums)
// String unions are more predictable and debuggable
export type MemoryCategory =
  | "factual"
  | "preference"
  | "behavioral"
  | "episodic"
  | "procedural"

export type MemoryStatus =
  | "active"
  | "superseded"
  | "merged_into"
  | "archived"
  | "quarantined"
  | "deleted"

export type MemorySource =
  | "extracted"
  | "user_provided"
  | "imported"
  | "inferred"

export type MemoryVisibility = "agent" | "org" | "session"

// Request types
export interface CreateMemoryRequest {
  agentId: string
  content: string
  category?: MemoryCategory
  confidence?: number
  sessionId?: string
  visibility?: MemoryVisibility
  tags?: string[]
  pinned?: boolean
}

// API response envelope
export interface ApiResponse<T> {
  data: T
  meta?: Record<string, unknown>
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  pagination: {
    hasMore: boolean
    nextCursor: string | null
    prevCursor: string | null
    totalCount: number
  }
}

export interface ApiError {
  error: {
    code: string
    message: string
    detail?: string
    docsUrl?: string
    requestId: string
    timestamp: string
    fieldErrors?: Array<{
      field: string
      code: string
      message: string
    }>
  }
}
```

### API Client Pattern

```typescript
// lib/api/client.ts

class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
    public readonly requestId: string,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

async function apiRequest<T>(
  path: string,
  options: RequestInit & {
    params?: Record<string, string | number | boolean | undefined>
  } = {},
): Promise<T> {
  const { params, ...fetchOptions } = options

  // Build URL with query params
  const url = new URL(path, process.env.NEXT_PUBLIC_API_URL)
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        url.searchParams.set(key, String(value))
      }
    })
  }

  const response = await fetch(url.toString(), {
    ...fetchOptions,
    headers: {
      "Content-Type": "application/json",
      ...fetchOptions.headers,
    },
  })

  // Parse response
  const body = await response.json()

  if (!response.ok) {
    const errorBody = body as ApiError
    throw new ApiError(
      errorBody.error.message,
      errorBody.error.code,
      response.status,
      errorBody.error.requestId,
    )
  }

  return body as T
}

// lib/api/memories.ts
export async function createMemory(
  request: CreateMemoryRequest,
): Promise<Memory> {
  const response = await apiRequest<ApiResponse<Memory>>(
    "/v1/memories",
    {
      method: "POST",
      body: JSON.stringify(request),
    },
  )
  return response.data
}

export async function searchMemories(
  agentId: string,
  query: string,
  options: {
    limit?: number
    minSimilarity?: number
    categories?: MemoryCategory[]
  } = {},
): Promise<Memory[]> {
  const response = await apiRequest<ApiResponse<{
    results: Array<{ memory: Memory; scores: Record<string, number> }>
  }>>("/v1/memories/search", {
    method: "POST",
    body: JSON.stringify({
      agent_id: agentId,
      query,
      limit: options.limit,
      min_similarity: options.minSimilarity,
      filters: {
        category: options.categories,
      },
    }),
  })

  return response.data.results.map((r) => r.memory)
}
```

### State Management

```typescript
// stores/agent-store.ts
import { create } from "zustand"
import { devtools } from "zustand/middleware"

interface AgentStore {
  // State
  selectedAgentId: string | null
  sidebarCollapsed: boolean

  // Actions
  selectAgent: (agentId: string | null) => void
  toggleSidebar: () => void
}

export const useAgentStore = create<AgentStore>()(
  devtools(
    (set) => ({
      // Initial state
      selectedAgentId: null,
      sidebarCollapsed: false,

      // Actions: plain functions, no async
      selectAgent: (agentId) => set({ selectedAgentId: agentId }),
      toggleSidebar: () =>
        set((state) => ({
          sidebarCollapsed: !state.sidebarCollapsed,
        })),
    }),
    { name: "agent-store" }, // Redux DevTools name
  ),
)

// Usage: select only what you need (prevents unnecessary rerenders)
const selectedAgentId = useAgentStore(
  (state) => state.selectedAgentId
)
```

```typescript
// TanStack Query for server state
// hooks/use-memories.ts
import {
  useQuery,
  useMutation,
  useQueryClient
} from "@tanstack/react-query"

export function useMemories(agentId: string) {
  return useQuery({
    queryKey: ["memories", agentId],
    queryFn: () => getMemories(agentId),
    staleTime: 30_000,     // Fresh for 30 seconds
    gcTime: 5 * 60_000,    // Keep in cache for 5 minutes
  })
}

export function useCreateMemory() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: createMemory,
    onSuccess: (newMemory) => {
      // Invalidate and refetch memories for this agent
      queryClient.invalidateQueries({
        queryKey: ["memories", newMemory.agentId],
      })
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        // Handle specific error codes
        if (error.code === "DUPLICATE_CONTENT") {
          // Show specific UI for duplicates
        }
      }
    },
  })
}
```

### Component Patterns

```typescript
// REQUIRED: Loading and error states for every data component
// components/memory/MemoryList.tsx

"use client"

import { useMemories } from "@/hooks/use-memories"

interface MemoryListProps {
  agentId: string
}

export function MemoryList({ agentId }: MemoryListProps) {
  const { data: memories, isLoading, error, refetch } = useMemories(agentId)

  // Loading state: always show something meaningful
  if (isLoading) {
    return <MemoryListSkeleton count={5} />
  }

  // Error state: never show blank screen
  if (error) {
    return (
      <ErrorState
        title="Failed to load memories"
        description="We couldn't load the memories for this agent."
        retry={() => void refetch()}
      />
    )
  }

  // Empty state: inform user, offer action
  if (!memories || memories.length === 0) {
    return (
      <EmptyState
        title="No memories yet"
        description="This agent hasn't created any memories yet."
        action={<CreateMemoryButton agentId={agentId} />}
      />
    )
  }

  return (
    <ul className="space-y-3">
      {memories.map((memory) => (
        <MemoryCard key={memory.id} memory={memory} />
      ))}
    </ul>
  )
}

// REQUIRED: Accessibility for interactive components
// components/ui/Button.tsx
interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger"
  size?: "sm" | "md" | "lg"
  isLoading?: boolean
  loadingText?: string
}

export function Button({
  variant = "primary",
  size = "md",
  isLoading = false,
  loadingText,
  disabled,
  children,
  ...props
}: ButtonProps) {
  const isDisabled = disabled || isLoading

  return (
    <button
      {...props}
      disabled={isDisabled}
      aria-busy={isLoading}
      aria-label={isLoading && loadingText
        ? loadingText
        : props["aria-label"]}
      className={cn(
        // Base styles
        "font-medium rounded-md transition-colors",
        "focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-offset-2 focus-visible:ring-blue-500",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        // Variant styles
        variant === "primary" && "bg-blue-600 text-white hover:bg-blue-700",
        variant === "secondary" && "bg-gray-100 text-gray-900 hover:bg-gray-200",
        variant === "danger" && "bg-red-600 text-white hover:bg-red-700",
        // Size styles
        size === "sm" && "px-3 py-1.5 text-sm",
        size === "md" && "px-4 py-2 text-sm",
        size === "lg" && "px-6 py-3 text-base",
      )}
    >
      {isLoading ? (
        <>
          <Spinner className="mr-2 h-4 w-4" aria-hidden="true" />
          {loadingText ?? children}
        </>
      ) : (
        children
      )}
    </button>
  )
}
```

---

## 🔬 Code Review Standards

### What Every Reviewer Checks

**Correctness:**

- [ ] Does the code do what it claims to do?
- [ ] Are all error cases handled?
- [ ] Are edge cases covered?
- [ ] Are the tests actually testing the right things?

**Security:**

- [ ] Is all input validated before use?
- [ ] Is org_id included in every data access query?
- [ ] Are there any SQL injection vectors?
- [ ] Are secrets handled correctly?
- [ ] Is there any prompt injection risk?

**Performance:**

- [ ] Are there N+1 query patterns?
- [ ] Is pagination used for large datasets?
- [ ] Are there unnecessary allocations in hot paths?
- [ ] Is async used correctly?

**Maintainability:**

- [ ] Are names descriptive and accurate?
- [ ] Is the code understandable without comments?
- [ ] Does it follow established patterns?
- [ ] Is the complexity justified?

**Testing:**

- [ ] Do tests cover failure cases?
- [ ] Are integration tests using real infrastructure?
- [ ] Are tests isolated from each other?

### Review Response Time

- All PRs must receive first review within 24 hours
- After requested changes: author has 48 hours to respond
- Stale PRs (no activity for 7 days) are closed with comment

### Merge Requirements

Before any PR can merge:

- [ ] All CI checks passing
- [ ] At least 2 approvals (1 for documentation-only changes)
- [ ] No unresolved review comments
- [ ] Branch is up-to-date with main
- [ ] Commit messages follow convention

### Commit Message Convention

```text
type(scope): short description (max 72 chars)

Optional longer description explaining why the change
was made, not what was changed (code shows what).

Fixes: IBEX-247
Breaking-change: false
```

**Types:**

```text
feat:     New feature
fix:      Bug fix
perf:     Performance improvement
refactor: Code change without feature or fix
test:     Adding or fixing tests
docs:     Documentation only
chore:    Build process, dependencies, tooling
security: Security fix
```

**Scopes:**

```text
proxy, memory, auth, context, session,
directive, worker, dashboard, sdk-python,
sdk-typescript, sdk-go, cli, infra, db
```

**Examples:**

```text
feat(memory): add vector similarity search with pgvector

Uses IVFFlat index for approximate nearest neighbor search.
Significantly faster than exact search at 1M+ vectors.

Fixes: IBEX-142

---

fix(proxy): prevent goroutine leak in streaming handler

When client disconnected mid-stream, the goroutine
accumulating the response continued running indefinitely.
Added context cancellation check in the read loop.

Fixes: IBEX-389

---

security(auth): use constant-time comparison for token validation

Previous string comparison was vulnerable to timing attacks.
Replaced with hmac.Equal() which runs in constant time.

Fixes: IBEX-401
Breaking-change: false
```
