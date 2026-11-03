package session

import (
	"context"
	"database/sql"
	"errors"
	"fmt"

	"github.com/google/uuid"
)

// ErrEvidenceFenceNotFound is returned for a missing, deleted, or cross-tenant
// session. Callers must not infer lifecycle authority from an absent row.
var ErrEvidenceFenceNotFound = errors.New("session: evidence fence not found")

// EvidenceFence is the authoritative lifecycle version for a session resource.
type EvidenceFence struct {
	ResourceType    string
	ResourceID      uuid.UUID
	ResourceVersion int64
}

// LookupEvidenceFence returns the active session fence under org-scoped RLS.
// The fence is read from the same PostgreSQL row whose soft-delete trigger
// advances the version. Missing/deleted/cross-tenant rows fail closed.
func (s *PostgresStore) LookupEvidenceFence(ctx context.Context, orgID, sessionID uuid.UUID) (EvidenceFence, error) {
	if orgID == uuid.Nil || sessionID == uuid.Nil {
		return EvidenceFence{}, ErrEvidenceFenceNotFound
	}
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return EvidenceFence{}, fmt.Errorf("session: begin evidence fence lookup: %w", err)
	}
	//nolint:errcheck // deferred rollback is harmless after commit
	defer func() { _ = tx.Rollback() }()
	if err := setOrgRLS(ctx, tx, orgID); err != nil {
		return EvidenceFence{}, err
	}
	var version int64
	err = tx.QueryRowContext(ctx, `
SELECT evidence_fence_version
FROM ibex_core.sessions
WHERE org_id = $1 AND id = $2 AND deleted_at IS NULL`, orgID, sessionID).Scan(&version)
	if errors.Is(err, sql.ErrNoRows) {
		return EvidenceFence{}, ErrEvidenceFenceNotFound
	}
	if err != nil {
		return EvidenceFence{}, fmt.Errorf("session: lookup evidence fence: %w", err)
	}
	if version <= 0 {
		return EvidenceFence{}, fmt.Errorf("session: invalid evidence fence version")
	}
	if err := tx.Commit(); err != nil {
		return EvidenceFence{}, fmt.Errorf("session: commit evidence fence lookup: %w", err)
	}
	return EvidenceFence{ResourceType: "session", ResourceID: sessionID, ResourceVersion: version}, nil
}
