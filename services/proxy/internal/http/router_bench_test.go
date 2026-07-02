package http

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

func BenchmarkProxyHealth(b *testing.B) {
	router := newTestRouter(config.Config{ServiceName: "proxy"}, nil, nil)
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			b.Fatalf("expected 200, got %d", rec.Code)
		}
	}
}
