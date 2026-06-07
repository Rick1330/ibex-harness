package validation

import (
	"net/http"
	"testing"
)

func TestValidateChatHeaders(t *testing.T) {
	tests := []struct {
		name    string
		headers map[string]string
		wantLen int
	}{
		{"no optional headers", map[string]string{}, 0},
		{"invalid session uuid", map[string]string{"X-IBEX-Session-ID": "not-a-uuid"}, 1},
		{"valid session", map[string]string{"X-IBEX-Session-ID": "550e8400-e29b-41d4-a716-446655440000"}, 0},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			h := http.Header{}
			for k, v := range tt.headers {
				h.Set(k, v)
			}
			got := ValidateChatHeaders(h)
			if len(got) != tt.wantLen {
				t.Fatalf("len=%d want %d: %+v", len(got), tt.wantLen, got)
			}
		})
	}
}
