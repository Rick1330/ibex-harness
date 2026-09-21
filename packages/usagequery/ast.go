// Package usagequery provides a typed AST, validator, and SQL renderer for
// bounded ClickHouse usage_facts queries (milestone 4.P.4).
package usagequery

import (
	"fmt"
	"time"

	"github.com/google/uuid"
)

// Shape identifies a constrained usage query template.
type Shape string

const (
	ShapeOrgTimeAggregate      Shape = "org_time_aggregate"
	ShapeAgentSessionBreakdown Shape = "agent_session_breakdown"
	ShapeRequestPointLookup    Shape = "request_point_lookup"
	ShapeFallbackAttribution   Shape = "fallback_attribution"
	ShapeToolCorrelation       Shape = "tool_correlation"
)

// Defaults for query budgets.
const (
	DefaultMaxTimeRange  = 31 * 24 * time.Hour
	DefaultMaxRows       = 10000
	DefaultMaxConcurrent = 4
)

// Query is the typed AST for a usage query.
type Query struct {
	Shape     Shape
	OrgID     uuid.UUID
	Start     time.Time
	End       time.Time
	AgentID   *uuid.UUID
	RequestID string
	Limit     int
}

// BudgetLimits constrains validation.
type BudgetLimits struct {
	MaxTimeRange  time.Duration
	MaxRows       int
	MaxConcurrent int
}

// ApplyDefaults fills zero fields.
func (b *BudgetLimits) ApplyDefaults() {
	if b.MaxTimeRange <= 0 {
		b.MaxTimeRange = DefaultMaxTimeRange
	}
	if b.MaxRows <= 0 {
		b.MaxRows = DefaultMaxRows
	}
	if b.MaxConcurrent <= 0 {
		b.MaxConcurrent = DefaultMaxConcurrent
	}
}

// Validate checks org_id, time range, and shape-specific requirements.
func Validate(q Query, limits BudgetLimits) error {
	limits.ApplyDefaults()
	if err := validateOrgAndWindow(q, limits); err != nil {
		return err
	}
	return validateShape(q)
}

func validateOrgAndWindow(q Query, limits BudgetLimits) error {
	if q.OrgID == uuid.Nil {
		return fmt.Errorf("usagequery: org_id is required")
	}
	if q.Start.IsZero() || q.End.IsZero() {
		return fmt.Errorf("usagequery: start and end are required")
	}
	if !q.End.After(q.Start) {
		return fmt.Errorf("usagequery: end must be after start")
	}
	if q.End.Sub(q.Start) > limits.MaxTimeRange {
		return fmt.Errorf("usagequery: time range exceeds max %s", limits.MaxTimeRange)
	}
	limit := q.Limit
	if limit <= 0 {
		limit = limits.MaxRows
	}
	if limit > limits.MaxRows {
		return fmt.Errorf("usagequery: limit %d exceeds max_rows %d", limit, limits.MaxRows)
	}
	return nil
}

func validateShape(q Query) error {
	switch q.Shape {
	case ShapeOrgTimeAggregate, ShapeAgentSessionBreakdown, ShapeFallbackAttribution, ShapeToolCorrelation:
		return nil
	case ShapeRequestPointLookup:
		if q.RequestID == "" {
			return fmt.Errorf("usagequery: request_id is required for request_point_lookup")
		}
		return nil
	default:
		return fmt.Errorf("usagequery: unknown shape %q", q.Shape)
	}
}

// InflightKey returns the Redis key for concurrent query gating.
func InflightKey(orgID uuid.UUID) string {
	return "org_id:" + orgID.String() + ":usagequery:inflight"
}
