package trace

import "time"

// ClampUint16Ms converts a duration to milliseconds clamped to uint16.
func ClampUint16Ms(d time.Duration) uint16 {
	if d <= 0 {
		return 0
	}
	ms := d / time.Millisecond
	if ms > time.Duration(^uint16(0)) {
		return ^uint16(0)
	}
	return uint16(ms)
}
