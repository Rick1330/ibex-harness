package trace

import "time"

// ClampUint16Ms floors a duration to whole milliseconds and saturates at uint16 max.
// Callers use this for stage latency fields that must fit ClickHouse UInt16 columns.
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
