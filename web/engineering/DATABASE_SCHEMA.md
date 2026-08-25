# IBEX Harness — Database Schema

PostgreSQL (OLTP + pgvector), Redis key patterns, and ClickHouse analytics schema. For system architecture and service flows, see [ARCHITECTURE.md](ARCHITECTURE.md).

**Roadmap note:** Phases **0–2** schema (orgs, users, agents, tokens, directives, sessions, `llm_traces`) is what is applied today. Phase **2.5** adds additive pre-work (temporal validity, multi-label categories, relationship-graph readiness). Phase **3** lands memory schema v2 with **HNSW** as the preferred vector index starting point. Phase **5** uses graph edges at query time (recursive CTEs) and hybrid retrieval — it does not require a separate graph database by default. See [`web/content/roadmap/`](../content/roadmap/).

## Schema Design Philosophy

### Core Principles

1. **Multi-tenancy at the schema level**: Every table that contains customer data has org_id as the first indexed column. Row-Level Security policies enforce this at the database engine level — not just at the application level.

2. **Immutability where it matters**: Billing events, audit logs, and memory versions are append-only. They are never updated or deleted (except via explicit GDPR deletion flows with full audit trails).

3. **Soft deletes with hard deletes for compliance**: Most entities use soft deletes (status column) for operational safety. GDPR deletion requests trigger hard deletes with cryptographically signed deletion certificates.

4. **Schema evolution without downtime**: Every migration follows the expand-contract pattern:
   - Phase 1: Add new columns/tables (backward compatible)
   - Phase 2: Migrate data, update application
   - Phase 3: Remove old columns/tables (cleanup)

5. **Indexes designed for actual query patterns**: Every index exists because a specific query pattern requires it. No speculative indexes.

6. **Constraints at the database level**: Not just in application code. Check constraints, foreign keys, and unique constraints enforced by PostgreSQL regardless of application bugs.

---

### PostgreSQL Schema

#### Schema Organization

```sql
-- Schemas separate concerns and permission domains
CREATE SCHEMA ibex_core;      -- Core platform data
CREATE SCHEMA ibex_billing;   -- Billing and usage
CREATE SCHEMA ibex_audit;     -- Audit logs (append-only)
CREATE SCHEMA ibex_analytics; -- Summary analytics
```

---

#### Organizations and Users

> **Milestone 1.1.1:** `ibex_core.organizations` and `ibex_core.tokens` are applied via numbered SQL in [`infra/migrations/postgres/`](../../infra/migrations/postgres/). Run `make db-migrate` after local Compose is up.
>
> **Milestone 1.1.7:** `ibex_core.users` and `ibex_core.agents` are applied as the Phase-1 column subset (see migrations `000006`–`000007`). `tokens.revoked_by` remains a single-column FK (`000008`). `tokens.user_id` / `tokens.agent_id` enforce tenant ownership via composite FKs `(user_id, org_id)` / `(agent_id, org_id)` (`000012`; `users` and `agents` expose `UNIQUE (id, org_id)`). Full-schema columns deferred to Phase 3+ remain documented below but are not yet migrated.
>
> **Milestone 2.3.1:** `ibex_core.directives` and `ibex_core.directive_versions` are applied as the Phase-2 agent-scoped subset (`000009`; see [ADR-0030](../content/docs/adr/0030-directive-versioning.mdx)). The marketplace-oriented columns documented in the DIRECTIVES sections below are not yet migrated.

```sql
-- ================================================================
-- ORGANIZATIONS
-- Root entity for multi-tenancy
-- ================================================================
CREATE TABLE ibex_core.organizations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,  -- URL-safe identifier
    tier            TEXT NOT NULL DEFAULT 'free'
                    CHECK (tier IN ('free', 'pro', 'enterprise')),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended',
                                      'cancelled', 'trial')),

    -- Quotas (overrides default tier limits)
    custom_token_quota_monthly    BIGINT,
    custom_memory_quota           BIGINT,
    custom_agent_quota            INTEGER,

    -- Billing
    stripe_customer_id            TEXT UNIQUE,
    billing_email                 TEXT,
    billing_cycle_anchor          DATE,

    -- Configuration
    settings                      JSONB NOT NULL DEFAULT '{}',
    -- settings schema:
    -- {
    --   "mfa_required": bool,
    --   "ip_allowlist": ["1.2.3.4/24"],
    --   "sso_domain": "company.com",
    --   "data_retention_days": 90,
    --   "memory_extraction_enabled": true,
    --   "drift_detection_enabled": true,
    --   "federation_enabled": false
    -- }

    -- Embedding geometry (ADR-0046 / migration 000013; deployment profile, not per-request)
    embedding_profile             TEXT NOT NULL DEFAULT 'cpu'
                                  CHECK (embedding_profile IN ('cpu', 'gpu', 'hosted')),
    embedding_dim                 INTEGER NOT NULL DEFAULT 384
                                  CHECK (embedding_dim > 0),
    embedding_model_id            TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2'
                                  CHECK (length(trim(embedding_model_id)) > 0),

    -- Metadata
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,  -- Soft delete

    CONSTRAINT organizations_slug_format
        CHECK (slug ~ '^[a-z0-9-]+$')
);

-- Indexes
CREATE INDEX idx_organizations_slug
    ON ibex_core.organizations(slug)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_organizations_stripe
    ON ibex_core.organizations(stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

-- RLS
ALTER TABLE ibex_core.organizations ENABLE ROW LEVEL SECURITY;

CREATE POLICY organizations_isolation ON ibex_core.organizations
    USING (
        id = current_setting('app.current_org_id', true)::UUID
        OR current_setting('app.is_service_account', true)::BOOLEAN = true
    );

-- Trigger: auto-update updated_at
CREATE TRIGGER organizations_updated_at
    BEFORE UPDATE ON ibex_core.organizations
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();

-- ================================================================
-- USERS
-- Human users who manage agents via dashboard/API
-- ================================================================
CREATE TABLE ibex_core.users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    email           TEXT NOT NULL,
    name            TEXT NOT NULL,
    avatar_url      TEXT,

    -- Role within organization
    role            TEXT NOT NULL DEFAULT 'member'
                    CHECK (role IN ('owner', 'admin',
                                    'member', 'viewer')),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'invited',
                                      'suspended', 'deactivated')),

    -- Authentication
    password_hash   TEXT,           -- NULL if SSO-only
    mfa_secret      TEXT,           -- TOTP secret (encrypted)
    mfa_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_backup_codes TEXT[],        -- Hashed backup codes

    -- SSO
    sso_provider    TEXT,           -- 'keycloak', 'okta', etc.
    sso_subject     TEXT,           -- External identity ID

    -- Session management
    last_login_at   TIMESTAMPTZ,
    last_login_ip   INET,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,

    -- Preferences
    preferences     JSONB NOT NULL DEFAULT '{}',
    -- preferences schema:
    -- {
    --   "theme": "dark",
    --   "timezone": "UTC",
    --   "notifications": {"email": true, "slack": false}
    -- }

    -- Metadata
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,

    UNIQUE(org_id, email),
    -- Applied in migration 000012 (composite token subject FKs):
    UNIQUE (id, org_id),  -- users_id_org_unique; required for tokens (user_id, org_id)
    CONSTRAINT users_email_format
        CHECK (email ~ '^[^@]+@[^@]+\.[^@]+$')
);

-- Indexes
CREATE INDEX idx_users_org_id
    ON ibex_core.users(org_id)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_users_email
    ON ibex_core.users(email)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_users_sso
    ON ibex_core.users(sso_provider, sso_subject)
    WHERE sso_provider IS NOT NULL;

-- RLS
ALTER TABLE ibex_core.users ENABLE ROW LEVEL SECURITY;

CREATE POLICY users_isolation ON ibex_core.users
    USING (
        org_id = current_setting('app.current_org_id', true)::UUID
        OR id = current_setting('app.current_user_id', true)::UUID
        OR current_setting('app.is_service_account', true)::BOOLEAN = true
    );
```

---

#### Agents and Directives

```sql
-- ================================================================
-- AGENTS
-- AI agents that use IBEX Harness for memory and context
-- ================================================================
CREATE TABLE ibex_core.agents (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL
                            REFERENCES ibex_core.organizations(id)
                            ON DELETE RESTRICT,
    created_by              UUID
                            REFERENCES ibex_core.users(id)
                            ON DELETE SET NULL,

    -- Identity
    name                    TEXT NOT NULL,
    description             TEXT,
    slug                    TEXT NOT NULL,

    -- Current directive
    active_directive_version_id UUID,
    -- FK added after directive_versions table created

    -- Configuration
    config                  JSONB NOT NULL DEFAULT '{}',
    -- config schema:
    -- {
    --   "memory_extraction_enabled": true,
    --   "drift_detection_enabled": true,
    --   "drift_sensitivity": 2.0,
    --   "context_budget_tokens": 4000,
    --   "max_memories_per_context": 20,
    --   "memory_scope": "agent",  -- or "org", "session"
    --   "llm_providers": ["openai", "anthropic"],
    --   "loop_detection_threshold": 5,
    --   "heartbeat_interval_seconds": 10
    -- }

    -- Status
    status                  TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'paused',
                                              'suspended', 'archived')),

    -- Statistics (denormalized for performance)
    total_sessions          INTEGER NOT NULL DEFAULT 0,
    total_memories          INTEGER NOT NULL DEFAULT 0,
    total_tokens_used       BIGINT NOT NULL DEFAULT 0,
    last_active_at          TIMESTAMPTZ,

    -- Metadata
    tags                    TEXT[] NOT NULL DEFAULT '{}',
    metadata                JSONB NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at              TIMESTAMPTZ,

    UNIQUE(org_id, slug),
    -- Applied in migration 000009 (directive/session composite FKs; tokens reuse in 000012):
    UNIQUE (id, org_id),  -- agents_id_org_unique; required for tokens (agent_id, org_id)
    CONSTRAINT agents_slug_format
        CHECK (slug ~ '^[a-z0-9-]+$')
);

-- Indexes
CREATE INDEX idx_agents_org_id
    ON ibex_core.agents(org_id)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_agents_status
    ON ibex_core.agents(org_id, status)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_agents_tags
    ON ibex_core.agents USING gin(tags)
    WHERE deleted_at IS NULL;

-- RLS
ALTER TABLE ibex_core.agents ENABLE ROW LEVEL SECURITY;

CREATE POLICY agents_isolation ON ibex_core.agents
    USING (
        org_id = current_setting('app.current_org_id', true)::UUID
        OR current_setting('app.is_service_account', true)::BOOLEAN = true
    );

-- ================================================================
-- DIRECTIVES
-- Named containers for directive versions (like a Git repository)
-- ================================================================
CREATE TABLE ibex_core.directives (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    created_by      UUID
                    REFERENCES ibex_core.users(id)
                    ON DELETE SET NULL,

    -- Identity
    name            TEXT NOT NULL,
    description     TEXT,

    -- Marketplace
    is_published    BOOLEAN NOT NULL DEFAULT FALSE,
    marketplace_id  TEXT UNIQUE,  -- External marketplace identifier

    -- Statistics
    total_versions  INTEGER NOT NULL DEFAULT 0,
    total_installs  INTEGER NOT NULL DEFAULT 0,

    -- Metadata
    tags            TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,

    UNIQUE(org_id, name)
);

-- Indexes
CREATE INDEX idx_directives_org_id
    ON ibex_core.directives(org_id)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_directives_marketplace
    ON ibex_core.directives(is_published)
    WHERE is_published = TRUE AND deleted_at IS NULL;

-- RLS
ALTER TABLE ibex_core.directives ENABLE ROW LEVEL SECURITY;

CREATE POLICY directives_isolation ON ibex_core.directives
    USING (
        org_id = current_setting('app.current_org_id', true)::UUID
        OR (is_published = TRUE)
        OR current_setting('app.is_service_account', true)::BOOLEAN = true
    );

-- ================================================================
-- DIRECTIVE VERSIONS
-- Immutable content of each directive version (Git commits)
-- ================================================================
CREATE TABLE ibex_core.directive_versions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    directive_id        UUID NOT NULL
                        REFERENCES ibex_core.directives(id)
                        ON DELETE RESTRICT,
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE RESTRICT,
    created_by          UUID
                        REFERENCES ibex_core.users(id)
                        ON DELETE SET NULL,

    -- Version information
    version_number      INTEGER NOT NULL,
    parent_version_id   UUID
                        REFERENCES ibex_core.directive_versions(id)
                        ON DELETE RESTRICT,

    -- Content (immutable after creation)
    content             TEXT NOT NULL,
    content_hash        TEXT NOT NULL,  -- SHA-256 for integrity
    content_tokens      INTEGER NOT NULL, -- Pre-computed token count

    -- Status lifecycle: draft → review → active → deprecated/revoked
    status              TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'review',
                                          'active', 'deprecated',
                                          'revoked')),

    -- Review and approval
    review_requested_at TIMESTAMPTZ,
    review_approved_at  TIMESTAMPTZ,
    review_approved_by  UUID REFERENCES ibex_core.users(id),
    review_notes        TEXT,

    -- Regression testing
    regression_test_status TEXT
                        CHECK (regression_test_status IN (
                            'pending', 'running', 'passed',
                            'failed', 'skipped'
                        )),
    regression_test_results JSONB,
    -- {
    --   "total_scenarios": 50,
    --   "passed": 48,
    --   "failed": 2,
    --   "failure_details": [...]
    -- }

    -- Promotion
    activated_at        TIMESTAMPTZ,
    activated_by        UUID REFERENCES ibex_core.users(id),
    deprecated_at       TIMESTAMPTZ,
    revoked_at          TIMESTAMPTZ,
    revoked_by          UUID REFERENCES ibex_core.users(id),
    revoke_reason       TEXT,

    -- Change notes
    change_summary      TEXT,
    breaking_changes    BOOLEAN NOT NULL DEFAULT FALSE,

    -- Metadata
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(directive_id, version_number),
    -- Only one active version per directive
    UNIQUE NULLS NOT DISTINCT (directive_id, status)
        WHERE status = 'active'
);

-- Indexes
CREATE INDEX idx_directive_versions_directive_id
    ON ibex_core.directive_versions(directive_id);

CREATE INDEX idx_directive_versions_status
    ON ibex_core.directive_versions(directive_id, status);

CREATE INDEX idx_directive_versions_org_active
    ON ibex_core.directive_versions(org_id)
    WHERE status = 'active';

-- RLS
ALTER TABLE ibex_core.directive_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY directive_versions_isolation
    ON ibex_core.directive_versions
    USING (
        org_id = current_setting('app.current_org_id', true)::UUID
        OR current_setting('app.is_service_account', true)::BOOLEAN = true
    );

-- Add FK from agents to directive_versions
ALTER TABLE ibex_core.agents
    ADD CONSTRAINT agents_active_directive_version_fk
    FOREIGN KEY (active_directive_version_id)
    REFERENCES ibex_core.directive_versions(id)
    ON DELETE RESTRICT;

-- ================================================================
-- DIRECTIVE SCENARIOS
-- Behavioral test scenarios for regression testing
-- ================================================================
CREATE TABLE ibex_core.directive_scenarios (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    directive_id    UUID NOT NULL
                    REFERENCES ibex_core.directives(id)
                    ON DELETE CASCADE,
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    created_by      UUID
                    REFERENCES ibex_core.users(id)
                    ON DELETE SET NULL,

    -- Scenario definition
    name            TEXT NOT NULL,
    description     TEXT,
    input_messages  JSONB NOT NULL,
    -- [{"role": "user", "content": "..."}]
    expected_behavior TEXT NOT NULL,
    -- Natural language description of expected behavior
    -- Used by LLM judge for evaluation

    -- Classification
    category        TEXT,  -- e.g., "safety", "capability", "format"
    is_critical     BOOLEAN NOT NULL DEFAULT FALSE,
    -- Critical scenarios: failure blocks promotion

    -- Metadata
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

-- Indexes
CREATE INDEX idx_directive_scenarios_directive_id
    ON ibex_core.directive_scenarios(directive_id)
    WHERE deleted_at IS NULL;
```

---

#### Memory System

> **Shipped (2.5.G5.M1 / ADR-0047):** foundation `ibex_core.memories` via
> `000014_create_memories_temporal` — tenancy, content, scalar category/status,
> and bi-temporal columns (`valid_from` / `valid_until` / `observed_at`).
> **Shipped (2.5.G5.M2 / ADR-0048):** `ibex_core.memory_labels` multi-label join
> table with per-label confidence; `memories.category` synced as primary when
> labels exist.
> **Shipped (2.5.G5.M3 / ADR-0049):** `ibex_core.memory_relationships` typed
> edges with dual composite FKs, FORCE RLS, bidirectional traversal indexes,
> `memory_supersession_edges` view, and `resolve_supersession_tip`.
> **Shipped (3.1.1 / ADR-0052):** expand `memories` with `embedding vector(1024)`,
> `embedding_model` / `embedding_dim`, quality columns, generated `search_vector`,
> HNSW + validity + GIN indexes (`000017_memory_schema_v2_expand`). Physical rename
> `category` → `primary_category` deferred.

```sql
-- ================================================================
-- MEMORIES (foundation — migration 000014 / ADR-0047)
-- Temporal validity included; embedding columns deferred to 3.1.1
-- ================================================================
CREATE TABLE ibex_core.memories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    agent_id        UUID NOT NULL,
    session_id      UUID,
    created_by_user UUID
                    REFERENCES ibex_core.users(id)
                    ON DELETE SET NULL,

    -- Content
    content         TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    -- SHA-256 of normalized content (exact dedup; app-enforced format)
    content_tokens  INTEGER NOT NULL,
    -- Pre-computed for budget management

    -- Classification (scalar primary; multi-label in memory_labels / ADR-0048.
    -- When labels exist, category is synced to highest-confidence label.)
    category        TEXT NOT NULL DEFAULT 'factual'
                    CHECK (category IN (
                        'factual',
                        'preference',
                        'behavioral',
                        'episodic',
                        'procedural'
                    )),

    -- Lifecycle
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN (
                        'active',
                        'superseded',
                        'merged_into',
                        'archived',
                        'quarantined',
                        'deleted'
                    )),
    deleted_at      TIMESTAMPTZ,

    -- Temporal validity (half-open [valid_from, valid_until);
    -- NULL valid_until = still open). observed_at = when IBEX learned the fact.
    valid_from      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until     TIMESTAMPTZ,
    observed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (id, org_id),
    CONSTRAINT memories_agent_org_fk
        FOREIGN KEY (agent_id, org_id)
        REFERENCES ibex_core.agents (id, org_id)
        ON DELETE CASCADE,
    CONSTRAINT memories_session_org_fk
        FOREIGN KEY (session_id, org_id)
        REFERENCES ibex_core.sessions (id, org_id),
    CONSTRAINT memories_content_not_empty CHECK (length(content) > 0),
    CONSTRAINT memories_content_max CHECK (octet_length(content) <= 10000),
    CONSTRAINT memories_content_hash_not_empty CHECK (length(content_hash) > 0),
    CONSTRAINT memories_content_tokens_nonneg CHECK (content_tokens >= 0),
    CONSTRAINT memories_valid_interval_chk
        CHECK (valid_until IS NULL OR valid_until > valid_from)
);

-- Operational indexes (temporal GiST / range indexes deferred until query patterns exist)
CREATE INDEX idx_memories_agent_active
    ON ibex_core.memories(org_id, agent_id)
    WHERE status = 'active' AND deleted_at IS NULL;

CREATE INDEX idx_memories_content_hash
    ON ibex_core.memories(org_id, agent_id, content_hash);

CREATE INDEX idx_memories_session_id
    ON ibex_core.memories(org_id, session_id)
    WHERE session_id IS NOT NULL;

ALTER TABLE ibex_core.memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.memories FORCE ROW LEVEL SECURITY;

CREATE POLICY memories_isolation ON ibex_core.memories
    USING (ibex_core.rls_org_visible(org_id));

-- ================================================================
-- MEMORY LABELS (migration 000015 / ADR-0048)
-- Multi-label taxonomy; category on memories is primary when labels exist
-- ================================================================
CREATE TABLE ibex_core.memory_labels (
    memory_id   UUID NOT NULL,
    org_id      UUID NOT NULL
                REFERENCES ibex_core.organizations(id)
                ON DELETE RESTRICT,
    label       TEXT NOT NULL
                CHECK (label IN (
                    'factual',
                    'preference',
                    'behavioral',
                    'episodic',
                    'procedural'
                )),
    confidence  NUMERIC(3,2) NOT NULL DEFAULT 1.00
                CHECK (confidence >= 0 AND confidence <= 1),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (memory_id, label),
    CONSTRAINT memory_labels_memory_org_fk
        FOREIGN KEY (memory_id, org_id)
        REFERENCES ibex_core.memories (id, org_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_memory_labels_org_label
    ON ibex_core.memory_labels (org_id, label);

ALTER TABLE ibex_core.memory_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.memory_labels FORCE ROW LEVEL SECURITY;

CREATE POLICY memory_labels_isolation ON ibex_core.memory_labels
    USING (ibex_core.rls_org_visible(org_id));

-- Trigger sync_memory_primary_category: WHEN labels remain, set
-- memories.category = ORDER BY confidence DESC, label ASC LIMIT 1.
-- When zero labels remain, leave category unchanged.
-- (Logical name = primary category; physical rename deferred — ADR-0052.)

-- ================================================================
-- MEMORIES EXPAND (migration 000017 / ADR-0052) — additive only
-- Do not greenfield-CREATE memories, memory_labels, or memory_relationships.
-- ================================================================
-- Columns added on ibex_core.memories:
--   embedding vector(1024) NULL,
--   embedding_model TEXT NULL
--     CHECK NULL or char_length <= 256 (memories_embedding_model_len_chk),
--   embedding_dim INTEGER NULL,
--   CHECK memories_embedding_triplet_chk (all NULL or embedding+model+dim=1024),
--   confidence NUMERIC(3,2) NOT NULL DEFAULT 0.80,
--   usefulness_score NUMERIC(3,2) NOT NULL DEFAULT 0.50,
--   source TEXT NOT NULL DEFAULT 'extracted'
--     CHECK IN ('extracted','user_provided','imported','inferred'),
--   superseded_by UUID, merged_into UUID
--     (composite FKs to memories(id, org_id)),
--   retrieval_count INTEGER NOT NULL DEFAULT 0,
--   last_retrieved_at TIMESTAMPTZ,
--   pii_detected / pii_redacted BOOLEAN NOT NULL DEFAULT FALSE,
--   metadata JSONB NOT NULL DEFAULT '{}'
--     CHECK jsonb_typeof = 'object' AND octet_length(text) <= 8192,
--   search_vector tsvector GENERATED ALWAYS AS
--     (setweight(to_tsvector('english', coalesce(content,'')), 'A')) STORED
--
-- Indexes:
--   idx_memories_embedding_hnsw USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64)
--     WHERE status = 'active' AND deleted_at IS NULL
--   idx_memories_validity (org_id, agent_id, valid_from, valid_until)
--     WHERE status = 'active' AND deleted_at IS NULL
--   idx_memories_search_vector USING GIN (search_vector)
--     WHERE status = 'active' AND deleted_at IS NULL

-- ================================================================
-- MEMORY RELATIONSHIPS (migration 000016 / ADR-0049)
-- Typed edges; supersedes means source replaces target
-- ================================================================
CREATE TABLE ibex_core.memory_relationships (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE RESTRICT,
    source_memory_id    UUID NOT NULL,
    target_memory_id    UUID NOT NULL,
    relationship_type   TEXT NOT NULL
                        CHECK (relationship_type IN (
                            'supersedes',    -- source replaces target
                            'contradicts',   -- source contradicts target
                            'specializes',   -- source is more specific
                            'generalizes',   -- source is more general
                            'merged_from',   -- source merged from target
                            'derived_from'   -- source derived from target
                        )),
    confidence          NUMERIC(3,2) NOT NULL DEFAULT 0.90
                        CHECK (confidence >= 0 AND confidence <= 1),
    resolution_notes    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (source_memory_id, target_memory_id, relationship_type),
    CONSTRAINT memory_relationships_no_self_loop_chk
        CHECK (source_memory_id <> target_memory_id),
    CONSTRAINT memory_relationships_source_org_fk
        FOREIGN KEY (source_memory_id, org_id)
        REFERENCES ibex_core.memories (id, org_id)
        ON DELETE CASCADE,
    CONSTRAINT memory_relationships_target_org_fk
        FOREIGN KEY (target_memory_id, org_id)
        REFERENCES ibex_core.memories (id, org_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_memory_relationships_org_source_type
    ON ibex_core.memory_relationships (org_id, source_memory_id, relationship_type);
CREATE INDEX idx_memory_relationships_org_target_type
    ON ibex_core.memory_relationships (org_id, target_memory_id, relationship_type);

ALTER TABLE ibex_core.memory_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.memory_relationships FORCE ROW LEVEL SECURITY;

CREATE POLICY memory_relationships_isolation ON ibex_core.memory_relationships
    USING (ibex_core.rls_org_visible(org_id));

-- View memory_supersession_edges: supersedes-only projection (security_invoker).
-- Function resolve_supersession_tip(org_id, memory_id, max_depth DEFAULT 5):
-- walk incoming supersedes to current tip with depth + cycle guards.

-- ================================================================
-- MEMORY VERSIONS
-- Append-only history of memory changes
-- (Never updated, only new rows inserted)
-- ================================================================
CREATE TABLE ibex_core.memory_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id       UUID NOT NULL
                    REFERENCES ibex_core.memories(id)
                    ON DELETE CASCADE,
    org_id          UUID NOT NULL,
    version_number  INTEGER NOT NULL,
    operation       TEXT NOT NULL
                    CHECK (operation IN (
                        'created', 'updated', 'status_changed',
                        'confidence_updated', 'merged', 'deleted'
                    )),
    previous_content    TEXT,
    new_content         TEXT,
    previous_status     TEXT,
    new_status          TEXT,
    change_reason       TEXT,
    changed_by          UUID REFERENCES ibex_core.users(id),
    changed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(memory_id, version_number)
)
PARTITION BY RANGE (changed_at);

-- Monthly partitions
CREATE TABLE ibex_core.memory_versions_2024_01
    PARTITION OF ibex_core.memory_versions
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
-- Additional partitions created monthly by migration scripts

CREATE INDEX idx_memory_versions_memory_id
    ON ibex_core.memory_versions(memory_id);
```

---

#### Session Management

> **Milestone 2.4.1:** `ibex_core.sessions` and `ibex_core.checkpoints` are applied as the Phase-2 subset (`000010`; see [ADR-0032](../content/docs/adr/0032-session-data-model.mdx)): hashes/metadata, soft delete, append-only checkpoints, FORCE RLS. Heartbeat, loop detection, and other fuller columns documented below are not yet migrated.

```sql
-- ================================================================
-- SESSIONS
-- Tracks agent execution sessions with full lifecycle
-- ================================================================
CREATE TABLE ibex_core.sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Using UUID v7 (time-ordered) for:
    -- 1. Chronological sorting by ID
    -- 2. Better index performance than random UUID
    -- 3. No need for separate created_at index in most queries

    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    agent_id        UUID NOT NULL
                    REFERENCES ibex_core.agents(id)
                    ON DELETE RESTRICT,
    user_id         UUID
                    REFERENCES ibex_core.users(id)
                    ON DELETE SET NULL,
    directive_version_id UUID
                    REFERENCES ibex_core.directive_versions(id)
                    ON DELETE RESTRICT,

    -- Status state machine:
    -- initializing → active → suspended → resuming → completed
    --                       → failed
    --                       → abandoned (suspended > 30 days)
    status          TEXT NOT NULL DEFAULT 'initializing'
                    CHECK (status IN (
                        'initializing', 'active', 'suspended',
                        'resuming', 'completed', 'failed', 'abandoned'
                    )),

    -- Timing
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_heartbeat_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    suspended_at        TIMESTAMPTZ,

    -- Checkpoint tracking
    checkpoint_sequence INTEGER NOT NULL DEFAULT 0,
    last_checkpoint_at  TIMESTAMPTZ,

    -- Loop detection
    loop_detection_fingerprints JSONB NOT NULL DEFAULT '[]',
    -- Last 20 tool call semantic fingerprints
    loop_suspected      BOOLEAN NOT NULL DEFAULT FALSE,
    loop_suspected_at   TIMESTAMPTZ,

    -- Behavioral tracking
    total_turns         INTEGER NOT NULL DEFAULT 0,
    total_tokens_used   BIGINT NOT NULL DEFAULT 0,
    total_memories_read INTEGER NOT NULL DEFAULT 0,
    total_memories_written INTEGER NOT NULL DEFAULT 0,
    total_tool_calls    INTEGER NOT NULL DEFAULT 0,
    error_count         INTEGER NOT NULL DEFAULT 0,

    -- Recovery information
    recovery_attempts   INTEGER NOT NULL DEFAULT 0,
    last_error          TEXT,
    last_error_at       TIMESTAMPTZ,

    -- Session metadata
    client_sdk_version  TEXT,
    client_language     TEXT,
    environment         TEXT,  -- 'development', 'staging', 'production'
    tags                TEXT[] NOT NULL DEFAULT '{}',
    metadata            JSONB NOT NULL DEFAULT '{}'
);

-- Indexes
CREATE INDEX idx_sessions_agent_id
    ON ibex_core.sessions(org_id, agent_id);

CREATE INDEX idx_sessions_status
    ON ibex_core.sessions(org_id, status)
    WHERE status IN ('active', 'suspended', 'resuming');

CREATE INDEX idx_sessions_heartbeat
    ON ibex_core.sessions(last_heartbeat_at)
    WHERE status = 'active';
-- Used by: heartbeat monitor to find stale sessions

CREATE INDEX idx_sessions_recent
    ON ibex_core.sessions(org_id, agent_id, started_at DESC);

-- RLS
ALTER TABLE ibex_core.sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY sessions_isolation ON ibex_core.sessions
    USING (
        org_id = current_setting('app.current_org_id', true)::UUID
        OR current_setting('app.is_service_account', true)::BOOLEAN = true
    );

-- Add FK from memories to sessions
ALTER TABLE ibex_core.memories
    ADD CONSTRAINT memories_session_id_fk
    FOREIGN KEY (session_id)
    REFERENCES ibex_core.sessions(id)
    ON DELETE SET NULL;

-- ================================================================
-- CHECKPOINTS
-- Immutable session state snapshots for crash recovery
-- ================================================================
CREATE TABLE ibex_core.checkpoints (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL
                        REFERENCES ibex_core.sessions(id)
                        ON DELETE CASCADE,
    org_id              UUID NOT NULL,
    sequence_number     INTEGER NOT NULL,

    -- State (compressed JSONB)
    state               JSONB NOT NULL,
    -- {
    --   "conversation": [...],      -- Message history
    --   "pending_memories": [...],  -- Writes not yet confirmed
    --   "completed_tools": [...],   -- Completed tool calls
    --   "plan_state": {...},        -- Agent plan tree
    --   "context_snapshot": "...",  -- Last assembled context
    --   "variables": {...}          -- Agent variables
    -- }
    state_hash          TEXT NOT NULL,
    -- SHA-256 of state for integrity verification
    state_size_bytes    INTEGER NOT NULL,
    is_compressed       BOOLEAN NOT NULL DEFAULT TRUE,

    -- Validity
    is_valid            BOOLEAN NOT NULL DEFAULT TRUE,
    validation_error    TEXT,

    -- Timing
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(session_id, sequence_number)
);

-- Indexes
CREATE INDEX idx_checkpoints_session_id
    ON ibex_core.checkpoints(session_id, sequence_number DESC)
    WHERE is_valid = TRUE;

-- Partial index: find latest valid checkpoint efficiently
CREATE INDEX idx_checkpoints_latest_valid
    ON ibex_core.checkpoints(session_id, sequence_number DESC)
    WHERE is_valid = TRUE;

-- ================================================================
-- SESSION EVENTS
-- Append-only event log for session replay
-- ================================================================
CREATE TABLE ibex_core.session_events (
    id              BIGSERIAL,
    -- Use BIGSERIAL for performance (sequential, no UUID overhead)
    session_id      UUID NOT NULL
                    REFERENCES ibex_core.sessions(id)
                    ON DELETE CASCADE,
    org_id          UUID NOT NULL,
    sequence_number INTEGER NOT NULL,

    event_type      TEXT NOT NULL
                    CHECK (event_type IN (
                        'session_started',
                        'session_completed',
                        'session_failed',
                        'session_suspended',
                        'session_resumed',
                        'checkpoint_created',
                        'inference_request',
                        'inference_response',
                        'memory_read',
                        'memory_written',
                        'tool_called',
                        'tool_completed',
                        'tool_failed',
                        'directive_updated',
                        'loop_detected',
                        'error_occurred'
                    )),

    -- Event data
    data            JSONB NOT NULL,
    -- Varies by event_type:
    -- inference_request: {messages, model, context_tokens}
    -- memory_read: {memory_ids, query, scores}
    -- tool_called: {tool_name, args, idempotency_key}

    -- Archival location
    archived_to     TEXT,
    -- S3/MinIO key after archival

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id),
    UNIQUE(session_id, sequence_number)
)
PARTITION BY RANGE (created_at);

-- Monthly partitions
CREATE TABLE ibex_core.session_events_2024_01
    PARTITION OF ibex_core.session_events
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

CREATE INDEX idx_session_events_session_id
    ON ibex_core.session_events(session_id, sequence_number);
```

---

#### Authentication and Tokens

```sql
-- ================================================================
-- TOKENS
-- All authentication tokens (PAT, Org, Service, Marketplace)
-- Session tokens are JWTs stored client-side, not in DB
-- ================================================================
CREATE TABLE ibex_core.tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE CASCADE,
    user_id         UUID,
    -- Composite tenant FK (000012): FOREIGN KEY (user_id, org_id)
    -- REFERENCES ibex_core.users (id, org_id) ON DELETE CASCADE
    agent_id        UUID,
    -- Composite tenant FK (000012): FOREIGN KEY (agent_id, org_id)
    -- REFERENCES ibex_core.agents (id, org_id) ON DELETE CASCADE

    -- Token classification
    type            TEXT NOT NULL
                    CHECK (type IN (
                        'pat',          -- Personal Access Token
                        'org_token',    -- Organization-scoped token
                        'service_token',-- Internal service-to-service
                        'marketplace'   -- Third-party publishers
                    )),

    -- Stored hash (never store plaintext)
    hash            TEXT NOT NULL UNIQUE,
    -- Argon2id hash of the actual token value

    -- Token prefix for display (first 8 chars of token, safe to show)
    prefix          TEXT NOT NULL,
    -- Example: "ibex_pat_" prefix shown in UI for identification

    -- Description
    name            TEXT NOT NULL,
    description     TEXT,

    -- Permissions (64-bit bitmap)
    permissions     BIGINT NOT NULL,

    -- Validity
    expires_at      TIMESTAMPTZ,
    -- NULL means non-expiring (PATs)

    -- Revocation
    is_revoked      BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at      TIMESTAMPTZ,
    revoked_by      UUID REFERENCES ibex_core.users(id),
    revoke_reason   TEXT,

    -- Usage tracking
    last_used_at    TIMESTAMPTZ,
    last_used_ip    INET,
    use_count       BIGINT NOT NULL DEFAULT 0,

    -- IP restriction (enterprise feature)
    allowed_ips     INET[],

    -- Metadata
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_tokens_org_id
    ON ibex_core.tokens(org_id)
    WHERE is_revoked = FALSE;

CREATE INDEX idx_tokens_user_id
    ON ibex_core.tokens(user_id)
    WHERE user_id IS NOT NULL AND is_revoked = FALSE;

CREATE INDEX idx_tokens_hash
    ON ibex_core.tokens(hash);
-- Most critical index: called on every request

-- RLS
ALTER TABLE ibex_core.tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY tokens_isolation ON ibex_core.tokens
    USING (
        org_id = current_setting('app.current_org_id', true)::UUID
        OR current_setting('app.is_service_account', true)::BOOLEAN = true
    );

-- ================================================================
-- MFA CHALLENGES
-- Temporary MFA verification challenges
-- ================================================================
CREATE TABLE ibex_core.mfa_challenges (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL
                REFERENCES ibex_core.users(id)
                ON DELETE CASCADE,
    operation   TEXT NOT NULL,
    -- What operation requires MFA verification

    -- Challenge state
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at TIMESTAMPTZ,
    attempts    INTEGER NOT NULL DEFAULT 0,

    -- Expiry
    expires_at  TIMESTAMPTZ NOT NULL
                DEFAULT NOW() + INTERVAL '5 minutes',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_mfa_challenges_user_id
    ON ibex_core.mfa_challenges(user_id)
    WHERE is_verified = FALSE
    AND expires_at > NOW();
```

---

#### Behavioral Fingerprinting

```sql
-- ================================================================
-- BEHAVIORAL FINGERPRINTS
-- Statistical snapshots of agent behavior
-- ================================================================
CREATE TABLE ibex_core.behavioral_fingerprints (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    agent_id        UUID NOT NULL
                    REFERENCES ibex_core.agents(id)
                    ON DELETE CASCADE,

    -- Computation window
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,
    trace_count         INTEGER NOT NULL,
    -- How many traces this fingerprint is based on

    -- Token usage features
    avg_prompt_tokens   NUMERIC(10,2) NOT NULL,
    std_prompt_tokens   NUMERIC(10,2) NOT NULL,
    avg_completion_tokens NUMERIC(10,2) NOT NULL,
    std_completion_tokens NUMERIC(10,2) NOT NULL,
    p95_total_tokens    NUMERIC(10,2) NOT NULL,

    -- Response characteristics
    avg_response_length NUMERIC(10,2) NOT NULL,
    avg_sentence_count  NUMERIC(10,2) NOT NULL,
    avg_response_time_ms NUMERIC(10,2) NOT NULL,

    -- Tool usage
    tool_call_rate      NUMERIC(5,4) NOT NULL,
    -- Fraction of calls that include tool usage
    unique_tools_used   INTEGER NOT NULL,
    tool_distribution   JSONB NOT NULL DEFAULT '{}',
    -- {"tool_name": 0.35, "other_tool": 0.65}

    -- Error rates
    error_rate          NUMERIC(5,4) NOT NULL,
    timeout_rate        NUMERIC(5,4) NOT NULL,

    -- Memory access patterns
    avg_memories_retrieved  NUMERIC(5,2) NOT NULL,
    memory_hit_rate         NUMERIC(5,4) NOT NULL,
    -- Fraction of retrievals that return results

    -- Semantic features (embedding centroid of responses)
    response_embedding_centroid vector(384),

    -- Baseline tracking
    is_baseline         BOOLEAN NOT NULL DEFAULT FALSE,
    -- The fingerprint used as the comparison baseline

    -- Computed drift from baseline (null if this IS baseline)
    drift_from_baseline JSONB,
    -- {
    --   "severity": "low|medium|high",
    --   "alerts": [
    --     {
    --       "feature": "tool_call_rate",
    --       "z_score": 3.2,
    --       "baseline_value": 0.4,
    --       "current_value": 0.8
    --     }
    --   ]
    -- }

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_behavioral_fingerprints_agent_id
    ON ibex_core.behavioral_fingerprints(org_id, agent_id,
                                          computed_at DESC);

CREATE INDEX idx_behavioral_fingerprints_baseline
    ON ibex_core.behavioral_fingerprints(agent_id)
    WHERE is_baseline = TRUE;

-- ================================================================
-- DRIFT ALERTS
-- Generated when behavioral drift exceeds thresholds
-- ================================================================
CREATE TABLE ibex_core.drift_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    agent_id        UUID NOT NULL
                    REFERENCES ibex_core.agents(id)
                    ON DELETE CASCADE,
    fingerprint_id  UUID NOT NULL
                    REFERENCES ibex_core.behavioral_fingerprints(id)
                    ON DELETE CASCADE,

    severity        TEXT NOT NULL
                    CHECK (severity IN ('low', 'medium', 'high')),

    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN (
                        'open',           -- Not yet reviewed
                        'acknowledged',   -- User has seen it
                        'resolved',       -- User resolved it
                        'false_positive'  -- Marked as not a real issue
                    )),

    -- Alert details
    alerts          JSONB NOT NULL,
    -- Array of individual feature drift alerts

    -- Resolution
    resolved_at     TIMESTAMPTZ,
    resolved_by     UUID REFERENCES ibex_core.users(id),
    resolution_notes TEXT,

    -- Notifications
    notification_sent_at TIMESTAMPTZ,
    notification_channels TEXT[],

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_drift_alerts_agent_id
    ON ibex_core.drift_alerts(org_id, agent_id, created_at DESC);

CREATE INDEX idx_drift_alerts_open
    ON ibex_core.drift_alerts(org_id, status)
    WHERE status = 'open';

-- RLS
ALTER TABLE ibex_core.drift_alerts ENABLE ROW LEVEL SECURITY;
CREATE POLICY drift_alerts_isolation ON ibex_core.drift_alerts
    USING (
        org_id = current_setting('app.current_org_id', true)::UUID
        OR current_setting('app.is_service_account', true)::BOOLEAN = true
    );
```

---

#### Billing and Usage

```sql
-- ================================================================
-- USAGE COUNTERS
-- Real-time usage tracking (Redis is source, this is persistence)
-- ================================================================
CREATE TABLE ibex_billing.usage_counters (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE CASCADE,

    -- Billing period
    period_year     SMALLINT NOT NULL,
    period_month    SMALLINT NOT NULL
                    CHECK (period_month BETWEEN 1 AND 12),

    -- Counters (updated atomically)
    tokens_used         BIGINT NOT NULL DEFAULT 0,
    memory_writes       BIGINT NOT NULL DEFAULT 0,
    memory_reads        BIGINT NOT NULL DEFAULT 0,
    embeddings_generated BIGINT NOT NULL DEFAULT 0,
    sessions_created    INTEGER NOT NULL DEFAULT 0,
    api_calls           BIGINT NOT NULL DEFAULT 0,

    -- Quota at time of period start
    token_quota         BIGINT NOT NULL,
    memory_quota        BIGINT NOT NULL,

    -- Billing status
    invoice_id          TEXT,
    invoiced_at         TIMESTAMPTZ,
    invoice_amount_cents INTEGER,

    last_updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(org_id, period_year, period_month)
);

CREATE INDEX idx_usage_counters_org_period
    ON ibex_billing.usage_counters(org_id, period_year, period_month);

-- RLS
ALTER TABLE ibex_billing.usage_counters ENABLE ROW LEVEL SECURITY;
CREATE POLICY usage_counters_isolation ON ibex_billing.usage_counters
    USING (
        org_id = current_setting('app.current_org_id', true)::UUID
        OR current_setting('app.is_service_account', true)::BOOLEAN = true
    );

-- ================================================================
-- TIER LIMITS
-- Configuration for what each tier allows
-- ================================================================
CREATE TABLE ibex_billing.tier_limits (
    tier                TEXT PRIMARY KEY
                        CHECK (tier IN ('free', 'pro', 'enterprise')),

    -- Token limits
    monthly_tokens      BIGINT NOT NULL,

    -- Memory limits
    max_memories        BIGINT NOT NULL,
    max_agents          INTEGER NOT NULL,
    max_sessions_per_day INTEGER NOT NULL,

    -- Feature flags
    drift_detection_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    behavioral_fingerprinting   BOOLEAN NOT NULL DEFAULT FALSE,
    directive_versioning        BOOLEAN NOT NULL DEFAULT FALSE,
    marketplace_access          BOOLEAN NOT NULL DEFAULT FALSE,
    federation_enabled          BOOLEAN NOT NULL DEFAULT FALSE,
    sso_enabled                 BOOLEAN NOT NULL DEFAULT FALSE,
    audit_log_retention_days    INTEGER NOT NULL DEFAULT 7,

    -- Rate limits
    requests_per_minute         INTEGER NOT NULL,
    requests_per_day            INTEGER NOT NULL,

    -- Support
    support_level   TEXT NOT NULL
                    CHECK (support_level IN (
                        'community', 'email', 'priority', 'dedicated'
                    )),

    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert default tier limits
INSERT INTO ibex_billing.tier_limits VALUES
(
    'free',
    1000000,        -- 1M tokens/month
    10000,          -- 10K memories max
    3,              -- 3 agents
    100,            -- 100 sessions/day
    FALSE, FALSE, FALSE, FALSE, FALSE, FALSE,
    7,              -- 7 days audit log
    60, 1000,       -- 60 rpm, 1000 rpd
    'community'
),
(
    'pro',
    100000000,      -- 100M tokens/month
    1000000,        -- 1M memories max
    50,             -- 50 agents
    10000,          -- 10K sessions/day
    TRUE, TRUE, TRUE, TRUE, FALSE, FALSE,
    30,             -- 30 days audit log
    1000, 50000,    -- 1000 rpm, 50K rpd
    'email'
),
(
    'enterprise',
    9999999999,     -- Unlimited (effectively)
    9999999999,     -- Unlimited
    9999,           -- Unlimited
    9999999,        -- Unlimited
    TRUE, TRUE, TRUE, TRUE, TRUE, TRUE,
    365,            -- 1 year audit log
    10000, 1000000, -- 10K rpm, 1M rpd
    'dedicated'
);
```

---

#### Audit Log

```sql
-- ================================================================
-- AUDIT LOG
-- Append-only compliance log (never updated, only inserted)
-- ================================================================
CREATE TABLE ibex_audit.audit_log (
    id              BIGSERIAL,
    org_id          UUID NOT NULL,
    -- Not FK: audit log must survive org deletion

    -- Actor
    user_id         UUID,
    token_id        UUID,
    service_name    TEXT,
    -- Which service performed the action

    -- Action
    action          TEXT NOT NULL,
    -- Examples: 'memory.read', 'directive.promote',
    --           'token.create', 'org.suspend'

    resource_type   TEXT NOT NULL,
    resource_id     UUID,

    -- Request context
    ip_address      INET,
    user_agent      TEXT,
    request_id      UUID,
    trace_id        TEXT,

    -- Result
    success         BOOLEAN NOT NULL,
    error_code      TEXT,
    error_message   TEXT,

    -- Change details
    previous_state  JSONB,
    new_state       JSONB,

    -- Compliance metadata
    data_classification TEXT
                    CHECK (data_classification IN (
                        'public', 'internal',
                        'confidential', 'restricted'
                    )),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id, created_at)
    -- Composite PK needed for partitioning
)
PARTITION BY RANGE (created_at);

-- Monthly partitions
CREATE TABLE ibex_audit.audit_log_2024_01
    PARTITION OF ibex_audit.audit_log
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

-- Indexes
CREATE INDEX idx_audit_log_org_id
    ON ibex_audit.audit_log(org_id, created_at DESC);

CREATE INDEX idx_audit_log_user_id
    ON ibex_audit.audit_log(user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

CREATE INDEX idx_audit_log_resource
    ON ibex_audit.audit_log(resource_type, resource_id,
                             created_at DESC)
    WHERE resource_id IS NOT NULL;

-- IMPORTANT: No RLS on audit log
-- Service accounts can write, admins can read their org's logs
-- Super admins can read all logs
-- This is enforced at application layer, not database layer
-- RLS would prevent cross-org forensics during incidents
```

---

#### Database Functions and Triggers

```sql
-- ================================================================
-- UTILITY FUNCTIONS
-- Shared functions used across tables
-- ================================================================

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION ibex_core.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at
CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON ibex_core.organizations
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();

CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON ibex_core.users
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();

CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON ibex_core.agents
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();

CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON ibex_core.memories
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();

-- Memory version tracking trigger
CREATE OR REPLACE FUNCTION ibex_core.track_memory_version()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO ibex_core.memory_versions (
        memory_id,
        org_id,
        version_number,
        operation,
        previous_content,
        new_content,
        previous_status,
        new_status
    )
    VALUES (
        NEW.id,
        NEW.org_id,
        (
            SELECT COALESCE(MAX(version_number), 0) + 1
            FROM ibex_core.memory_versions
            WHERE memory_id = NEW.id
        ),
        CASE
            WHEN TG_OP = 'INSERT' THEN 'created'
            WHEN OLD.status != NEW.status THEN 'status_changed'
            WHEN OLD.content != NEW.content THEN 'updated'
            ELSE 'updated'
        END,
        OLD.content,
        NEW.content,
        OLD.status,
        NEW.status
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER track_memory_version
    AFTER INSERT OR UPDATE ON ibex_core.memories
    FOR EACH ROW EXECUTE FUNCTION ibex_core.track_memory_version();

-- Agent statistics update function
CREATE OR REPLACE FUNCTION ibex_core.update_agent_stats()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE ibex_core.agents
    SET
        total_memories = (
            SELECT COUNT(*) FROM ibex_core.memories
            WHERE agent_id = NEW.agent_id
            AND status = 'active'
            AND deleted_at IS NULL
        ),
        last_active_at = NOW()
    WHERE id = NEW.agent_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_agent_memory_stats
    AFTER INSERT ON ibex_core.memories
    FOR EACH ROW EXECUTE FUNCTION ibex_core.update_agent_stats();

-- GDPR deletion function
-- Handles complete data deletion with audit trail
CREATE OR REPLACE FUNCTION ibex_core.gdpr_delete_agent_data(
    p_org_id UUID,
    p_agent_id UUID,
    p_requested_by UUID,
    p_deletion_scope TEXT -- 'all', 'memories_only', 'sessions_only'
)
RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
    v_memories_deleted INTEGER;
    v_sessions_deleted INTEGER;
    v_certificate_id UUID;
BEGIN
    -- Verify requester has permission (application layer also checks)
    IF NOT EXISTS (
        SELECT 1 FROM ibex_core.users
        WHERE id = p_requested_by
        AND org_id = p_org_id
        AND role IN ('owner', 'admin')
        AND deleted_at IS NULL
    ) THEN
        RAISE EXCEPTION 'Insufficient permissions for GDPR deletion';
    END IF;

    -- Delete memories
    IF p_deletion_scope IN ('all', 'memories_only') THEN
        UPDATE ibex_core.memories
        SET
            status = 'deleted',
            content = '[GDPR DELETED]',
            embedding = NULL,
            deleted_at = NOW()
        WHERE agent_id = p_agent_id
        AND org_id = p_org_id
        AND deleted_at IS NULL;

        GET DIAGNOSTICS v_memories_deleted = ROW_COUNT;
    END IF;

    -- Mark sessions
    IF p_deletion_scope IN ('all', 'sessions_only') THEN
        UPDATE ibex_core.sessions
        SET status = 'completed'
        WHERE agent_id = p_agent_id
        AND org_id = p_org_id
        AND status NOT IN ('completed', 'failed');

        GET DIAGNOSTICS v_sessions_deleted = ROW_COUNT;
    END IF;

    -- Generate deletion certificate
    v_certificate_id := gen_random_uuid();

    -- Write to audit log (survives org deletion)
    INSERT INTO ibex_audit.audit_log (
        org_id, user_id, action,
        resource_type, resource_id,
        success, new_state
    ) VALUES (
        p_org_id,
        p_requested_by,
        'gdpr.deletion',
        'agent',
        p_agent_id,
        TRUE,
        jsonb_build_object(
            'certificate_id', v_certificate_id,
            'deletion_scope', p_deletion_scope,
            'memories_deleted', v_memories_deleted,
            'sessions_deleted', v_sessions_deleted,
            'completed_at', NOW()
        )
    );

    v_result := jsonb_build_object(
        'certificate_id', v_certificate_id,
        'memories_deleted', v_memories_deleted,
        'sessions_deleted', v_sessions_deleted,
        'completed_at', NOW()
    );

    RETURN v_result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

---

#### Migration Strategy

```sql
-- ================================================================
-- ALEMBIC MIGRATION CONFIGURATION
-- Naming convention: {timestamp}_{description}.py
-- Example: 20240115_001_create_organizations.py
-- ================================================================

-- Migration principles:
--
-- 1. NEVER drop columns in same migration as removing usage
--    Phase 1: Add new column, deploy code using both
--    Phase 2: Drop old column (separate migration, separate deploy)
--
-- 2. ALWAYS use CREATE INDEX CONCURRENTLY for large tables
--    Standard CREATE INDEX takes table lock
--    CONCURRENTLY builds without locking (but takes longer)
--
-- 3. ALWAYS add NOT NULL with a DEFAULT for existing tables
--    ALTER TABLE t ADD COLUMN c TEXT NOT NULL DEFAULT 'value';
--    First marks all existing rows with default
--    Then removes default if desired
--
-- 4. LARGE TABLE operations:
--    - Use batched updates (1000 rows at a time)
--    - Run during low traffic
--    - Have rollback plan ready
--
-- 5. FOREIGN KEYS on large tables:
--    Add NOT VALID first (fast, doesn't check existing rows)
--    Then VALIDATE separately (slower, can be done online)
--    ALTER TABLE t ADD CONSTRAINT fk FOREIGN KEY (...) NOT VALID;
--    ALTER TABLE t VALIDATE CONSTRAINT fk;

-- Example migration sequence:
-- 20240101_001_initial_schema.py → Core tables
-- 20240101_002_add_rls_policies.py → Security
-- 20240101_003_seed_tier_limits.py → Reference data
-- 20240115_001_add_memory_pii_fields.py → Feature addition
-- 20240120_001_add_memory_injection_risk.py → Feature addition
```

---

### ClickHouse Schema

#### Phase 2 — `ibex.llm_traces` (canonical)

Applied by migration `infra/migrations/clickhouse/000001_create_llm_traces` ([ADR-0033](../content/docs/adr/0033-clickhouse-schema.mdx)). No prompt/completion content.

```sql
CREATE TABLE IF NOT EXISTS ibex.llm_traces
(
    request_id           String,
    org_id               UUID,
    agent_id             UUID,
    session_id           Nullable(UUID),
    checkpoint_id        Nullable(UUID),
    model                LowCardinality(String),
    provider             LowCardinality(String),
    is_streaming         Bool,
    input_tokens         UInt32,
    output_tokens        UInt32,
    total_tokens         UInt32,
    auth_latency_ms      UInt16,
    directive_latency_ms UInt16,
    provider_ttfb_ms     UInt32,
    total_latency_ms     UInt32,
    status_code          UInt16,
    is_complete          Bool,
    error_code           LowCardinality(String),
    requested_at         DateTime64(3, 'UTC'),
    completed_at         DateTime64(3, 'UTC'),
    event_date           Date MATERIALIZED toDate(requested_at)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (org_id, agent_id, requested_at)
TTL event_date + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;
```

#### Phase 2.5 — `ibex.mcp_tool_calls` (G6.M1 / ADR-0050)

Applied by migration `infra/migrations/clickhouse/000002_create_mcp_tool_calls`. Metadata only — no tool argument or memory content columns. Phase 3.5.E.4 must expand, not recreate.

```sql
CREATE TABLE IF NOT EXISTS ibex.mcp_tool_calls
(
    request_id   String,
    org_id       UUID,
    agent_id     Nullable(UUID),
    tool_name    LowCardinality(String),
    latency_ms   UInt32,
    success      Bool,
    error_code   LowCardinality(String),
    requested_at DateTime64(3, 'UTC'),
    event_date   Date MATERIALIZED toDate(requested_at)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (org_id, requested_at, request_id)
TTL event_date + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;
```

#### Future ClickHouse tables (Phase 3+)

The following sketches (`inference_traces`, billing MVs, etc.) are **not** applied in Phase 2. Kept for planning only.

```sql
-- ================================================================
-- INFERENCE TRACES (future — richer than Phase 2 llm_traces)
-- ================================================================
CREATE TABLE inference_traces (
    -- Identifiers
    trace_id            UUID,
    org_id              UUID,
    agent_id            UUID,
    session_id          UUID,
    user_id             Nullable(UUID),

    -- Request details
    model               String,
    prompt_tokens       UInt32,
    completion_tokens   UInt32,
    total_tokens        UInt32,
    prompt_hash         String,
    -- SHA-256 of prompt for deduplication analysis
    -- (not the actual prompt - privacy)

    -- Context assembly
    directive_version_id    Nullable(UUID),
    memories_retrieved      UInt8,
    memory_ids              Array(UUID),
    context_tokens_used     UInt16,
    context_budget_tokens   UInt16,

    -- Performance
    total_latency_ms        UInt32,
    provider_latency_ms     UInt32,
    proxy_overhead_ms       UInt16,
    context_assembly_ms     UInt16,
    auth_validation_ms      UInt8,
    rate_limit_check_ms     UInt8,

    -- Result
    status                  Enum8(
                                'success' = 1,
                                'error' = 2,
                                'timeout' = 3,
                                'rate_limited' = 4,
                                'auth_failed' = 5
                            ),
    error_type              Nullable(String),
    error_message           Nullable(String),

    -- Provider info
    provider                String,  -- 'openai', 'anthropic', etc.
    provider_request_id     Nullable(String),

    -- Client info
    sdk_language            Nullable(String),
    sdk_version             Nullable(String),

    -- Streaming
    is_streaming            UInt8,  -- Boolean as UInt8
    stream_chunks           Nullable(UInt16),

    -- Cost estimation
    estimated_cost_cents    Nullable(Decimal(10,6)),

    -- Timestamp
    created_at              DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (org_id, agent_id, created_at)
TTL created_at + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- Materialized view: hourly aggregates for fast dashboard queries
CREATE MATERIALIZED VIEW inference_traces_hourly
ENGINE = SummingMergeTree()
ORDER BY (org_id, agent_id, hour)
AS SELECT
    org_id,
    agent_id,
    toStartOfHour(created_at) AS hour,
    count() AS total_requests,
    sum(prompt_tokens) AS total_prompt_tokens,
    sum(completion_tokens) AS total_completion_tokens,
    avg(total_latency_ms) AS avg_latency_ms,
    quantile(0.95)(total_latency_ms) AS p95_latency_ms,
    countIf(status = 'success') AS success_count,
    countIf(status = 'error') AS error_count
FROM inference_traces
GROUP BY org_id, agent_id, hour;

-- ================================================================
-- BILLING EVENTS
-- Immutable record of every billable action
-- ================================================================
CREATE TABLE billing_events (
    org_id              UUID,
    event_type          Enum8(
                            'token_usage' = 1,
                            'memory_write' = 2,
                            'memory_read' = 3,
                            'embedding_generated' = 4,
                            'session_created' = 5,
                            'api_call' = 6
                        ),
    quantity            UInt64,
    unit                String,  -- 'tokens', 'memories', 'requests'

    -- Cost calculation inputs
    unit_price_cents    Decimal(10,6),
    total_cost_cents    Decimal(10,2),

    -- Context
    agent_id            Nullable(UUID),
    session_id          Nullable(UUID),
    trace_id            Nullable(UUID),

    -- Metadata
    metadata            String,  -- JSON

    -- Billing period
    billing_period      String,  -- 'YYYY-MM' format

    created_at          DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY billing_period
ORDER BY (org_id, created_at)
SETTINGS index_granularity = 8192;
-- No TTL: billing records kept forever

-- ================================================================
-- MEMORY ACCESS LOG
-- Track which memories are retrieved and when
-- ================================================================
CREATE TABLE memory_access_log (
    org_id          UUID,
    agent_id        UUID,
    session_id      UUID,
    memory_id       UUID,
    trace_id        UUID,

    -- Access context
    access_type     Enum8('retrieved' = 1, 'pinned' = 2,
                          'injected' = 3),
    retrieval_rank  UInt8,
    retrieval_score Float32,
    relevance_score Float32,
    recency_score   Float32,
    usefulness_score Float32,

    -- Feedback
    feedback        Nullable(Enum8('positive' = 1, 'negative' = 2,
                                    'neutral' = 3)),
    feedback_at     Nullable(DateTime64(3)),

    created_at      DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (org_id, agent_id, memory_id, created_at)
TTL created_at + INTERVAL 90 DAY;

-- ================================================================
-- API REQUEST LOG
-- All API server requests (not proxy - that's inference_traces)
-- ================================================================
CREATE TABLE api_request_log (
    org_id          Nullable(UUID),
    user_id         Nullable(UUID),
    request_id      UUID,
    trace_id        String,

    -- Request
    method          String,
    path            String,
    status_code     UInt16,
    request_size_bytes UInt32,
    response_size_bytes UInt32,

    -- Performance
    duration_ms     UInt32,
    db_queries      UInt8,
    db_duration_ms  UInt16,
    cache_hits      UInt8,
    cache_misses    UInt8,

    -- Client
    ip_address      String,
    user_agent      Nullable(String),

    created_at      DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (org_id, created_at)
TTL created_at + INTERVAL 30 DAY;
```

---

### Redis Data Structures

```text
================================================================
REDIS KEY PATTERNS AND DATA STRUCTURES
================================================================

Authentication:
  Key:   auth:bloom_filter
  Type:  Bloom filter (RedisBloom)
  Use:   Fast invalid token rejection
  Size:  Dynamic (scales with token count)

  Key:   auth:token:{sha256_hash}
  Type:  String (JSON)
  TTL:   30 seconds
  Value: {"org_id":"...","permissions":123,"expires_at":"..."}
  Use:   Validated token cache

  Key:   auth:revoked:{token_id}
  Type:  String
  TTL:   Until token would have expired + 1 hour
  Value: "1"
  Use:   Token revocation (checked even if in bloom filter)

Rate Limiting:
  Key:   ratelimit:{org_id}:agent:{agent_id}:minute
  Type:  String (integer counter)
  TTL:   60 seconds
  Use:   Per-agent per-minute rate limit

  Key:   ratelimit:{org_id}:minute
  Type:  String (integer counter)
  TTL:   60 seconds
  Use:   Per-org per-minute rate limit

  Key:   ratelimit:{org_id}:day
  Type:  String (integer counter)
  TTL:   86400 seconds
  Use:   Per-org daily limit

  Key:   ratelimit:{org_id}:month_tokens
  Type:  String (integer counter)
  TTL:   Expires at end of billing month
  Use:   Monthly token quota tracking

Chat Idempotency (m2.1.6):
  Key:   idempotency:{org_id}:{key}
  Type:  String (JSON: v, state, fingerprint, status, body)
  TTL:   pending claim ~9m; completed record 24h (IBEX_IDEMPOTENCY_TTL)
  Use:   Client Idempotency-Key claim/commit for non-streaming chat; org from verified token

Hot Memory Cache:
  Key:   {org_id}:hot_memories:{agent_id}
  Type:  Sorted set
  TTL:   3600 seconds (1 hour)
  Score: composite_score (recency × relevance × usefulness)
  Member: memory_id
  Use:   Top memories for this agent sorted by relevance

  Key:   {org_id}:memory:{memory_id}
  Type:  Hash (RedisJSON)
  TTL:   3600 seconds
  Value: {id, content, category, confidence, ...}
  Use:   Full memory object cache (avoids DB reads)

  Key:   {org_id}:memory_embedding:{memory_id}
  Type:  String (binary float array)
  TTL:   86400 seconds (24 hours)
  Use:   Cached embedding (expensive to recompute)

Directive Cache:
  Key:   {org_id}:directive:{agent_id}
  Type:  String (typed JSON envelope)
  TTL:   60 seconds (default; configurable via IBEX_DIRECTIVE_CACHE_TTL)
  Value: {"v":1,"content":"...","injection_mode":"system_first","version_id":"<uuid>"}
         - v: serialization envelope version (forward-compat; not the directive revision)
         - content: active directive text
         - injection_mode: system_first | system_append | user_prepend
         - version_id: directive_versions.id of the active revision
  Use:   Hot path: directive retrieved on every request

  Key:   {org_id}:directive_version:{agent_id}
  Type:  String (UUID)
  TTL:   60 seconds (default; same TTL as directive cache when used)
  Value: Current active directive version ID
  Use:   Version tracking for cache invalidation

Session State:
  Key:   session:{session_id}:heartbeat
  Type:  String (timestamp)
  TTL:   30 seconds (refreshed by heartbeat)
  Value: Unix timestamp of last heartbeat
  Use:   Detect dead sessions

  Key:   session:{session_id}:state
  Type:  Hash
  TTL:   86400 seconds (refreshed on activity)
  Fields: {status, checkpoint_seq, loop_count, ...}
  Use:   Real-time session state

Pub/Sub Channels:
  Channel: directive_updates:{org_id}
  Message: {"agent_id":"...", "new_version_id":"..."}
  Use:   Notify proxies of directive changes

  Channel: token_revocations
  Message: {"token_hash":"...", "token_id":"..."}
  Use:   Immediate token revocation across all proxies

Message Queues (Redis Streams):
  Stream:  memory_extraction_jobs
  Fields:  {trace_id, session_id, agent_id, org_id}
  Groups:  memory_extractors
  Use:     Queue memory extraction after each LLM call

  Stream:  conflict_detection_jobs
  Fields:  {memory_id, candidate_ids[], org_id}
  Groups:  conflict_detectors
  Use:     Queue conflict resolution

  Stream:  notification_jobs
  Fields:  {type, recipient_id, data, org_id}
  Groups:  notification_workers
  Use:     Queue notifications

  Stream:  fingerprint_jobs
  Fields:  {agent_id, org_id, trace_count}
  Groups:  fingerprint_workers
  Use:     Queue behavioral fingerprint computation

Billing:
  Key:   {org_id}:usage:{YYYY-MM}:{event_type}
  Type:  String (integer counter)
  TTL:   90 days after month ends
  Use:   Real-time usage counter (synced to PostgreSQL)

Agent Statistics:
  Key:   {org_id}:agent_stats:{agent_id}
  Type:  Hash
  TTL:   3600 seconds
  Fields: {total_memories, active_sessions, last_active}
  Use:   Dashboard display without DB query
```

---

### Index Strategy Summary

```text
QUERY PATTERN → INDEX → REASONING

"All active memories for agent X":
  → idx_memories_agent_active (org_id, agent_id) WHERE active
  → Partial index (status='active') keeps it small and fast

"Find memory by content hash (dedup check)":
  → idx_memories_content_hash (org_id, agent_id, content_hash)
  → Exact lookup, should be near-instant

"Vector similarity search for top-K memories":
  → idx_memories_embedding USING ivfflat
  → ANN search, 95% accuracy vs exact, 100x faster at scale

"Full-text search across memory content":
  → idx_memories_search_vector USING gin
  → tsvector supports stemming, stop words, ranking

"Recent sessions for agent (dashboard)":
  → idx_sessions_recent (org_id, agent_id, started_at DESC)
  → Dashboard loads recent sessions frequently

"Find stale sessions (heartbeat monitor)":
  → idx_sessions_heartbeat (last_heartbeat_at) WHERE active
  → Background job runs every 30s, must be fast

"Latest valid checkpoint for session":
  → idx_checkpoints_latest_valid (session_id, sequence DESC)
  → Called on session resume, must be instant

"Open drift alerts for org":
  → idx_drift_alerts_open (org_id, status) WHERE open
  → Dashboard notification count query

"Billing usage for period":
  → idx_usage_counters_org_period (org_id, year, month)
  → Billing queries by period
```
