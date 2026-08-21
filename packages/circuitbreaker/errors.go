package circuitbreaker

import "errors"

// ErrOpen is returned when the circuit is open and the call was not attempted.
var ErrOpen = errors.New("circuit breaker open")
