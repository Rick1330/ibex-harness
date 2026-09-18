package usagequery

import (
	"fmt"
	"strings"
	"time"
)

// Rendered is parameterized ClickHouse SQL plus positional args.
type Rendered struct {
	SQL     string
	Args    []any
	MaxRows int
}

// RenderSQL builds constrained SQL with mandatory org_id predicate.
func RenderSQL(q Query, limits BudgetLimits) (Rendered, error) {
	if err := Validate(q, limits); err != nil {
		return Rendered{}, err
	}
	limits.ApplyDefaults()
	limit := q.Limit
	if limit <= 0 {
		limit = limits.MaxRows
	}
	settings := fmt.Sprintf("SETTINGS max_rows_to_read = %d", limits.MaxRows)

	switch q.Shape {
	case ShapeOrgTimeAggregate:
		return renderOrgTime(q, limit, settings)
	case ShapeAgentSessionBreakdown:
		return renderAgentSession(q, limit, settings)
	case ShapeRequestPointLookup:
		return renderRequestPoint(q, settings)
	case ShapeFallbackAttribution:
		return renderFallback(q, limit, settings)
	case ShapeToolCorrelation:
		return renderToolCorrelation(q, limit, settings)
	default:
		return Rendered{}, fmt.Errorf("usagequery: unknown shape %q", q.Shape)
	}
}

func renderOrgTime(q Query, limit int, settings string) (Rendered, error) {
	sql := strings.TrimSpace(fmt.Sprintf(`
SELECT
  toStartOfHour(occurred_at) AS bucket,
  sum(input_tokens) AS input_tokens,
  sum(output_tokens) AS output_tokens,
  sum(estimated_cost_cents) AS estimated_cost_cents,
  count() AS requests,
  any(completeness) AS completeness
FROM ibex.usage_facts
WHERE org_id = ?
  AND occurred_at >= ?
  AND occurred_at < ?
GROUP BY bucket
ORDER BY bucket
LIMIT %d
%s`, limit, settings))
	return Rendered{SQL: sql, Args: []any{q.OrgID, q.Start.UTC(), q.End.UTC()}, MaxRows: limit}, nil
}

func renderAgentSession(q Query, limit int, settings string) (Rendered, error) {
	args := []any{q.OrgID, q.Start.UTC(), q.End.UTC()}
	agentPred := ""
	if q.AgentID != nil {
		agentPred = " AND agent_id = ?"
		args = append(args, *q.AgentID)
	}
	sql := strings.TrimSpace(fmt.Sprintf(`
SELECT
  agent_id,
  sum(input_tokens) AS input_tokens,
  sum(output_tokens) AS output_tokens,
  sum(estimated_cost_cents) AS estimated_cost_cents,
  count() AS requests,
  any(completeness) AS completeness
FROM ibex.usage_facts
WHERE org_id = ?
  AND occurred_at >= ?
  AND occurred_at < ?%s
GROUP BY agent_id
ORDER BY estimated_cost_cents DESC
LIMIT %d
%s`, agentPred, limit, settings))
	return Rendered{SQL: sql, Args: args, MaxRows: limit}, nil
}

func renderRequestPoint(q Query, settings string) (Rendered, error) {
	sql := strings.TrimSpace(fmt.Sprintf(`
SELECT
  request_id, org_id, agent_id, provider, model,
  original_model, fallback_model, fallback_reason,
  input_tokens, output_tokens, total_tokens,
  estimated_cost_cents, actual_cost_cents, rate_card_version,
  completeness, occurred_at
FROM ibex.usage_facts
WHERE org_id = ?
  AND request_id = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 1
%s`, settings))
	return Rendered{
		SQL: sql,
		Args: []any{q.OrgID, q.RequestID, q.Start.UTC(), q.End.UTC()},
		MaxRows: 1,
	}, nil
}

func renderFallback(q Query, limit int, settings string) (Rendered, error) {
	sql := strings.TrimSpace(fmt.Sprintf(`
SELECT
  original_model,
  fallback_model,
  fallback_reason,
  count() AS requests,
  sum(estimated_cost_cents) AS estimated_cost_cents,
  any(completeness) AS completeness
FROM ibex.usage_facts
WHERE org_id = ?
  AND occurred_at >= ?
  AND occurred_at < ?
  AND fallback_model IS NOT NULL
GROUP BY original_model, fallback_model, fallback_reason
ORDER BY requests DESC
LIMIT %d
%s`, limit, settings))
	return Rendered{SQL: sql, Args: []any{q.OrgID, q.Start.UTC(), q.End.UTC()}, MaxRows: limit}, nil
}

func renderToolCorrelation(q Query, limit int, settings string) (Rendered, error) {
	sql := strings.TrimSpace(fmt.Sprintf(`
SELECT
  f.request_id,
  f.agent_id,
  f.model,
  f.estimated_cost_cents,
  f.completeness,
  f.occurred_at,
  t.tool_name,
  t.latency_ms,
  t.success,
  t.error_code
FROM ibex.usage_facts AS f
INNER JOIN ibex.mcp_tool_calls AS t
  ON t.org_id = f.org_id AND t.request_id = f.request_id
WHERE f.org_id = ?
  AND f.occurred_at >= ?
  AND f.occurred_at < ?
ORDER BY f.occurred_at DESC
LIMIT %d
%s`, limit, settings))
	return Rendered{SQL: sql, Args: []any{q.OrgID, q.Start.UTC(), q.End.UTC()}, MaxRows: limit}, nil
}

// FormatTimeUTC is exported for golden fixtures.
func FormatTimeUTC(t time.Time) string {
	return t.UTC().Format(time.RFC3339Nano)
}
