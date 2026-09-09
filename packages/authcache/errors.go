package authcache

import "errors"

var (
	// ErrInvalidToken is returned when upstream rejects the token.
	ErrInvalidToken = errors.New("authcache: invalid token")
	// ErrOrgSuspended is returned when upstream rejects due to org lifecycle (not bloomed).
	ErrOrgSuspended = errors.New("authcache: organization suspended")
	// ErrUnavailable is returned when upstream cannot validate (fail closed).
	ErrUnavailable = errors.New("authcache: unavailable")
)
