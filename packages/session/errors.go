package session

import "errors"

var (
	// ErrNotFound is returned when a session is missing for the given org.
	ErrNotFound = errors.New("session: not found")
	// ErrDuplicateTurn is returned when UNIQUE(session_id, turn_index) conflicts.
	ErrDuplicateTurn = errors.New("session: duplicate turn_index")
	// ErrConflict is returned for other unique/constraint conflicts.
	ErrConflict = errors.New("session: conflict")
)
