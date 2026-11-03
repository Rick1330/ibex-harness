-- Companion to 000057 / ADR-0094: same lookup from the "candidate memory" side.
-- A hydrated memory can be either endpoint of a pending escalation, so both
-- directions need their own partial index.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memory_conflict_escalations_org_candidate_pending
    ON ibex_core.memory_conflict_escalations (org_id, candidate_memory_id)
    WHERE status = 'pending'; -- NOSONAR
