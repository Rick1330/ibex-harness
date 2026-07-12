package provider

import (
	"errors"
	"fmt"
)

// ErrNoProviderForModel is returned when no registered provider supports a model.
var ErrNoProviderForModel = errors.New("no provider configured for this model")

// ProviderError is returned by Complete when the provider returns a non-2xx response.
// ProviderBody is for error mapping only — never log its contents.
type ProviderError struct {
	ProviderName   string
	StatusCode     int
	ProviderBody   []byte
	ProviderErrMsg string
}

func (e *ProviderError) Error() string {
	return fmt.Sprintf("provider %s returned %d: %s", e.ProviderName, e.StatusCode, e.ProviderErrMsg)
}
