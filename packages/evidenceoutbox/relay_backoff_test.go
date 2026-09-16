package evidenceoutbox

import (
	"testing"
)

func TestUnit_RetryBackoffSeconds_JitterAndCap(t *testing.T) {
	t.Parallel()
	seen := map[int]struct{}{}
	for i := 0; i < 40; i++ {
		secs := retryBackoffSeconds(3)
		if secs < 1 || secs > maxRetryBackoffSecs {
			t.Fatalf("backoff=%d out of range", secs)
		}
		seen[secs] = struct{}{}
	}
	if len(seen) < 2 {
		t.Fatalf("expected jittered delays, got single value set %#v", seen)
	}
	if got := retryBackoffSeconds(100); got > maxRetryBackoffSecs {
		t.Fatalf("cap exceeded: %d", got)
	}
}
