package authcache

import "errors"

var (
	// ErrInvalidToken is returned when upstream rejects the token.
	ErrInvalidToken = errors.New("authcache: invalid token")
	// ErrUnavailable is returned when upstream cannot validate (fail closed).
	ErrUnavailable = errors.New("authcache: unavailable")
)
