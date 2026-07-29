package session

import (
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/provider"
	pkgsession "github.com/Rick1330/ibex-harness/packages/session"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/asyncpool"
	httptrace "github.com/Rick1330/ibex-harness/services/proxy/internal/http/trace"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/llm"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/sessioncache"
	"github.com/google/uuid"
)

const (
	// HeaderSessionID is the sticky session correlation header.
	HeaderSessionID = "X-IBEX-Session-ID"
	// CheckpointTaskTimeout bounds AppendCheckpoint / retry work off the hot path.
	CheckpointTaskTimeout = 5 * time.Second
	defaultGetOrCreateTO  = 50 * time.Millisecond
	// maxExternalIDLen bounds sticky keys (UUID header max 36; pad for defense).
	maxExternalIDLen = 64
)

// Resolved holds hot-path session identity for response headers + checkpoint.
// SessionID == uuid.Nil means sticky-only (fail-open): emit response header, skip checkpoint.
type Resolved struct {
	SessionID  uuid.UUID
	ExternalID string
	TurnIndex  int
	OrgID      uuid.UUID
	AgentID    uuid.UUID
}

// Durable reports whether a Postgres session row is available for checkpoints.
func (rs Resolved) Durable() bool {
	return rs.SessionID != uuid.Nil
}

// LifecycleDeps wires session store/cache/pool for resolve + checkpoint.
type LifecycleDeps struct {
	Store         pkgsession.Store
	Cache         *sessioncache.Cache
	Pool          *asyncpool.Pool
	GetOrCreateTO time.Duration
	Log           *logger.Logger
}

func (d LifecycleDeps) getOrCreateTimeout() time.Duration {
	if d.GetOrCreateTO <= 0 {
		return defaultGetOrCreateTO
	}
	return d.GetOrCreateTO
}

// ResolveInput is tenant + request identity for GetOrCreate / cache lookup.
type ResolveInput struct {
	ExternalID         string
	OrgID              uuid.UUID
	AgentID            uuid.UUID
	DirectiveVersionID *uuid.UUID
	Parsed             *llm.ChatCompletionRequest
	ProviderName       string
}

type getOrCreateInput struct {
	key          sessioncache.LookupKey
	parsed       *llm.ChatCompletionRequest
	providerName string
	directiveVID *uuid.UUID
}

// CheckpointInput is LLM-turn data for AppendCheckpoint + trace assemble.
type CheckpointInput struct {
	Messages       []llm.Message
	CompletionText string
	Model          string
	Provider       string
	Usage          *provider.Usage
	Latency        time.Duration
	ProviderReqID  string
	IsStreaming    bool
	IsComplete     bool
}

// SnapshotMeta is request-scoped identity the parent extracts from context.
type SnapshotMeta struct {
	RequestID   string
	OrgID       uuid.UUID
	AgentID     uuid.UUID
	SessionID   *uuid.UUID
	AuthMs      uint16
	DirectiveMs uint16
	RequestedAt time.Time
}

// PostResponseJob bundles checkpoint/trace work for the bounded pool Submit.
type PostResponseJob struct {
	Deps         LifecycleDeps
	In           CheckpointInput
	Snap         httptrace.AssembleInput
	SnapOK       bool
	DoCheckpoint bool
	DoTrace      bool
	TraceWriter  httptrace.TraceWriter
	Log          *logger.Logger
	ExternalID   string
	Params       pkgsession.CheckpointParams
}
