package idempotency

import (
	"fmt"

	"github.com/google/uuid"
)

// RedisKey returns the org-scoped Redis key for an idempotency token.
// Format: idempotency:{org_id}:{key}
func RedisKey(orgID uuid.UUID, key string) string {
	return fmt.Sprintf("idempotency:%s:%s", orgID.String(), key)
}
