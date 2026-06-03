package token

import "errors"

// ErrUnauthenticated indicates the token cannot be validated (generic fail-closed).
var ErrUnauthenticated = errors.New("unauthenticated")
