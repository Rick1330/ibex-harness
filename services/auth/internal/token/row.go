package token

import "time"

// Row is the domain projection of an active token used by Validator.
// Optional fields use pointers so callers avoid sql.Null* types.
type Row struct {
	ID          string
	OrgID       string
	UserID      *string
	AgentID     *string
	Permissions int64
	ExpiresAt   *time.Time
	Hash        string
}
