package bootstrap

import (
	"testing"
	"time"

	authv1 "github.com/Rick1330/ibex-harness/packages/proto/gen/go/ibex/auth/v1"
)

type stubAuthClient struct {
	authv1.AuthServiceClient
}

func TestUnit_NewCredentialResolver(t *testing.T) {
	t.Parallel()
	if got := newCredentialResolver(nil, time.Second); got != nil {
		t.Fatal("nil client should yield nil resolver")
	}
	if got := newCredentialResolver(stubAuthClient{}, 0); got == nil {
		t.Fatal("expected resolver")
	}
}
