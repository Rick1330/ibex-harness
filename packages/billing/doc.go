// Package billing implements spend-cap budget cache, rate-card cost estimates,
// and usage_facts write helpers for milestone 4.P.4.
package billing

import "errors"

// ErrBudgetUnavailable is returned when budget load/cache infrastructure fails (fail closed).
var ErrBudgetUnavailable = errors.New("budget unavailable")
