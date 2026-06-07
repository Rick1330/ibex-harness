package shutdown

import (
	"fmt"
	"time"
)

// ValidateTimeout checks IBEX_SHUTDOWN_TIMEOUT is positive.
func ValidateTimeout(d time.Duration) error {
	if d <= 0 {
		return fmt.Errorf("IBEX_SHUTDOWN_TIMEOUT must be positive")
	}
	return nil
}
