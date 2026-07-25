package clickhouse

import (
	"fmt"
	"strings"

	"github.com/google/uuid"
)

func validateRecord(r TraceRecord) error {
	if strings.TrimSpace(r.RequestID) == "" {
		return fmt.Errorf("%w: empty request_id", ErrInvalidRecord)
	}
	if r.OrgID == uuid.Nil {
		return fmt.Errorf("%w: empty org_id", ErrInvalidRecord)
	}
	if r.AgentID == uuid.Nil {
		return fmt.Errorf("%w: empty agent_id", ErrInvalidRecord)
	}
	if r.RequestedAt.IsZero() || r.CompletedAt.IsZero() {
		return fmt.Errorf("%w: missing timestamps", ErrInvalidRecord)
	}
	return nil
}
