package metrics

import (
	"database/sql"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	_ "github.com/lib/pq"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	dto "github.com/prometheus/client_model/go"
	"github.com/prometheus/common/expfmt"
)

func TestMetricsEndpoint_Format(t *testing.T) {
	t.Parallel()
	reg := NewProxy("test-proxy")
	seedProxySamples(reg)
	srv := httptest.NewServer(promhttp.HandlerFor(reg.Gatherer(), promhttp.HandlerOpts{}))
	defer srv.Close()

	resp, err := http.Get(srv.URL)
	if err != nil {
		t.Fatalf("get metrics: %v", err)
	}
	t.Cleanup(func() { _ = resp.Body.Close() })

	dec := expfmt.NewDecoder(resp.Body, expfmt.NewFormat(expfmt.TypeTextPlain))
	for {
		var mf dto.MetricFamily
		err := dec.Decode(&mf)
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatalf("parse metrics: %v", err)
		}
	}
}

func TestMetricsEndpoint_RequiredMetrics(t *testing.T) {
	t.Parallel()
	reg := NewProxy("test-proxy")
	seedProxySamples(reg)
	assertRequiredMetrics(t, reg.Gatherer(), ProxyRequiredMetricNames)
}

func TestAuthMetricsEndpoint_RequiredMetrics(t *testing.T) {
	t.Parallel()
	db, err := sql.Open("postgres", "postgres://localhost/unused?sslmode=disable")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })

	reg := NewAuth(AuthConfig{ServiceName: "test-auth", DB: db})
	seedAuthSamples(reg)
	assertRequiredMetrics(t, reg.Gatherer(), AuthRequiredMetricNames)
}

func TestMetricLabels_NoHighCardinality(t *testing.T) {
	t.Parallel()
	proxyReg := NewProxy("test-proxy")
	authReg := NewAuth(AuthConfig{ServiceName: "test-auth"})

	assertNoForbiddenLabels(t, proxyReg.Gatherer())
	assertNoForbiddenLabels(t, authReg.Gatherer())
}

func TestHTTPMiddleware_RecordsRouteTemplate(t *testing.T) {
	t.Parallel()
	reg := NewProxy("test-proxy")
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/health", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := HTTPMiddleware(reg)(mux)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/health", nil)
	handler.ServeHTTP(rec, req)

	names := gatherMetricNames(t, reg.Gatherer())
	if _, ok := names["ibex_proxy_requests_total"]; !ok {
		t.Fatal("missing ibex_proxy_requests_total")
	}
	body := scrapeMetrics(t, reg.Gatherer())
	if !containsRouteLabel(body, "/v1/health") {
		t.Fatalf("expected route=/v1/health in metrics, got:\n%s", body)
	}
}

func BenchmarkObserveHTTPRequest(b *testing.B) {
	reg := NewProxy("bench-proxy")
	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		reg.ObserveHTTPRequest(HTTPRequestObservation{
			Route: "/v1/test", Method: "GET", StatusCode: "200", Seconds: 0.001,
		})
	}
}

func BenchmarkObserveDBQuery(b *testing.B) {
	reg := NewAuth(AuthConfig{ServiceName: "bench-auth"})
	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		reg.ObserveDBQuery(DBQueryObservation{Operation: DBOpFindTokenByPrefix, Seconds: 0.001})
	}
}

func BenchmarkObserveValidateToken(b *testing.B) {
	reg := NewAuth(AuthConfig{ServiceName: "bench-auth"})
	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		reg.ObserveValidateToken(ValidateTokenObservation{Result: TokenResultOK, Seconds: 0.001})
	}
}

func BenchmarkIncRateLimit(b *testing.B) {
	reg := NewProxy("bench-proxy")
	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		reg.IncRateLimitAllowed()
	}
}

func seedProxySamples(reg *ProxyRegistry) {
	reg.ObserveHTTPRequest(HTTPRequestObservation{
		Route: "/health", Method: http.MethodGet, StatusCode: "200", Seconds: 0.001,
	})
	reg.IncRateLimitAllowed()
}

func seedAuthSamples(reg *AuthRegistry) {
	reg.ObserveValidateToken(ValidateTokenObservation{Result: TokenResultOK, Seconds: 0.001})
	reg.ObserveValidateAgent(ValidateAgentObservation{Result: AgentResultOK, Seconds: 0.001})
	reg.IncGRPCRequest(GRPCRequestLabels{Method: "ValidateToken", Status: "OK"})
	reg.ObserveDBQuery(DBQueryObservation{Operation: DBOpFindTokenByPrefix, Seconds: 0.001})
	reg.ObserveHTTPRequest(HTTPRequestObservation{
		Route: "/health", Method: http.MethodGet, StatusCode: "200", Seconds: 0.001,
	})
}

func assertRequiredMetrics(t *testing.T, gatherer prometheus.Gatherer, required []string) {
	t.Helper()
	names := gatherMetricNames(t, gatherer)
	for _, name := range required {
		if _, ok := names[name]; !ok {
			t.Fatalf("missing required metric %q", name)
		}
	}
}

func gatherMetricNames(t *testing.T, gatherer prometheus.Gatherer) map[string]struct{} {
	t.Helper()
	mfs, err := gatherer.Gather()
	if err != nil {
		t.Fatalf("gather: %v", err)
	}
	names := make(map[string]struct{}, len(mfs))
	for _, mf := range mfs {
		names[mf.GetName()] = struct{}{}
	}
	return names
}

func scrapeMetrics(t *testing.T, gatherer prometheus.Gatherer) string {
	t.Helper()
	rec := httptest.NewRecorder()
	Handler(gatherer).ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("metrics status: got %d", rec.Code)
	}
	body, err := io.ReadAll(rec.Body)
	if err != nil {
		t.Fatalf("read body: %v", err)
	}
	return string(body)
}

func containsRouteLabel(body, route string) bool {
	return strings.Contains(body, `route="`+route+`"`)
}

func assertNoForbiddenLabels(t *testing.T, gatherer prometheus.Gatherer) {
	t.Helper()
	mfs, err := gatherer.Gather()
	if err != nil {
		t.Fatalf("gather: %v", err)
	}
	forbidden := make(map[string]struct{}, len(ForbiddenLabelNames))
	for _, name := range ForbiddenLabelNames {
		forbidden[name] = struct{}{}
	}
	for _, mf := range mfs {
		for _, m := range mf.GetMetric() {
			checkMetricLabels(t, mf.GetName(), m, forbidden)
		}
	}
}

func checkMetricLabels(t *testing.T, metricName string, m *dto.Metric, forbidden map[string]struct{}) {
	t.Helper()
	for _, lp := range m.GetLabel() {
		if _, bad := forbidden[lp.GetName()]; bad {
			t.Fatalf("metric %q uses forbidden label %q", metricName, lp.GetName())
		}
	}
}
