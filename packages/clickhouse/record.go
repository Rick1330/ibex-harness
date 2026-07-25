// Package clickhouse provides a typed batch writer for ibex.llm_traces.
package clickhouse

import (
	"time"

	"github.com/google/uuid"
)

// TraceRecord is a single row in ibex.llm_traces.
// Field names and types match the ClickHouse schema exactly.
// Content (prompt/completion) is intentionally omitted — never stored.
type TraceRecord struct {
	RequestID          string
	OrgID              uuid.UUID
	AgentID            uuid.UUID
	SessionID          *uuid.UUID
	CheckpointID       *uuid.UUID
	Model              string
	Provider           string
	IsStreaming        bool
	InputTokens        uint32
	OutputTokens       uint32
	TotalTokens        uint32
	AuthLatencyMs      uint16
	DirectiveLatencyMs uint16
	ProviderTTFBMs     uint32
	TotalLatencyMs     uint32
	StatusCode         uint16
	IsComplete         bool
	ErrorCode          string
	RequestedAt        time.Time
	CompletedAt        time.Time
}
