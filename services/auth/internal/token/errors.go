package token

import "errors"

// ErrUnauthenticated indicates the token cannot be validated (generic fail-closed).
var ErrUnauthenticated = errors.New("unauthenticated")

// ErrOrgSuspended indicates the token is valid but its organization is not active.
var ErrOrgSuspended = errors.New("organization suspended")
