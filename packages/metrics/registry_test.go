package metrics

import (
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"
	"github.com/prometheus/common/expfmt"
)

func TestMetricsEndpoint_Format(t *testing.T) {
	reg := NewProxy("test-proxy")
	seedProxySamples(reg)
	srv := httptest.NewServer(Handler(reg.Gatherer()))
	defer srv.Close()

	resp, err := http.Get(srv.URL)
	if err != nil {
		t.Fatalf("get metrics: %v", err)
	}
	defer resp.Body.Close()

	dec := expfmt.NewDecoder(resp.Body, expfmt.FmtText)
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
	reg := NewProxy("test-proxy")
	seedProxySamples(reg)
	assertRequiredMetrics(t, reg.Gatherer(), ProxyRequiredMetricNames)
}

func TestAuthMetricsEndpoint_RequiredMetrics(t *testing.T) {
	reg := NewAuth("test-auth", nil)
	seedAuthSamples(reg)
	assertRequiredMetrics(t, reg.Gatherer(), AuthRequiredMetricNames)
}

func TestMetricLabels_NoHighCardinality(t *testing.T) {
	proxyReg := NewProxy("test-proxy")
	authReg := NewAuth("test-auth", nil)

	assertNoForbiddenLabels(t, proxyReg.Gatherer())
	assertNoForbiddenLabels(t, authReg.Gatherer())
}

func seedProxySamples(reg *ProxyRegistry) {
	reg.ObserveHTTPRequest("/health", http.MethodGet, "200", 0.001)
	reg.IncRateLimitAllowed()
}

func seedAuthSamples(reg *AuthRegistry) {
	reg.ObserveValidateToken(TokenResultOK, 0.001)
	reg.ObserveValidateAgent(AgentResultOK, 0.001)
	reg.IncGRPCRequest("ValidateToken", "OK")
	reg.ObserveDBQuery("find_token_by_prefix", 0.001)
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
