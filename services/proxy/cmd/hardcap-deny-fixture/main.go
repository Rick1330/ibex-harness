// Minimal HTTP fixture that mounts the real proxy BudgetMiddleware against an
// exhausted hard-cap loader. Used by web/e2e/hard-cap-denial.spec.ts (journey #8).
package main

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"os"
	"time"

	"github.com/Rick1330/ibex-harness/packages/billing"
	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/packages/metrics"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/auth"
	proxyhttp "github.com/Rick1330/ibex-harness/services/proxy/internal/http"
	"github.com/google/uuid"
)

type exhaustedLoader struct {
	org uuid.UUID
}

func (e exhaustedLoader) LoadOrg(_ context.Context, orgID uuid.UUID) (billing.BudgetSnapshot, error) {
	if orgID != e.org {
		return billing.BudgetSnapshot{}, fmt.Errorf("unexpected org")
	}
	return billing.BudgetSnapshot{
		HasHardCap:      true,
		CapCents:        100,
		SpentCents:      100,
		EnforcementMode: billing.EnforcementHardCap,
	}, nil
}

func main() {
	org := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	cache, err := billing.NewCache(
		exhaustedLoader{org: org},
		billing.Config{CacheTTL: time.Minute, LRUSize: 4},
		billing.NoopMetrics{},
	)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	reg := metrics.NewProxy("hardcap-e2e")
	deny := proxyhttp.BudgetMiddleware(cache, logger.Discard("hardcap-e2e"), reg)(
		http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"ok":true}`))
		}),
	)
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/chat/completions", func(w http.ResponseWriter, r *http.Request) {
		ctx := auth.WithContext(r.Context(), &auth.ValidateResult{OrgID: org})
		deny.ServeHTTP(w, r.WithContext(ctx))
	})

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Printf("%s\n", ln.Addr().String())
	_ = http.Serve(ln, mux)
}
