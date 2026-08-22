package responsepipeline

import "errors"

// ErrInvalidResponse is returned when upstream body is not valid chat completion JSON.
var ErrInvalidResponse = errors.New("invalid chat completion response JSON")
