package http

import (
	"testing"
	"time"
)

func TestUnit_idempotencyCASHTimeout_BudgetsFloorAndScaling(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   time.Duration
		want time.Duration
	}{
		{name: "floor", in: 50 * time.Millisecond, want: 500 * time.Millisecond},
		{name: "scaled", in: 100 * time.Millisecond, want: 900 * time.Millisecond},
	}
	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			if got := idempotencyCASHTimeout(tc.in); got != tc.want {
				t.Fatalf("idempotencyCASHTimeout(%v)=%v want %v", tc.in, got, tc.want)
			}
		})
	}
}
