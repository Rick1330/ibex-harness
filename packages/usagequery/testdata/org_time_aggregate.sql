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
LIMIT 100
SETTINGS max_rows_to_read = 10000
