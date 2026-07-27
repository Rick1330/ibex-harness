package http

import (
	"testing"
	"time"
)

func TestUnit_idempotencyCASHTimeout(t *testing.T) {
	t.Parallel()
	if got := idempotencyCASHTimeout(50 * time.Millisecond); got != 500*time.Millisecond {
		t.Fatalf("floor: got %v want 500ms", got)
	}
	if got := idempotencyCASHTimeout(100 * time.Millisecond); got != 900*time.Millisecond {
		t.Fatalf("scaled: got %v want 900ms", got)
	}
}
