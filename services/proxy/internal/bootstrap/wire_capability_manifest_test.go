package bootstrap

import (
	"path/filepath"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/healthcheck"
	"github.com/Rick1330/ibex-harness/packages/logger"
	ibexmetrics "github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/packages/provider"
	"github.com/Rick1330/ibex-harness/packages/ratelimit"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
)

func TestNewHTTPServerManifestLoadFailure(t *testing.T) {
	t.Setenv("IBEX_PROVIDER_CAPABILITY_MANIFEST", filepath.Join(t.TempDir(), "missing.json"))
	cfg := config.Config{Port: "8080"}
	cfg.ApplyDefaults()
	providerReg, err := provider.NewRegistry(provider.BuiltInCapabilityCatalog())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := newHTTPServer(proxyhttp.RouterDeps{
		Config: cfg, Logger: logger.Discard("proxy"), Metrics: ibexmetrics.NewProxy("proxy"),
		Limiter: ratelimit.Noop(), Health: &healthcheck.Server{}, ProviderRegistry: providerReg,
	}); err == nil {
		t.Fatal("configured missing manifest must fail server construction")
	}
}
