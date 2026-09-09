package session

import "errors"

var (
	// ErrNotFound is returned when a session is missing for the given org.
	ErrNotFound = errors.New("session: not found")
	// ErrAgentNotFound is returned when GetOrCreate targets a missing or soft-deleted agent.
	ErrAgentNotFound = errors.New("session: agent not found or deleted")
	// ErrDuplicateTurn is returned when UNIQUE(session_id, turn_index) conflicts.
	ErrDuplicateTurn = errors.New("session: duplicate turn_index")
	// ErrConflict is returned for other unique/constraint conflicts.
	ErrConflict = errors.New("session: conflict")
)
