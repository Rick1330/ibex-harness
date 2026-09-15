package http

import (
	"net/http"
	"testing"

	"github.com/Rick1330/ibex-harness/packages/modelpolicy"
)

func mustNewRouter(tb testing.TB, deps RouterDeps) http.Handler {
	tb.Helper()
	// Unit tests historically assumed allow-all when ModelRouter was nil.
	// Production NewRouter defaults to DenyAllRegistry (4.P.1); tests opt into
	// the documented IBEX_MODEL_POLICY_ALLOW_PASSTHROUGH escape hatch unless
	// they set ModelRouter explicitly.
	if deps.ModelRouter == nil && deps.ProviderRegistry != nil {
		deps.ModelRouter = modelpolicy.PassthroughRegistry{Base: deps.ProviderRegistry}
	}
	h, err := NewRouter(deps)
	if err != nil {
		tb.Fatalf("NewRouter: %v", err)
	}
	return h
}
