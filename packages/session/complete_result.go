package session

// CompleteResult is the typed outcome of Complete / CompleteByExternalID.
// NotFound is returned as a result (nil error) so HTTP handlers can map 404
// without inventing a parallel check.
type CompleteResult int

const (
	// CompleteOK means an active session transitioned to completed.
	CompleteOK CompleteResult = iota
	// CompleteNoop means the session was already terminal (completed, abandoned, error).
	CompleteNoop
	// CompleteNotFound means no matching non-deleted session existed for the lookup.
	CompleteNotFound
)

// String returns a stable low-cardinality label for metrics/logs.
func (r CompleteResult) String() string {
	switch r {
	case CompleteOK:
		return ResultOK
	case CompleteNoop:
		return ResultNoop
	case CompleteNotFound:
		return "not_found"
	default:
		return "unknown"
	}
}
