package bootstrap

import (
	"testing"
	"time"

	"github.com/Rick1330/ibex-harness/packages/logger"
	"github.com/Rick1330/ibex-harness/services/proxy/internal/config"
)

func TestUnit_SetupContextClient_EmptyTarget(t *testing.T) {
	t.Parallel()

	got, err := setupContextClient(config.Config{ContextGRPCTarget: ""}, logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("setupContextClient: %v", err)
	}
	if got.client != nil || got.conn != nil {
		t.Fatalf("expected nil client/conn for empty target, got %+v", got)
	}
}

func TestUnit_SetupContextClient_Dials(t *testing.T) {
	t.Parallel()

	got, err := setupContextClient(config.Config{
		Environment:            "development",
		ContextGRPCTarget:      "127.0.0.1:9092",
		ContextAssembleTimeout: 45 * time.Millisecond,
	}, logger.Discard("proxy"), nil)
	if err != nil {
		t.Fatalf("setupContextClient: %v", err)
	}
	if got.client == nil || got.conn == nil {
		t.Fatal("expected non-nil client and conn")
	}
	t.Cleanup(func() {
		if err := got.conn.Close(); err != nil {
			t.Errorf("close conn: %v", err)
		}
	})
}

func TestUnit_CollectGRPCConns(t *testing.T) {
	t.Parallel()

	if got := collectGRPCConns(nil, nil); len(got) != 0 {
		t.Fatalf("len=%d, want 0", len(got))
	}
}
